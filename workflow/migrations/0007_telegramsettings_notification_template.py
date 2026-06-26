from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ("workflow", "0006_telegramsettings_show_employee_ranking_to_staff"),
    ]

    operations = [
        migrations.AddField(
            model_name="telegramsettings",
            name="notification_template",
            field=models.TextField(blank=True, default="🔔 {title}\n\n{message}{object_line}"),
        ),
    ]
