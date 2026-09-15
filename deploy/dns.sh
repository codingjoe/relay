# shellcheck shell=bash
#
# DNS lookups and the record set the zone has to publish.
#
# Every lookup asks a resolver directly, so the answer is what the world sees
# now, not what this machine cached. Pass a resolver to see what a specific
# resolver answers, and the zone's own nameserver to see what the zone answers
# before the delegation is in place.
#
# Sources deploy/config.sh and deploy/hcloud.sh. Step scripts source all three.

# Answers come back as FQDNs with a trailing dot, and hcloud reports the zone's
# nameservers the same way, so fold both sides of a comparison the same way.
fold_dns_values() {
    sed 's/\.$//' | tr '[:upper:]' '[:lower:]'
}

dns_answers() {
    local type="$1"
    local name="$2"
    local resolver="${3:-}"
    local arguments=(+short "$type" "$name")
    if [ -n "$resolver" ]; then
        arguments+=("@$resolver")
    fi
    dig "${arguments[@]}" 2>/dev/null | fold_dns_values | sort -u || true
}

dns_ptr_name() {
    local address="$1"
    local resolver="${2:-}"
    local arguments=(+short -x "$address")
    if [ -n "$resolver" ]; then
        arguments+=("@$resolver")
    fi
    dig "${arguments[@]}" 2>/dev/null | fold_dns_values | head -n 1 || true
}

# The resolver answers exactly the expected values and nothing else.
dns_has_records() {
    local type="$1"
    local name="$2"
    local resolver="$3"
    shift 3
    [ "$(printf '%s\n' "$@" | fold_dns_values | sort -u)" = "$(dns_answers "$type" "$name" "$resolver")" ]
}

# The relative record names the zone holds. The wildcard carries pg and redis,
# which the sender reaches over the-box's Layer 4 SNI routes.
zone_record_names() {
    printf '%s\n' "@" "*" ns1 ns2 mx1 mx2 smtp
}

# The hostnames the zone answers for. The wildcard covers pg, redis and
# storage, so a name without a record of its own still resolves.
platform_hostnames() {
    printf '%s\n' "$RELAY_HOSTNAME" "ns1.$RELAY_HOSTNAME" "ns2.$RELAY_HOSTNAME" \
        "mx1.$RELAY_HOSTNAME" "mx2.$RELAY_HOSTNAME" "smtp.$RELAY_HOSTNAME" \
        "pg.$RELAY_HOSTNAME" "redis.$RELAY_HOSTNAME"
}

# The name Caddy serves stored message bodies on. It resolves through the
# wildcard while it sits under the zone, and needs a record of its own
# elsewhere.
storage_hostname() {
    printf '%s' "${RELAY_STORAGE_DOMAIN:-storage.$RELAY_HOSTNAME}"
}

storage_hostname_is_covered() {
    case "$(storage_hostname)" in
        *."$RELAY_HOSTNAME") ;;
        *) return 1 ;;
    esac
}

# One name per egress address, so a blacklisted address rotates out on its own.
sender_hostname() {
    printf 'sender-%s.mail.%s' "$1" "$RELAY_HOSTNAME"
}

# Every address this deployment publishes resolves to the server, or to its own
# floating IP, at the given resolver.
a_records_resolve() {
    local resolver="$1"
    local address hostname index position
    local -a smtp_addresses=()
    read -ra smtp_addresses <<<"$(fetch_smtp_floating_ip_addresses)"
    [ -n "${smtp_addresses[0]:-}" ] || return 1
    address="$(fetch_server_address)"
    [ -n "$address" ] || return 1
    for hostname in $(platform_hostnames); do
        dns_has_records A "$hostname" "$resolver" "$address" || return 1
    done
    if storage_hostname_is_covered; then
        dns_has_records A "$(storage_hostname)" "$resolver" "$address" || return 1
    fi
    for ((index = 0; index < ${#smtp_addresses[@]}; index++)); do
        position=$((index + 1))
        hostname="$(sender_hostname "$position")"
        dns_has_records A "$hostname" "$resolver" "${smtp_addresses[$index]}" || return 1
    done
}

# Every PTR record matches its forward record. Hetzner answers for reverse
# zones, so ask hcloud rather than a resolver.
ptr_records_are_set() {
    local index position address hostname
    local -a smtp_addresses=()
    read -ra smtp_addresses <<<"$(fetch_smtp_floating_ip_addresses)"
    [ -n "${smtp_addresses[0]:-}" ] || return 1
    [ "$(fetch_server_ptr_name)" = "$RELAY_HOSTNAME" ] || return 1
    for ((index = 0; index < ${#smtp_addresses[@]}; index++)); do
        position=$((index + 1))
        address="$(smtp_floating_ip_name "$position")"
        hostname="$(sender_hostname "$position")"
        [ "$(floating_ip_ptr_name "$address")" = "$hostname" ] || return 1
    done
}

ptr_records_are_propagated() {
    local resolver="$1"
    local address index position hostname
    local -a smtp_addresses=()
    address="$(fetch_server_address)"
    [ -n "$address" ] || return 1
    [ "$(dns_ptr_name "$address" "$resolver")" = "$RELAY_HOSTNAME" ] || return 1
    read -ra smtp_addresses <<<"$(fetch_smtp_floating_ip_addresses)"
    [ -n "${smtp_addresses[0]:-}" ] || return 1
    for ((index = 0; index < ${#smtp_addresses[@]}; index++)); do
        position=$((index + 1))
        hostname="$(sender_hostname "$position")"
        [ "$(dns_ptr_name "${smtp_addresses[$index]}" "$resolver")" = "$hostname" ] || return 1
    done
}
