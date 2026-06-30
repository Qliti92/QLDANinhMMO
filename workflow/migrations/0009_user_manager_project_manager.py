from django.conf import settings
from django.db import migrations, models
import django.db.models.deletion


class Migration(migrations.Migration):
    dependencies = [
        ("workflow", "0008_purge_soft_deleted_projects"),
    ]

    operations = [
        migrations.AddField(
            model_name="user",
            name="manager",
            field=models.ForeignKey(
                blank=True,
                limit_choices_to={"role": "MANAGER"},
                null=True,
                on_delete=django.db.models.deletion.SET_NULL,
                related_name="managed_staff",
                to=settings.AUTH_USER_MODEL,
            ),
        ),
        migrations.AddField(
            model_name="project",
            name="manager",
            field=models.ForeignKey(
                blank=True,
                null=True,
                on_delete=django.db.models.deletion.SET_NULL,
                related_name="managed_projects",
                to=settings.AUTH_USER_MODEL,
            ),
        ),
        migrations.AddIndex(
            model_name="project",
            index=models.Index(fields=["manager"], name="wf_pr_manager_idx"),
        ),
    ]
