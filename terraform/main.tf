terraform {
  required_providers {
    hcloud = {
      source  = "hetznercloud/hcloud"
      version = "~> 1.50"
    }
    tls = {
      source  = "hashicorp/tls"
      version = "~> 4.0"
    }
    aws = {
      source  = "hashicorp/aws"
      version = "~> 5.0"
    }
  }
}

provider "hcloud" {
  token = var.hcloud_token
}

# AWS provider configured for Hetzner S3-compatible Object Storage
provider "aws" {
  region                      = var.s3_region
  access_key                  = var.s3_access_key
  secret_key                  = var.s3_secret_key
  skip_credentials_validation = true
  skip_metadata_api_check     = true
  skip_region_validation      = true
  skip_requesting_account_id  = true

  s3_use_path_style = true

  endpoints {
    s3 = "https://${var.s3_endpoint}"
  }
}

variable "hcloud_token" {
  type      = string
  sensitive = true
}

variable "hostname" {
  type    = string
  default = "relay.example.com"
}

variable "server_type" {
  type    = string
  default = "cx22"
}

variable "server_location" {
  type    = string
  default = "nbg1"
}

variable "ssh_public_keys" {
  type    = list(string)
  default = []
}

variable "smtp_floating_ip_count" {
  type    = number
  default = 1
}

# Hetzner S3 Object Storage
# Create S3 credentials in Hetzner Cloud Console → Object Storage → Credentials
variable "s3_access_key" {
  type      = string
  sensitive = true
}

variable "s3_secret_key" {
  type      = string
  sensitive = true
}

variable "s3_endpoint" {
  type    = string
  default = "nbg1.your-objectstorage.com"
}

variable "s3_region" {
  type    = string
  default = "nbg1"
}

variable "s3_bucket_name" {
  type    = string
  default = null
}

locals {
  # Bucket names are unique across Hetzner Object Storage, so derive a unique
  # name from the hostname instead of a generic one.
  s3_bucket_name = coalesce(var.s3_bucket_name, "relay-${replace(var.hostname, ".", "-")}")
}

# Deployment SSH key pair (used by the-box GitHub Actions)
resource "tls_private_key" "deploy_key" {
  algorithm = "ED25519"
}

resource "hcloud_ssh_key" "deploy_key" {
  name       = "${var.hostname}-deploy"
  public_key = tls_private_key.deploy_key.public_key_openssh
}

# Server
resource "hcloud_server" "relay" {
  name        = var.hostname
  server_type = var.server_type
  image       = "ubuntu-24.04"
  location    = var.server_location
  ssh_keys    = concat(var.ssh_public_keys, [hcloud_ssh_key.deploy_key.id])
  user_data = templatefile("${path.module}/cloud-init.yaml.tftpl", {
    deploy_public_key = tls_private_key.deploy_key.public_key_openssh
    smtp_ips          = [for ip in hcloud_floating_ip.smtp : ip.ip_address]
  })
}

# Floating IPs for SMTP (blacklist rotation). Hetzner allows only one primary
# IPv4 per server, so extra egress IPs must be floating IPs.
resource "hcloud_floating_ip" "smtp" {
  count         = var.smtp_floating_ip_count
  name          = "${var.hostname}-smtp-${count.index + 1}"
  type          = "ipv4"
  home_location = var.server_location
}

resource "hcloud_floating_ip_assignment" "smtp" {
  count          = var.smtp_floating_ip_count
  floating_ip_id = hcloud_floating_ip.smtp[count.index].id
  server_id      = hcloud_server.relay.id
}

# PTR records — must match forward A records
resource "hcloud_rdns" "server" {
  server_id  = hcloud_server.relay.id
  ip_address = hcloud_server.relay.ipv4_address
  dns_ptr    = var.hostname
}

resource "hcloud_rdns" "smtp" {
  count          = var.smtp_floating_ip_count
  floating_ip_id = hcloud_floating_ip.smtp[count.index].id
  ip_address     = hcloud_floating_ip.smtp[count.index].ip_address
  dns_ptr        = "smtp${count.index + 1}.${var.hostname}"
}

# S3 bucket for message storage (Hetzner Object Storage)
resource "aws_s3_bucket" "relay" {
  bucket = local.s3_bucket_name
}

resource "aws_s3_bucket_ownership_controls" "relay" {
  bucket = aws_s3_bucket.relay.id
  rule {
    object_ownership = "BucketOwnerPreferred"
  }
}

output "server_ip" {
  value = hcloud_server.relay.ipv4_address
}

output "smtp_ips" {
  value = [for ip in hcloud_floating_ip.smtp : ip.ip_address]
}

output "ssh_private_key" {
  value     = tls_private_key.deploy_key.private_key_openssh
  sensitive = true
}

output "s3_endpoint_url" {
  value = "https://${var.s3_endpoint}"
}

output "s3_bucket_name" {
  value = local.s3_bucket_name
}
