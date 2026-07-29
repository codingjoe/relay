import gzip
import io
import zipfile
from email import message_from_bytes


def iter_attachments(raw_bytes):
    """Yield decompressed attachment payloads from a raw email.

    Handles gzip and zip decompression automatically.
    """
    msg = message_from_bytes(raw_bytes)
    for part in msg.walk():
        if part.get_content_disposition() == "attachment":
            data = part.get_payload(decode=True)
            if data is not None:
                filename = part.get_filename() or ""
                content_type = part.get_content_type()
                if filename.endswith(".gz") or content_type == "application/gzip":
                    data = gzip.decompress(data)
                elif filename.endswith(".zip") or content_type == "application/zip":
                    with zipfile.ZipFile(io.BytesIO(data)) as zf:
                        data = zf.read(zf.namelist()[0])
                yield data


def first_attachment(raw_bytes):
    """Return the first decompressed attachment from a raw email, or None."""
    return next(iter_attachments(raw_bytes), None)
