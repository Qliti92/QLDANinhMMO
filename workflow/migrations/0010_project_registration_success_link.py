from django.db import migrations, models


class Migration(migrations.Migration):
    dependencies = [
        ("workflow", "0009_user_manager_project_manager"),
    ]

    operations = [
        migrations.AddField(
            model_name="project",
            name="registration_success_link",
            field=models.URLField(blank=True, max_length=1000),
        ),
    ]
