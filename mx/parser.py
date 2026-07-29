from abstract.email_utils import iter_attachments


def first_attachment(raw_bytes):
    """Return the first decompressed TLS-RPT attachment from a raw email, or None."""
    for data in iter_attachments(raw_bytes):
        return data
    return None
