import re
from email.errors import HeaderParseError
from email.header import decode_header

from django.db import migrations


def decode_header_value(subject):
    """
    Mirror abstract.email_utils.decode_header_value as of this migration.

    Data migrations are self-contained so later changes to the helper
    cannot redefine what this migration does on fresh deployments.
    """
    if not subject:
        return subject
    text = re.sub(r"\r\n|\r|\n", "", subject)
    try:
        chunks = decode_header(text)
    except HeaderParseError:
        chunks = [(text, None)]
    parts = []
    for data, charset in chunks:
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
    if not text:
        # Undecodable payload decodes to nothing; keep the raw value.
        text = subject
    try:
        text.encode("utf-8")
    except UnicodeEncodeError:
        text = text.encode("utf-8", "surrogateescape").decode("utf-8", "replace")
    return re.sub(r"\r\n|\r|\n", "", text)


def decode_stored_subjects(apps, schema_editor):
    Message = apps.get_model("message", "Message")
    changed = []
    for message in Message.objects.exclude(subject="").iterator():
        decoded = decode_header_value(message.subject)
        if decoded != message.subject:
            message.subject = decoded
            changed.append(message)
            if len(changed) >= 500:
                Message.objects.bulk_update(changed, ["subject"])
                changed.clear()
    if changed:
        Message.objects.bulk_update(changed, ["subject"])


class Migration(migrations.Migration):
    dependencies = [
        ("message", "0006_alter_message_subject"),
    ]

    operations = [
        # Irreversible: the byte-exact value remains in raw_body and headers.
        migrations.RunPython(decode_stored_subjects, migrations.RunPython.noop),
    ]
