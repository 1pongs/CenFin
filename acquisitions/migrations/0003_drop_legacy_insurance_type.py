from django.db import migrations


def drop_legacy_insurance_type(apps, schema_editor):
    # Some environments have a stray NOT NULL column 'insurance_type'
    # in acquisitions_acquisition that isn't part of the model. Drop it
    # to avoid IntegrityError on inserts.
    connection = schema_editor.connection
    # Only applicable for MySQL/MariaDB. Skip for SQLite and others.
    try:
        vendor = getattr(connection, "vendor", None)
    except Exception:
        vendor = None
    if vendor != "mysql":
        return
    table = 'acquisitions_acquisition'
    with connection.cursor() as cursor:
        # Check if the column exists
        cursor.execute(
            """
            SELECT COUNT(*)
            FROM INFORMATION_SCHEMA.COLUMNS
            WHERE TABLE_SCHEMA = DATABASE()
              AND TABLE_NAME = %s
              AND COLUMN_NAME = 'insurance_type'
            """,
            [table],
        )
        exists = cursor.fetchone()[0]
        if exists:
            cursor.execute(f"ALTER TABLE {table} DROP COLUMN insurance_type")


class Migration(migrations.Migration):

    dependencies = [
        ('acquisitions', '0002_remove_acquisition_maturity_date_and_more'),
    ]

    operations = [
        migrations.RunPython(drop_legacy_insurance_type, migrations.RunPython.noop),
    ]
