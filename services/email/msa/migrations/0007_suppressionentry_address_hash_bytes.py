from django.db import migrations


def hex_to_bytes(apps, schema_editor):
    """Store the digest as raw bytes instead of a hex string."""
    connection = schema_editor.connection
    table = connection.ops.quote_name("msa_suppressionentry")
    column = connection.ops.quote_name("address_hash")
    if connection.vendor == "postgresql":
        schema_editor.execute(
            f"ALTER TABLE {table} ALTER COLUMN {column} TYPE bytea "
            f"USING decode({column}, 'hex')"
        )
    else:
        with connection.cursor() as cursor:
            cursor.execute(f"SELECT id, {column} FROM {table}")  # noqa: S608
            rows = cursor.fetchall()
        for pk, value in rows:
            schema_editor.execute(
                f"UPDATE {table} SET {column} = %s WHERE id = %s",  # noqa: S608
                [bytes.fromhex(value), pk],
            )


def bytes_to_hex(apps, schema_editor):
    """Store the digest as a hex string again."""
    connection = schema_editor.connection
    table = connection.ops.quote_name("msa_suppressionentry")
    column = connection.ops.quote_name("address_hash")
    if connection.vendor == "postgresql":
        schema_editor.execute(
            f"ALTER TABLE {table} ALTER COLUMN {column} TYPE text "
            f"USING encode({column}, 'hex')"
        )
    else:
        with connection.cursor() as cursor:
            cursor.execute(f"SELECT id, {column} FROM {table}")  # noqa: S608
            rows = cursor.fetchall()
        for pk, value in rows:
            schema_editor.execute(
                f"UPDATE {table} SET {column} = %s WHERE id = %s",  # noqa: S608
                [bytes(value).hex(), pk],
            )


class Migration(migrations.Migration):
    dependencies = [
        ("msa", "0006_remove_outgoingmessage_feedback_id"),
    ]

    operations = [
        # The digest is unchanged, only its encoding. Hex text converts to
        # bytes without the plain address.
        migrations.RunPython(hex_to_bytes, bytes_to_hex),
    ]
