from django.db import migrations


def purge_soft_deleted_projects(apps, schema_editor):
    Project = apps.get_model("workflow", "Project")
    Project.objects.filter(deleted_at__isnull=False).delete()


class Migration(migrations.Migration):
    dependencies = [
        ("workflow", "0007_telegramsettings_notification_template"),
    ]

    operations = [
        migrations.RunPython(purge_soft_deleted_projects, migrations.RunPython.noop),
    ]
