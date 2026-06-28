<p align="center">
  <picture>
    <source media="(prefers-color-scheme: dark)" srcset="./images/logo-dark.svg">
    <source media="(prefers-color-scheme: light)" srcset="./images/logo-light.svg">
    <img alt="The Box – Signature Edition: Secure, convenient, fast & free forever!" src="./images/logo-light.svg">
  </picture>
</p>

# The Box — Django Edition: Secure, convenient, fast & free forever!

Production ready zero-config Django deployment and development on your own hardware:

- 🏗️ [12-factor] app principles
- 🚀 continues deployment
- 🔐 environment & key management
- 🗄️ managed PostgreSQL databases
- 🔔 managed [updates & security alerts][dependabot]
- 🔒 SSL via [Let's Encrypt][letsencrypt]

_No config, no costs, just GitHub and your own server._

**Check out our Demo running on a Raspberry Pi 5 8GB: [https://django.the-box.sh](https://django.the-box.sh)**

## Getting Started

1. Use the "Use this template" button to create a new repository for your project.
1. Make sure you have a fresh linux server (VPS or RaspberryPi) that you can connect to via SSH.
1. Make sure you have both [GitHub CLI](https://cli.github.com/), [Docker](https://www.docker.com/) or [Podman](https://podman.io/), and [dtop](https://github.com/amir20/dtop) installed on your development.
1. Run the installer on you development machine:

```
bash <(curl -fsSL https://the-box.sh/install.sh)
```

The installer will guide you through the setup process and get your first application up and running in seconds!

Do connect to the Box, use:

```shell
dtop
```

### DNS Setup

If you haven't done so already, here are the steps to set up your DNS records:

```text
A @ YOUR_SERVER_IP
AAAA @ YOUR_SERVER_IPV6
CNAME * your.domain
```

Find out more at [the-box.sh](https://the-box.sh).

[12-factor]: https://12factor.net/
[dependabot]: https://github.com/dependabot
[letsencrypt]: https://letsencrypt.org/
