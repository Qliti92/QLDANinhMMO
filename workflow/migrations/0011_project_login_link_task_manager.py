from django.db import migrations, models
import django.db.models.deletion


def backfill_task_manager(apps, schema_editor):
    Task = apps.get_model("workflow", "Task")
    User = apps.get_model("workflow", "User")

    manager_ids = set(User.objects.filter(role="MANAGER").values_list("pk", flat=True))
    for task in Task.objects.select_related("assigned_by", "assignee"):
        manager_id = None
        if task.assigned_by_id in manager_ids:
            manager_id = task.assigned_by_id
        elif getattr(task.assignee, "manager_id", None):
            manager_id = task.assignee.manager_id
        if manager_id:
            task.manager_id = manager_id
            task.save(update_fields=["manager"])


class Migration(migrations.Migration):
    dependencies = [
        ("workflow", "0010_project_registration_success_link"),
    ]

    operations = [
        migrations.AddField(
            model_name="project",
            name="login_link",
            field=models.URLField(blank=True, max_length=1000),
        ),
        migrations.AddField(
            model_name="task",
            name="manager",
            field=models.ForeignKey(
                blank=True,
                null=True,
                on_delete=django.db.models.deletion.SET_NULL,
                related_name="managed_tasks",
                to="workflow.user",
            ),
        ),
        migrations.AddIndex(
            model_name="task",
            index=models.Index(fields=["manager"], name="wf_tk_manager_idx"),
        ),
        migrations.RunPython(backfill_task_manager, migrations.RunPython.noop),
    ]
