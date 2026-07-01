from django.db.models import Q, QuerySet

from .models import Project, Task


class ProjectRepository:
    @staticmethod
    def visible_to(user) -> QuerySet[Project]:
        qs = Project.objects.active().select_related("current_employee", "created_by", "manager")
        if not user.is_authenticated:
            return qs.none()
        if user.is_admin_role:
            return qs
        if user.is_manager_role:
            return qs.filter(
                Q(manager=user)
                | Q(created_by=user)
                | Q(current_employee__manager=user)
            ).distinct()
        return qs.filter(current_employee=user)

    @staticmethod
    def search_and_filter(qs: QuerySet[Project], params) -> QuerySet[Project]:
        query = params.get("q")
        project_state = params.get("project_state")
        status = params.get("status")
        result = params.get("result")
        employee = params.get("employee")
        priority = params.get("priority")
        deadline_status = params.get("deadline_status")
        date_from = params.get("date_from")
        date_to = params.get("date_to")

        if query:
            qs = qs.filter(Q(project_name__icontains=query) | Q(project_link__icontains=query))
        if project_state:
            qs = qs.filter(project_state=project_state)
        if status:
            qs = qs.filter(status=status)
        if result:
            qs = qs.filter(result=result)
        if employee:
            qs = qs.filter(current_employee_id=employee)
        if priority:
            qs = qs.filter(priority=priority)
        if deadline_status:
            from django.utils import timezone

            now = timezone.now()
            active = qs.exclude(status__in=[Project.Status.DONE, Project.Status.CANCELLED])
            if deadline_status == "none":
                qs = active.filter(deadline_at__isnull=True)
            elif deadline_status == "due_soon":
                qs = active.filter(deadline_at__gte=now, deadline_at__lte=now + timezone.timedelta(hours=24))
            elif deadline_status == "overdue":
                qs = active.filter(deadline_at__lt=now)
        if date_from:
            qs = qs.filter(created_at__date__gte=date_from)
        if date_to:
            qs = qs.filter(created_at__date__lte=date_to)
        return qs


class TaskRepository:
    @staticmethod
    def visible_to(user) -> QuerySet[Task]:
        qs = Task.objects.active().select_related("assignee", "assigned_by", "manager")
        if not user.is_authenticated:
            return qs.none()
        if user.is_admin_role:
            return qs
        if user.is_manager_role:
            return qs.filter(Q(manager=user) | Q(assigned_by=user) | Q(assignee__manager=user)).distinct()
        return qs.filter(assignee=user)

    @staticmethod
    def search_and_filter(qs: QuerySet[Task], params) -> QuerySet[Task]:
        query = params.get("q")
        status = params.get("status")
        employee = params.get("employee")
        priority = params.get("priority")
        deadline_status = params.get("deadline_status")
        date_from = params.get("date_from")
        date_to = params.get("date_to")

        if query:
            qs = qs.filter(Q(title__icontains=query) | Q(description__icontains=query))
        if status:
            qs = qs.filter(status=status)
        if employee:
            qs = qs.filter(assignee_id=employee)
        if priority:
            qs = qs.filter(priority=priority)
        if deadline_status:
            from django.utils import timezone

            now = timezone.now()
            active = qs.exclude(status__in=[Task.Status.DONE, Task.Status.CANCELLED])
            if deadline_status == "none":
                qs = active.filter(deadline_at__isnull=True)
            elif deadline_status == "due_soon":
                qs = active.filter(deadline_at__gte=now, deadline_at__lte=now + timezone.timedelta(hours=24))
            elif deadline_status == "overdue":
                qs = active.filter(deadline_at__lt=now)
        if date_from:
            qs = qs.filter(created_at__date__gte=date_from)
        if date_to:
            qs = qs.filter(created_at__date__lte=date_to)
        return qs
