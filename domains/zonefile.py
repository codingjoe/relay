"""BIND zone file export for one group of domain records."""

ZONE_FILE_TTL = 3600


def build_zone_file(domain, group, nameservers, mx_hostnames, mx_priority):
    """Return a BIND zone file with the records for one group."""

    def relative(name):
        if name == domain.name:
            return "@"
        return name.removesuffix(f".{domain.name}")

    def txt(value):
        return f'"{value}"'

    match group:
        case "delegation":
            records = [
                (relative(domain.sender_domain), "NS", f"{nameserver.split(':')[0]}.")
                for nameserver in nameservers
            ]
        case "sending":
            records = [
                ("@", "TXT", txt(domain.root_spf_record)),
                *(
                    (relative(name), "CNAME", f"{target}.")
                    for name, target in domain.dkim_cnames.values()
                ),
            ]
        case "receiving":
            records = [
                ("@", "MX", f"{mx_priority} {hostname.split(':')[0]}.")
                for hostname in mx_hostnames
            ]
        case "reporting":
            records = [
                (relative(domain.dmarc_record_name), "TXT", txt(domain.dmarc_record)),
                (
                    relative(domain.mta_sts_record_name),
                    "CNAME",
                    f"{domain.mta_sts_record_cname_target}.",
                ),
                (
                    relative(domain.mta_sts_hostname),
                    "CNAME",
                    f"{domain.mta_sts_cname_target}.",
                ),
                (
                    relative(domain.tls_rpt_record_name),
                    "CNAME",
                    f"{domain.tls_rpt_record_cname_target}.",
                ),
            ]
        case _:
            raise ValueError(group)

    return (
        "\n".join(
            [
                f"$ORIGIN {domain.name}.",
                f"$TTL {ZONE_FILE_TTL}",
                "",
                *(
                    f"{name} IN {record_type} {value}"
                    for name, record_type, value in records
                ),
            ]
        )
        + "\n"
    )
