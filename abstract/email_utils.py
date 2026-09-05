import base64
import gzip
import io
import re
import zipfile
from email import message_from_bytes
from email.header import decode_header


class MissingAttachmentError(ValueError):
    """The email contains no attachment."""


def decode_header_value(value):
    """
    Return an RFC 2047-decoded header value as unfolded text.

    Encoded-words are decoded with their declared charset. Raw 8-bit
    bytes without a charset are assumed to be UTF-8. Line folding is
    removed and undecodable bytes become U+FFFD, so the result is
    always a single-line, valid `str`.
    """
    if not value:
        return ""
    parts = []
    for data, charset in decode_header(value):
        if isinstance(data, str):
            parts.append(data)
            continue
        if charset in (None, "unknown-8bit"):
            charset = "utf-8"
        try:
            parts.append(data.decode(charset, "replace"))
        except LookupError:
            parts.append(data.decode("utf-8", "replace"))
    text = "".join(parts)
    try:
        text.encode("utf-8")
    except UnicodeEncodeError:
        # Input may carry surrogate escapes from raw 8-bit bytes.
        text = text.encode("utf-8", "surrogateescape").decode("utf-8", "replace")
    # Unfold per RFC 5322: drop the CRLF, keep the whitespace that follows.
    return re.sub(r"\r?\n", "", text)


def extract_part_text(part):
    """Extract text content from a MIME part, including sub-messages and base64 data."""
    if part.is_multipart():
        for sub in part.get_payload():
            if payload := sub.get_payload(decode=True):
                # Python's email parser may return base64 bytes when CTE is set
                # but the sub-message structure doesn't honor it
                try:
                    stripped = bytes(payload).strip()
                    decoded = base64.b64decode(stripped)
                    re_encoded = base64.b64encode(decoded)
                    if re_encoded == stripped.replace(b"\n", b"").replace(b"\r", b""):
                        payload = decoded
                except ValueError, TypeError:
                    pass  # payload is not base64-encoded, use as-is
                return payload.decode("utf-8", errors="replace")
        return ""
    if payload := part.get_payload(decode=True):
        return payload.decode("utf-8", errors="replace")
    return ""


def iter_attachments(raw_bytes):
    """
    Yield decompressed attachment payloads from a raw email.

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
