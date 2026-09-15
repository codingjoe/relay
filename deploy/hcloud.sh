# shellcheck shell=bash
#
# Read-only helpers for the Hetzner Cloud resources this deployment owns.
#
# A step calls hcloud directly for anything that changes a resource. These
# helpers only answer questions, and they answer with an empty value when the
# resource is absent, so a step can report the work as pending instead of
# failing.
#
# Sources deploy/config.sh. Step scripts source both.

require_hcloud() {
    require_command hcloud jq
    hcloud server list >/dev/null 2>&1 ||
    fail "hcloud is not authenticated. Run: HCLOUD_TOKEN=<token> hcloud context create relay --token-from-env"
}

zone_exists() {
    hcloud zone describe "$RELAY_HOSTNAME" >/dev/null 2>&1
}

server_exists() {
    hcloud server describe "$RELAY_HOSTNAME" >/dev/null 2>&1
}

floating_ip_exists() {
    hcloud floating-ip describe "$1" >/dev/null 2>&1
}

smtp_floating_ip_name() {
    printf '%s-smtp-%s' "$RELAY_HOSTNAME" "$1"
}

# The hcloud names of the SSH keys this deployment uploads, with the file each
# holds, one tab separated pair per line. A public key file that is not on this
# machine is skipped, so the key is never requested.
ssh_key_pairs() {
    local key_file
    printf '%s\t%s\n' "$DEPLOY_KEY_NAME" "${DEPLOY_KEY}.pub"
    for key_file in "${SSH_PUBLIC_KEY_FILES[@]}"; do
        [ -f "$key_file" ] || continue
        printf '%s\t%s\n' "$RELAY_HOSTNAME-$(basename "$key_file" .pub)" "$key_file"
    done
}

ssh_key_names() {
    local key_name key_file
    while IFS=$'\t' read -r key_name key_file; do
        printf '%s\n' "$key_name"
    done < <(ssh_key_pairs)
}

uploaded_ssh_key() {
    hcloud ssh-key describe "$1" -o json 2>/dev/null | jq -r '.public_key // empty' || true
}

fetch_zone_nameservers() {
    hcloud zone describe "$RELAY_HOSTNAME" -o json 2>/dev/null |
    jq -r '[.authoritative_nameservers.assigned[]?] | join(" ")' || true
}

fetch_zone_delegation_status() {
    hcloud zone describe "$RELAY_HOSTNAME" -o json 2>/dev/null |
    jq -r '.authoritative_nameservers.delegation_status // "unknown"' || true
}

# Ask one nameserver, so a record that Hetzner accepted is visible right away,
# without waiting for the delegation to the parent zone.
first_zone_nameserver() {
    local nameservers
    read -ra nameservers <<<"$(fetch_zone_nameservers)"
    printf '%s' "${nameservers[0]:-}"
}

fetch_server_id() {
    hcloud server describe "$RELAY_HOSTNAME" -o json 2>/dev/null | jq -r '.id // empty' || true
}

fetch_server_status() {
    hcloud server describe "$RELAY_HOSTNAME" -o json 2>/dev/null | jq -r '.status // empty' || true
}

fetch_server_address() {
    hcloud server ip "$RELAY_HOSTNAME" 2>/dev/null || true
}

fetch_server_ptr_name() {
    hcloud server describe "$RELAY_HOSTNAME" -o json 2>/dev/null |
    jq -r '.public_net.ipv4.dns_ptr // empty' || true
}

# Prints the addresses separated by spaces, so a caller can read them into an
# array with: read -ra addresses <<<"$(fetch_smtp_floating_ip_addresses)"
fetch_smtp_floating_ip_addresses() {
    local index
    for ((index = 1; index <= SMTP_FLOATING_IP_COUNT; index++)); do
        floating_ip_address "$(smtp_floating_ip_name "$index")"
    done | tr '\n' ' '
}

floating_ip_address() {
    hcloud floating-ip describe "$1" -o json 2>/dev/null | jq -r '.ip // empty' || true
}

floating_ip_server_id() {
    hcloud floating-ip describe "$1" -o json 2>/dev/null | jq -r '.server // empty' || true
}

floating_ip_ptr_name() {
    hcloud floating-ip describe "$1" -o json 2>/dev/null |
    jq -r '[.dns_ptr[]?.dns_ptr] | first // empty' || true
}

# A server type and a location are only valid together, and hcloud's own error
# for a bad pairing is opaque. Check it before creating anything.
validate_server_type_location() {
    local locations
    if ! hcloud server-type describe "$SERVER_TYPE" >/dev/null 2>&1; then
        fail "hcloud does not know the server type \"$SERVER_TYPE\""
    fi
    locations="$(hcloud server-type describe "$SERVER_TYPE" -o json |
        jq -r '[.prices[].location] | join(", ")')"
    case ", $locations, " in
        *", $SERVER_LOCATION,"*) ;;
        *)
            fail "$SERVER_TYPE is not offered in $SERVER_LOCATION. Available locations: $locations"
            ;;
    esac
}
