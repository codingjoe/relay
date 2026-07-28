"""Parse TLS-RPT report emails."""

import gzip
import io
import json
import zipfile
from email import message_from_bytes

from .serializers import TlsReportSerializer


def extract_attachment(raw_bytes):
    """Return the decompressed TLS-RPT report attachment from a raw email, or None."""
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
                return data
    return None


def parse_tls_json(data):
    """Return a TLS-RPT JSON report deserialized via a DRF serializer."""
    report_data = json.loads(data)
    serializer = TlsReportSerializer(data=report_data)
    serializer.is_valid(raise_exception=True)
    return {
        "metadata": serializer.metadata,
        "policies": serializer.parsed_policies,
    }
