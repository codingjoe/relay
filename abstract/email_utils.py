import gzip
import io
import zipfile
from email import message_from_bytes

DEFAULT_MAX_ATTACHMENT_SIZE_BYTES = 25 * 1024**2
DEFAULT_MAX_ARCHIVE_MEMBER_COUNT = 1
DEFAULT_MAX_ZIP_DIRECTORY_SIZE_BYTES = 64 * 1024
ZIP_END_SIGNATURE = b"PK\x05\x06"


class AttachmentSizeLimitExceeded(ValueError):
    """Indicate that an attachment exceeds the permitted expanded size."""


def read_attachment(stream, max_size_bytes):
    """Read an attachment up to the permitted size."""
    data = stream.read(max_size_bytes + 1)
    if len(data) > max_size_bytes:
        raise AttachmentSizeLimitExceeded(
            f"Attachment exceeds the {max_size_bytes}-byte size limit."
        )
    return data


def validate_zip_structure(data):
    """Reject ZIPs whose directory can describe excessive members."""
    end_offset = data.rfind(ZIP_END_SIGNATURE)
    if end_offset < 0 or end_offset + 22 > len(data):
        raise zipfile.BadZipFile("ZIP attachment has no valid end record.")
    member_count = int.from_bytes(data[end_offset + 10 : end_offset + 12], "little")
    directory_size = int.from_bytes(data[end_offset + 12 : end_offset + 16], "little")
    if member_count != DEFAULT_MAX_ARCHIVE_MEMBER_COUNT:
        raise ValueError("ZIP attachment must contain one file.")
    if directory_size > DEFAULT_MAX_ZIP_DIRECTORY_SIZE_BYTES:
        raise ValueError("ZIP attachment directory is too large.")


def iter_attachments(
    raw_bytes,
    *,
    max_size_bytes=DEFAULT_MAX_ATTACHMENT_SIZE_BYTES,
):
    """Yield attachment payloads within the expanded size limit."""
    if max_size_bytes < 1:
        raise ValueError("max_size_bytes must be positive.")
    msg = message_from_bytes(raw_bytes)
    for part in msg.walk():
        if part.get_content_disposition() == "attachment":
            data = part.get_payload(decode=True)
            if data is not None:
                if len(data) > max_size_bytes:
                    raise AttachmentSizeLimitExceeded(
                        f"Attachment exceeds the {max_size_bytes}-byte size limit."
                    )
                filename = part.get_filename() or ""
                content_type = part.get_content_type()
                if filename.endswith(".gz") or content_type == "application/gzip":
                    with gzip.GzipFile(fileobj=io.BytesIO(data)) as gzip_file:
                        data = read_attachment(gzip_file, max_size_bytes)
                elif filename.endswith(".zip") or content_type == "application/zip":
                    validate_zip_structure(data)
                    with zipfile.ZipFile(io.BytesIO(data)) as archive:
                        members = archive.infolist()
                        if len(members) != DEFAULT_MAX_ARCHIVE_MEMBER_COUNT:
                            raise ValueError("ZIP attachment must contain one file.")
                        member = members[0]
                        if member.is_dir() or member.flag_bits & 1:
                            raise ValueError(
                                "ZIP attachment member must be an unencrypted file."
                            )
                        if member.file_size > max_size_bytes:
                            raise AttachmentSizeLimitExceeded(
                                f"Attachment exceeds the {max_size_bytes}-byte size limit."
                            )
                        with archive.open(member) as zip_file:
                            data = read_attachment(zip_file, max_size_bytes)
                yield data
