"""Parse TLS-RPT report emails."""

import gzip
import io
import zipfile
from email import message_from_bytes

from .serializers import TlsReportSerializer


def extract_attachment(raw_bytes):
    """Extract and decompress the report attachment from a raw email.

    TLS-RPT reports arrive as gzip- or zip-compressed JSON.
    Returns the decompressed bytes, or ``None`` if no attachment is found.
    """
    msg = message_from_bytes(raw_bytes)
    for part in msg.walk():
        if part.get_content_disposition() != "attachment":
            continue
        data = part.get_payload(decode=True)
        if data is None:
            continue
        filename = part.get_filename() or ""
        content_type = part.get_content_type()
        if filename.endswith(".gz") or content_type == "application/gzip":
            data = gzip.decompress(data)
        elif filename.endswith(".zip") or content_type == "application/zip":
            with zipfile.ZipFile(io.BytesIO(data)) as zf:
                data = zf.read(zf.namelist()[0])
        return data
    return None


def parse_tls_json(data):
    """Parse a TLS-RPT JSON report using a DRF serializer.

    Returns ``{"metadata": {...}, "policies": [...]}``.
    """
    import json

    report_data = json.loads(data)
    serializer = TlsReportSerializer(data=report_data)
    serializer.is_valid(raise_exception=True)
    return {
        "metadata": serializer.metadata,
        "policies": serializer.parsed_policies,
    }
