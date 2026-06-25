from django.contrib.auth import get_user_model
from django.core.management.base import BaseCommand

from workflow.models import Project
from workflow.services import ProjectService

User = get_user_model()


class Command(BaseCommand):
    help = "Create demo users and projects."

    def handle(self, *args, **options):
        admin, _ = User.objects.get_or_create(
            username="admin",
            defaults={"role": User.Role.ADMIN, "is_staff": True, "is_superuser": True, "email": "admin@example.com"},
        )
        admin.set_password("admin123")
        admin.save()

        manager, _ = User.objects.get_or_create(
            username="manager",
            defaults={"role": User.Role.MANAGER, "is_staff": True, "email": "manager@example.com"},
        )
        manager.set_password("manager123")
        manager.save()

        staff, _ = User.objects.get_or_create(
            username="staff",
            defaults={"role": User.Role.STAFF, "email": "staff@example.com"},
        )
        staff.set_password("staff123")
        staff.save()

        projects = []
        for index in range(1, 6):
            project, _ = Project.objects.get_or_create(
                project_link=f"https://example.com/project-{index}",
                defaults={"project_name": f"Demo Project {index}", "created_by": manager},
            )
            projects.append(project)
        ProjectService.assign(projects[:3], staff, manager)
        self.stdout.write(self.style.SUCCESS("Demo data created."))
