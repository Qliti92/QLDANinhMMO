from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ("workflow", "0005_project_project_state_project_wf_pr_state_idx"),
    ]

    operations = [
        migrations.AddField(
            model_name="telegramsettings",
            name="show_employee_ranking_to_staff",
            field=models.BooleanField(default=True),
        ),
    ]
