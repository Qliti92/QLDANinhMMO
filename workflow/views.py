from io import BytesIO
import logging

from django.contrib import messages
from django.contrib.auth import get_user_model
from django.contrib.auth.mixins import LoginRequiredMixin
from django.db.models import Count, Q
from django.http import FileResponse, JsonResponse
from django.shortcuts import get_object_or_404, redirect, render
from django.urls import reverse_lazy
from django.utils import timezone
from django.views import View
from django.views.generic import CreateView, DetailView, FormView, ListView, TemplateView, UpdateView

from .forms import (
    AssignmentForm,
    BulkActionForm,
    GeneralSettingsForm,
    ImportExcelForm,
    ProjectForm,
    ProgressUpdateForm,
    QuickProjectUpdateForm,
    QuickProjectStateForm,
    QuickResultForm,
    QuickStatusForm,
    StaffTaskUpdateForm,
    StaffProjectUpdateForm,
    TaskForm,
    TaskProgressUpdateForm,
    TelegramProfileForm,
    TelegramSettingsForm,
    UserCreateForm,
    UserUpdateForm,
)
from .models import ActivityLog, ImportBatch, Notification, Project, ProjectProgress, Task, TelegramSettings
from .permissions import AdminRequiredMixin, ManagerRequiredMixin, require_manager
from .repositories import ProjectRepository, TaskRepository
from .services import ImportService, NotificationService, ProgressService, ProjectService, ReportService, TaskService, TelegramService, build_projects_workbook, excel_safe, log_activity

User = get_user_model()
logger = logging.getLogger(__name__)


def scoped_staff_queryset(user):
    qs = User.objects.filter(role=User.Role.STAFF, is_active=True)
    if user.is_manager_role:
        return qs.filter(manager=user)
    return qs


def page_not_found(request, exception):
    return render(request, "404.html", status=404)


class DashboardView(LoginRequiredMixin, TemplateView):
    template_name = "workflow/dashboard.html"

    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)
        qs = ProjectRepository.visible_to(self.request.user)
        telegram_settings = TelegramSettings.get_solo()
        context["counts"] = ReportService.dashboard_counts(qs)
        context["recent_projects"] = qs[:10]
        context["show_employee_ranking"] = self.request.user.can_manage_projects or telegram_settings.show_employee_ranking_to_staff
        context["employee_ranking"] = ReportService.employee_kpis(self.request.user)[:8] if context["show_employee_ranking"] else []
        active = qs.exclude(status__in=[Project.Status.DONE, Project.Status.CANCELLED])
        now = timezone.now()
        context["stat_groups"] = [
            ("Tổng quan", ["total", "new", "assigned", "working", "completed", "cancelled"]),
            ("Kết quả", ["profit", "loss", "pending_result", "avg_progress"]),
            ("Hạn xử lý", ["overdue", "due_soon", "no_deadline", "updated_today"]),
            ("Ưu tiên", ["high_priority", "urgent_priority"]),
        ]
        context["overdue_projects"] = active.filter(deadline_at__lt=now).select_related("current_employee")[:6]
        context["due_soon_projects"] = active.filter(deadline_at__gte=now, deadline_at__lte=now + timezone.timedelta(hours=24)).select_related("current_employee")[:6]
        context["urgent_projects"] = qs.filter(priority=Project.Priority.URGENT).select_related("current_employee")[:6]
        context["blocked_progress"] = (
            ProjectProgress.objects.select_related("project", "user")
            .filter(project__in=qs)
            .exclude(blocker_note="")[:6]
        )
        return context


class ProjectListView(LoginRequiredMixin, ListView):
    model = Project
    template_name = "workflow/project_list.html"
    context_object_name = "projects"
    paginate_by = 20

    def get_queryset(self):
        qs = ProjectRepository.visible_to(self.request.user)
        return ProjectRepository.search_and_filter(qs, self.request.GET)

    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)
        context["project_states"] = Project.ProjectState.choices
        context["statuses"] = Project.Status.choices
        context["results"] = Project.Result.choices
        context["priorities"] = Project.Priority.choices
        context["employees"] = scoped_staff_queryset(self.request.user)
        context["managers"] = User.objects.filter(role=User.Role.MANAGER, is_active=True)
        context["assign_form"] = AssignmentForm(user=self.request.user)
        return context


class ProjectDetailView(LoginRequiredMixin, DetailView):
    model = Project
    template_name = "workflow/project_detail.html"
    context_object_name = "project"

    def get_queryset(self):
        return ProjectRepository.visible_to(self.request.user)

    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)
        context["assign_form"] = AssignmentForm(initial={"project_ids": str(self.object.pk)}, user=self.request.user)
        context["quick_update_form"] = QuickProjectUpdateForm(
            initial={
                "project_state": self.object.project_state,
                "status": self.object.status,
                "result": self.object.result,
            },
            staff_only=not self.request.user.can_manage_projects,
        )
        context["project_state_form"] = QuickProjectStateForm(initial={"project_state": self.object.project_state})
        context["status_form"] = QuickStatusForm(initial={"status": self.object.status}, staff_only=not self.request.user.can_manage_projects)
        context["result_form"] = QuickResultForm(initial={"result": self.object.result})
        context["progress_form"] = ProgressUpdateForm()
        return context


class ProjectCreateView(ManagerRequiredMixin, CreateView):
    model = Project
    form_class = ProjectForm
    template_name = "workflow/project_form.html"

    def get_form_kwargs(self):
        kwargs = super().get_form_kwargs()
        kwargs["user"] = self.request.user
        return kwargs

    def form_valid(self, form):
        form.instance.created_by = self.request.user
        if self.request.user.is_manager_role:
            form.instance.manager = self.request.user
        response = super().form_valid(form)
        log_activity(
            self.request.user,
            ActivityLog.Action.PROJECT_CREATED,
                "Đã tạo dự án",
            project=self.object,
            request=self.request,
        )
        messages.success(self.request, "Đã tạo dự án.")
        return response


class ProjectUpdateView(LoginRequiredMixin, UpdateView):
    model = Project
    template_name = "workflow/project_form.html"

    def get_queryset(self):
        return ProjectRepository.visible_to(self.request.user)

    def get_form_class(self):
        return ProjectForm if self.request.user.can_manage_projects else StaffProjectUpdateForm

    def get_form_kwargs(self):
        kwargs = super().get_form_kwargs()
        if self.request.user.can_manage_projects:
            kwargs["user"] = self.request.user
        return kwargs

    def form_valid(self, form):
        before_project_state = self.object.project_state
        before_status = self.object.status
        before_result = self.object.result
        response = super().form_valid(form)
        after_project_state = self.object.project_state
        after_status = self.object.status
        after_result = self.object.result
        if before_project_state != after_project_state:
            log_activity(
                self.request.user,
                ActivityLog.Action.PROJECT_UPDATED,
                f"ÄÃ£ Ä‘á»•i tráº¡ng thÃ¡i dá»± Ã¡n thÃ nh {self.object.get_project_state_display()}",
                project=self.object,
                request=self.request,
            )
        if before_status != after_status:
            self.object.status = before_status
            ProjectService.update_status(self.object, after_status, self.request.user, request=self.request)
        if before_result != after_result:
            self.object.result = before_result
            ProjectService.update_result(self.object, after_result, self.request.user, request=self.request)
        if before_project_state == after_project_state and before_status == after_status and before_result == after_result:
            log_activity(
                self.request.user,
                ActivityLog.Action.PROJECT_UPDATED,
                "Đã cập nhật dự án",
                project=self.object,
                request=self.request,
            )
        messages.success(self.request, "Đã cập nhật dự án.")
        return response


class ProjectDeleteView(ManagerRequiredMixin, View):
    def post(self, request, pk):
        project = get_object_or_404(ProjectRepository.visible_to(request.user), pk=pk)
        ProjectService.soft_delete([project], request.user, request=request)
        messages.success(request, "Đã xóa dự án.")
        return redirect("project_list")


class ProjectQuickUpdateView(LoginRequiredMixin, View):
    def post(self, request, pk):
        project = get_object_or_404(ProjectRepository.visible_to(request.user), pk=pk)
        form = QuickProjectUpdateForm(request.POST, staff_only=not request.user.can_manage_projects)
        if not form.is_valid():
            messages.error(request, "Không thể lưu thao tác nhanh.")
            return redirect(project.get_absolute_url())

        before_project_state = project.project_state
        before_status = project.status
        before_result = project.result
        after_project_state = form.cleaned_data["project_state"]
        after_status = form.cleaned_data["status"]
        after_result = form.cleaned_data["result"]

        if before_project_state != after_project_state:
            project.project_state = after_project_state
            project.save(update_fields=["project_state", "updated_at"])
            log_activity(
                request.user,
                ActivityLog.Action.PROJECT_UPDATED,
                f"Đã đổi trạng thái dự án thành {project.get_project_state_display()}",
                project=project,
                request=request,
            )
            if not request.user.can_manage_projects:
                NotificationService.notify_managers(
                    actor=request.user,
                    project=project,
                    title=f"{request.user} cập nhật trạng thái dự án",
                    message=f"{request.user} đã cập nhật trạng thái dự án “{project.project_name}” thành {project.get_project_state_display()}.",
                    notification_type=Notification.Type.STATUS_UPDATED,
                )

        if before_status != after_status:
            ProjectService.update_status(project, after_status, request.user, request=request)

        if before_result != after_result:
            ProjectService.update_result(project, after_result, request.user, request=request)

        if before_project_state == after_project_state and before_status == after_status and before_result == after_result:
            messages.info(request, "Không có thay đổi mới.")
        else:
            messages.success(request, "Đã lưu thao tác nhanh.")
        return redirect(project.get_absolute_url())


class ImportExcelView(ManagerRequiredMixin, FormView):
    template_name = "workflow/import.html"
    form_class = ImportExcelForm
    success_url = reverse_lazy("project_list")

    def form_valid(self, form):
        try:
            if form.cleaned_data.get("file"):
                summary = ImportService.import_xlsx(form.cleaned_data["file"], self.request.user, request=self.request)
            else:
                summary = ImportService.import_pasted_links(form.cleaned_data["links"], self.request.user, request=self.request)
        except ValueError as exc:
            form.add_error(None, str(exc))
            return self.form_invalid(form)
        except Exception:
            logger.exception("Import failed for user_id=%s", self.request.user.pk)
            form.add_error(None, "Khong import duoc du lieu. Vui long kiem tra file/link hoac xem log server.")
            return self.form_invalid(form)
        messages.success(
            self.request,
            f"Đã import {summary.batch.imported_rows} dòng. Trùng: {summary.batch.duplicate_rows}. Lỗi: {summary.batch.invalid_rows}.",
        )
        return redirect("import_detail", pk=summary.batch.pk)


class ImportBatchListView(ManagerRequiredMixin, ListView):
    model = ImportBatch
    template_name = "workflow/import_list.html"
    context_object_name = "batches"
    paginate_by = 25

    def get_queryset(self):
        qs = ImportBatch.objects.select_related("uploaded_by")
        if self.request.user.is_manager_role:
            qs = qs.filter(uploaded_by=self.request.user)
        return qs


class BulkActionView(ManagerRequiredMixin, View):
    def post(self, request):
        qs = ProjectRepository.visible_to(request.user)
        form = BulkActionForm(request.POST, project_queryset=qs, user=request.user)
        if not form.is_valid():
            messages.error(request, "Không thể xử lý thao tác hàng loạt.")
            return redirect("project_list")

        projects = list(qs.filter(pk__in=form.cleaned_data["project_ids"]))
        action = form.cleaned_data["action"]
        if action == BulkActionForm.ACTION_ASSIGN:
            count = ProjectService.assign(
                projects,
                form.cleaned_data["employee"],
                request.user,
                request=request,
                deadline_at=form.cleaned_data.get("deadline_at"),
                priority=form.cleaned_data.get("priority") or None,
                note=form.cleaned_data.get("note") or "",
                notify=form.cleaned_data.get("notify"),
            )
        elif action == BulkActionForm.ACTION_ASSIGN_MANAGER:
            count = ProjectService.assign_manager(
                projects,
                form.cleaned_data["manager"],
                request.user,
                request=request,
                notify=form.cleaned_data.get("notify"),
            )
        elif action == BulkActionForm.ACTION_MARK_PROFIT:
            for project in projects:
                ProjectService.update_result(project, Project.Result.PROFIT, request.user, request=request)
            count = len(projects)
        elif action == BulkActionForm.ACTION_MARK_LOSS:
            for project in projects:
                ProjectService.update_result(project, Project.Result.LOSS, request.user, request=request)
            count = len(projects)
        elif action == BulkActionForm.ACTION_CHANGE_PROJECT_STATE:
            for project in projects:
                project.project_state = form.cleaned_data["project_state"]
                project.save(update_fields=["project_state", "updated_at"])
                log_activity(
                    request.user,
                    ActivityLog.Action.PROJECT_UPDATED,
                    f"Đã đổi trạng thái dự án thành {project.get_project_state_display()}",
                    project=project,
                    request=request,
                )
            count = len(projects)
        elif action == BulkActionForm.ACTION_CHANGE_STATUS:
            for project in projects:
                ProjectService.update_status(project, form.cleaned_data["status"], request.user, request=request)
            count = len(projects)
        else:
            count = ProjectService.soft_delete(projects, request.user, request=request)

        log_activity(
            request.user,
            ActivityLog.Action.BULK_ACTION,
            f"Processed bulk action {action}",
            metadata={"action": action, "count": count},
            request=request,
        )
        messages.success(request, f"Đã áp dụng thao tác cho {count} dự án.")
        return redirect("project_list")


class AssignProjectsView(ManagerRequiredMixin, View):
    def post(self, request):
        form = AssignmentForm(request.POST, user=request.user)
        if not form.is_valid():
            messages.error(request, "Không thể phân công dự án.")
            return redirect(request.META.get("HTTP_REFERER", "project_list"))
        projects = list(ProjectRepository.visible_to(request.user).filter(pk__in=form.cleaned_data["project_ids"]))
        count = ProjectService.assign(
            projects,
            form.cleaned_data["employee"],
            request.user,
            request=request,
            deadline_at=form.cleaned_data.get("deadline_at"),
            priority=form.cleaned_data.get("priority") or None,
            note=form.cleaned_data.get("note") or "",
            notify=form.cleaned_data.get("notify"),
        )
        messages.success(request, f"Đã giao {count} dự án.")
        if count == 1:
            return redirect(projects[0].get_absolute_url())
        return redirect("project_list")


class ProjectStatusUpdateView(LoginRequiredMixin, View):
    def post(self, request, pk):
        project = get_object_or_404(ProjectRepository.visible_to(request.user), pk=pk)
        form = QuickStatusForm(request.POST, staff_only=not request.user.can_manage_projects)
        if not form.is_valid():
            messages.error(request, "Trạng thái không hợp lệ.")
            return redirect(project.get_absolute_url())
        ProjectService.update_status(project, form.cleaned_data["status"], request.user, request=request)
        messages.success(request, "Đã cập nhật trạng thái.")
        return redirect(project.get_absolute_url())


class ProjectStateUpdateView(LoginRequiredMixin, View):
    def post(self, request, pk):
        project = get_object_or_404(ProjectRepository.visible_to(request.user), pk=pk)
        form = QuickProjectStateForm(request.POST)
        if not form.is_valid():
            messages.error(request, "Trạng thái dự án không hợp lệ.")
            return redirect(project.get_absolute_url())
        project.project_state = form.cleaned_data["project_state"]
        project.save(update_fields=["project_state", "updated_at"])
        log_activity(
            request.user,
            ActivityLog.Action.PROJECT_UPDATED,
            f"Đã đổi trạng thái dự án thành {project.get_project_state_display()}",
            project=project,
            request=request,
        )
        messages.success(request, "Đã cập nhật trạng thái dự án.")
        if not request.user.can_manage_projects:
            NotificationService.notify_managers(
                actor=request.user,
                project=project,
                title=f"{request.user} cập nhật trạng thái dự án",
                message=f"{request.user} đã cập nhật trạng thái dự án “{project.project_name}” thành {project.get_project_state_display()}.",
                notification_type=Notification.Type.STATUS_UPDATED,
            )
        return redirect(project.get_absolute_url())


class ProjectProgressUpdateView(LoginRequiredMixin, View):
    def post(self, request, pk):
        project = get_object_or_404(ProjectRepository.visible_to(request.user), pk=pk)
        if not request.user.can_manage_projects and project.current_employee_id != request.user.pk:
            return JsonResponse({"error": "Không có quyền cập nhật tiến trình"}, status=403)
        form = ProgressUpdateForm(request.POST)
        if not form.is_valid():
            messages.error(request, "Không thể cập nhật tiến trình.")
            return redirect(project.get_absolute_url())
        ProgressService.add_progress(
            project,
            request.user,
            form.cleaned_data["progress_percent"],
            form.cleaned_data["status_note"],
            form.cleaned_data.get("blocker_note") or "",
            request=request,
            registration_success_link=form.cleaned_data.get("registration_success_link") or "",
            login_link=form.cleaned_data.get("login_link") or "",
        )
        messages.success(request, "Đã cập nhật tiến trình.")
        return redirect(project.get_absolute_url())


class TaskListView(LoginRequiredMixin, ListView):
    model = Task
    template_name = "workflow/task_list.html"
    context_object_name = "tasks"
    paginate_by = 20

    def get_queryset(self):
        qs = TaskRepository.visible_to(self.request.user)
        return TaskRepository.search_and_filter(qs, self.request.GET)

    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)
        context["statuses"] = Task.Status.choices
        context["priorities"] = Task.Priority.choices
        context["employees"] = scoped_staff_queryset(self.request.user)
        return context


class TaskDetailView(LoginRequiredMixin, DetailView):
    model = Task
    template_name = "workflow/task_detail.html"
    context_object_name = "task"

    def get_queryset(self):
        return TaskRepository.visible_to(self.request.user).prefetch_related("attachments", "progress_updates")

    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)
        context["status_form"] = StaffTaskUpdateForm(initial={"status": self.object.status})
        context["progress_form"] = TaskProgressUpdateForm()
        return context


class TaskCreateView(ManagerRequiredMixin, CreateView):
    model = Task
    form_class = TaskForm
    template_name = "workflow/task_form.html"

    def get_form_kwargs(self):
        kwargs = super().get_form_kwargs()
        kwargs["user"] = self.request.user
        return kwargs

    def form_valid(self, form):
        files = self.request.FILES.getlist("attachments")
        self.object = TaskService.create_task(form, self.request.user, files=files, request=self.request)
        messages.success(self.request, "Đã giao nhiệm vụ.")
        return redirect(self.object.get_absolute_url())


class TaskUpdateView(LoginRequiredMixin, UpdateView):
    model = Task
    template_name = "workflow/task_form.html"

    def get_queryset(self):
        return TaskRepository.visible_to(self.request.user)

    def get_form_class(self):
        return TaskForm if self.request.user.can_manage_projects else StaffTaskUpdateForm

    def get_form_kwargs(self):
        kwargs = super().get_form_kwargs()
        if self.request.user.can_manage_projects:
            kwargs["user"] = self.request.user
        return kwargs

    def form_valid(self, form):
        if self.request.user.can_manage_projects:
            files = self.request.FILES.getlist("attachments")
            self.object = TaskService.update_task(self.object, form, self.request.user, files=files, request=self.request)
        else:
            task = get_object_or_404(TaskRepository.visible_to(self.request.user), pk=self.object.pk)
            TaskService.update_status(task, form.cleaned_data["status"], self.request.user, request=self.request)
            self.object = task
        messages.success(self.request, "Đã cập nhật nhiệm vụ.")
        return redirect(self.object.get_absolute_url())


class TaskDeleteView(ManagerRequiredMixin, View):
    def post(self, request, pk):
        task = get_object_or_404(TaskRepository.visible_to(request.user), pk=pk)
        task.soft_delete(user=request.user)
        log_activity(
            request.user,
            ActivityLog.Action.TASK_UPDATED,
            f"Đã xóa nhiệm vụ {task.title}",
            metadata={"task_id": task.pk},
            request=request,
        )
        messages.success(request, "Đã xóa nhiệm vụ.")
        return redirect("task_list")


class TaskStatusUpdateView(LoginRequiredMixin, View):
    def post(self, request, pk):
        task = get_object_or_404(TaskRepository.visible_to(request.user), pk=pk)
        form = StaffTaskUpdateForm(request.POST)
        if not form.is_valid():
            messages.error(request, "Trạng thái không hợp lệ.")
            return redirect(task.get_absolute_url())
        TaskService.update_status(task, form.cleaned_data["status"], request.user, request=request)
        messages.success(request, "Đã cập nhật trạng thái nhiệm vụ.")
        return redirect(task.get_absolute_url())


class TaskProgressUpdateView(LoginRequiredMixin, View):
    def post(self, request, pk):
        task = get_object_or_404(TaskRepository.visible_to(request.user), pk=pk)
        if not request.user.can_manage_projects and task.assignee_id != request.user.pk:
            return JsonResponse({"error": "Không có quyền cập nhật tiến độ"}, status=403)
        form = TaskProgressUpdateForm(request.POST)
        if not form.is_valid():
            messages.error(request, "Không thể cập nhật tiến độ nhiệm vụ.")
            return redirect(task.get_absolute_url())
        TaskService.add_progress(
            task,
            request.user,
            form.cleaned_data["progress_percent"],
            form.cleaned_data["status_note"],
            form.cleaned_data.get("blocker_note") or "",
            request=request,
        )
        messages.success(request, "Đã cập nhật tiến độ nhiệm vụ.")
        return redirect(task.get_absolute_url())


class ProjectResultUpdateView(LoginRequiredMixin, View):
    def post(self, request, pk):
        project = get_object_or_404(ProjectRepository.visible_to(request.user), pk=pk)
        form = QuickResultForm(request.POST)
        if not form.is_valid():
            messages.error(request, "Kết quả không hợp lệ.")
            return redirect(project.get_absolute_url())
        ProjectService.update_result(project, form.cleaned_data["result"], request.user, request=request)
        messages.success(request, "Đã cập nhật kết quả.")
        return redirect(project.get_absolute_url())


class ImportDetailView(ManagerRequiredMixin, DetailView):
    model = ImportBatch
    template_name = "workflow/import_detail.html"

    def get_queryset(self):
        qs = ImportBatch.objects.select_related("uploaded_by")
        if self.request.user.is_manager_role:
            qs = qs.filter(uploaded_by=self.request.user)
        return qs


class ImportDuplicateExportView(ManagerRequiredMixin, View):
    def get(self, request, pk):
        qs = ImportBatch.objects.all()
        if request.user.is_manager_role:
            qs = qs.filter(uploaded_by=request.user)
        batch = get_object_or_404(qs, pk=pk)
        from openpyxl import Workbook

        workbook = Workbook()
        sheet = workbook.active
        sheet.title = "Dong trung"
        sheet.append(["Dòng", "Tên dự án", "Domain", "Nguồn", "Người đang nhận", "Trạng thái hiện tại", "Kết quả hiện tại"])
        for item in batch.duplicate_report:
            sheet.append(
                [
                    item.get("row", ""),
                    excel_safe(item.get("project_name", "")),
                    excel_safe(item.get("project_link", "")),
                    excel_safe(item.get("source", "")),
                    excel_safe(item.get("current_assignee", "")),
                    excel_safe(item.get("current_status", "")),
                    excel_safe(item.get("current_result", "")),
                ]
            )
        buffer = BytesIO()
        workbook.save(buffer)
        buffer.seek(0)
        return FileResponse(buffer, as_attachment=True, filename=f"du-an-trung-{batch.pk}.xlsx")


class ExportProjectsView(LoginRequiredMixin, View):
    def get(self, request):
        qs = ProjectRepository.search_and_filter(ProjectRepository.visible_to(request.user), request.GET)
        workbook = build_projects_workbook(qs)
        buffer = BytesIO()
        workbook.save(buffer)
        buffer.seek(0)
        return FileResponse(buffer, as_attachment=True, filename="projects.xlsx")


class KPIView(ManagerRequiredMixin, TemplateView):
    template_name = "workflow/kpi.html"

    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)
        context["rows"] = ReportService.employee_kpis(self.request.user)
        return context


class ReportView(ManagerRequiredMixin, TemplateView):
    template_name = "workflow/reports.html"

    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)
        qs = ProjectRepository.search_and_filter(ProjectRepository.visible_to(self.request.user), self.request.GET)
        counts = ReportService.dashboard_counts(qs)
        completed_base = counts["completed"] + counts["cancelled"]
        counts["completion_rate"] = round(counts["completed"] / completed_base * 100, 2) if completed_base else 0
        counts["success_rate"] = round(counts["profit"] / counts["completed"] * 100, 2) if counts["completed"] else 0
        context["counts"] = counts
        context["by_status"] = list(qs.values("status").annotate(total=Count("id")))
        context["by_result"] = list(qs.values("result").annotate(total=Count("id")))
        context["by_priority"] = list(qs.values("priority").annotate(total=Count("id")))
        context["by_employee"] = list(qs.values("current_employee__username").annotate(total=Count("id")))
        now = timezone.now()
        active = qs.exclude(status__in=[Project.Status.DONE, Project.Status.CANCELLED])
        context["deadline_summary"] = [
            {"label": "Quá hạn", "total": active.filter(deadline_at__lt=now).count()},
            {"label": "Sắp tới hạn", "total": active.filter(deadline_at__gte=now, deadline_at__lte=now + timezone.timedelta(hours=24)).count()},
            {"label": "Chưa có hạn", "total": active.filter(deadline_at__isnull=True).count()},
            {"label": "Đúng hạn", "total": active.filter(deadline_at__gt=now + timezone.timedelta(hours=24)).count()},
        ]
        return context


class ActivityLogListView(LoginRequiredMixin, ListView):
    model = ActivityLog
    template_name = "workflow/activity_logs.html"
    context_object_name = "logs"
    paginate_by = 50

    def get_queryset(self):
        qs = ActivityLog.objects.select_related("user", "project")
        if self.request.user.is_manager_role:
            user = self.request.user
            visible_project_ids = ProjectRepository.visible_to(user).values_list("pk", flat=True)
            visible_task_ids = TaskRepository.visible_to(user).values_list("pk", flat=True)
            qs = qs.filter(
                Q(user=user)
                | Q(project_id__in=visible_project_ids)
                | Q(metadata__manager_id=user.pk)
                | Q(metadata__task_id__in=visible_task_ids)
            )
        elif not self.request.user.can_manage_projects:
            user = self.request.user
            visible_task_ids = TaskRepository.visible_to(user).values_list("pk", flat=True)
            qs = qs.filter(
                Q(user=user)
                | Q(project__current_employee=user)
                | Q(metadata__employee_id=user.pk)
                | Q(metadata__assignee_id=user.pk)
                | Q(metadata__task_id__in=visible_task_ids)
            )
        action = self.request.GET.get("action")
        if action:
            qs = qs.filter(action=action)
        return qs

    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)
        context["actions"] = ActivityLog.Action.choices
        return context


class NotificationListView(LoginRequiredMixin, ListView):
    model = Notification
    template_name = "workflow/notifications.html"
    context_object_name = "notifications"
    paginate_by = 30

    def get_queryset(self):
        qs = Notification.objects.select_related("actor", "project", "task", "recipient")
        if self.request.user.is_manager_role:
            visible_project_ids = ProjectRepository.visible_to(self.request.user).values_list("pk", flat=True)
            visible_task_ids = TaskRepository.visible_to(self.request.user).values_list("pk", flat=True)
            qs = qs.filter(
                Q(recipient=self.request.user)
                | Q(actor=self.request.user)
                | Q(project_id__in=visible_project_ids)
                | Q(task_id__in=visible_task_ids)
            )
        elif not self.request.user.can_manage_projects:
            qs = qs.filter(recipient=self.request.user)
        status = self.request.GET.get("status")
        notification_type = self.request.GET.get("type")
        if status == "unread":
            qs = qs.filter(is_read=False)
        if notification_type:
            qs = qs.filter(notification_type=notification_type)
        return qs

    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)
        context["notification_types"] = Notification.Type.choices
        return context


class NotificationReadView(LoginRequiredMixin, View):
    def post(self, request, pk):
        if request.user.is_admin_role:
            qs = Notification.objects.all()
        elif request.user.is_manager_role:
            visible_project_ids = ProjectRepository.visible_to(request.user).values_list("pk", flat=True)
            visible_task_ids = TaskRepository.visible_to(request.user).values_list("pk", flat=True)
            qs = Notification.objects.filter(
                Q(recipient=request.user)
                | Q(actor=request.user)
                | Q(project_id__in=visible_project_ids)
                | Q(task_id__in=visible_task_ids)
            )
        else:
            qs = Notification.objects.filter(recipient=request.user)
        notification = get_object_or_404(qs, pk=pk)
        notification.mark_read()
        return redirect(request.META.get("HTTP_REFERER", "notifications"))


class NotificationReadAllView(LoginRequiredMixin, View):
    def post(self, request):
        qs = Notification.objects.filter(is_read=False)
        if request.user.is_manager_role:
            visible_project_ids = ProjectRepository.visible_to(request.user).values_list("pk", flat=True)
            visible_task_ids = TaskRepository.visible_to(request.user).values_list("pk", flat=True)
            qs = qs.filter(
                Q(recipient=request.user)
                | Q(actor=request.user)
                | Q(project_id__in=visible_project_ids)
                | Q(task_id__in=visible_task_ids)
            )
        elif not request.user.can_manage_projects:
            qs = qs.filter(recipient=request.user)
        qs.update(is_read=True, read_at=timezone.now())
        messages.success(request, "Đã đánh dấu tất cả thông báo là đã đọc.")
        return redirect("notifications")


class GeneralSettingsView(ManagerRequiredMixin, TemplateView):
    template_name = "workflow/general_settings.html"

    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)
        settings_obj = TelegramSettings.get_solo()
        context["settings_obj"] = settings_obj
        context["form"] = kwargs.get("form") or GeneralSettingsForm(instance=settings_obj)
        return context

    def post(self, request):
        form = GeneralSettingsForm(request.POST, instance=TelegramSettings.get_solo())
        if form.is_valid():
            form.save()
            messages.success(request, "Đã lưu cài đặt chung.")
            return redirect("general_settings")
        messages.error(request, "Không thể lưu cài đặt chung.")
        return self.render_to_response(self.get_context_data(form=form))


class TelegramSettingsView(LoginRequiredMixin, TemplateView):
    template_name = "workflow/telegram_settings.html"

    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)
        telegram_settings = TelegramSettings.get_solo()
        if not self.request.user.telegram_link_token:
            self.request.user.save(update_fields=["telegram_link_token"])
        context["telegram_settings"] = telegram_settings
        context["settings_form"] = TelegramSettingsForm(instance=telegram_settings)
        context["profile_form"] = TelegramProfileForm(instance=self.request.user)
        context["bot_start_url"] = (
            f"https://t.me/{telegram_settings.bot_username}?start={self.request.user.telegram_link_token}"
            if telegram_settings.bot_username
            else ""
        )
        staff_qs = scoped_staff_queryset(self.request.user)
        if self.request.user.is_admin_role:
            linked_qs = User.objects.exclude(telegram_chat_id="")
        elif self.request.user.is_manager_role:
            linked_qs = staff_qs.exclude(telegram_chat_id="")
        else:
            linked_qs = User.objects.filter(pk=self.request.user.pk).exclude(telegram_chat_id="")
        context["linked_users"] = linked_qs.order_by("username")
        context["unlinked_staff"] = staff_qs.filter(telegram_chat_id="").order_by("username")
        return context


class TelegramSettingsUpdateView(LoginRequiredMixin, View):
    def post(self, request):
        action = request.POST.get("action")
        if action in {"save_bot", "test_bot", "sync_updates"} and not request.user.can_manage_projects:
            messages.error(request, "Bạn không có quyền cấu hình Telegram.")
            return redirect("telegram_settings")

        if action == "save_bot":
            form = TelegramSettingsForm(request.POST, instance=TelegramSettings.get_solo())
            if form.is_valid():
                form.save()
                messages.success(request, "Đã lưu cấu hình Telegram.")
            else:
                messages.error(request, "Không thể lưu cấu hình Telegram.")
            return redirect("telegram_settings")

        if action == "test_bot":
            try:
                bot = TelegramService.test_bot()
            except ValueError as exc:
                messages.error(request, str(exc))
            else:
                messages.success(request, f"Bot Telegram hoạt động: @{bot.get('username', '')}.")
            return redirect("telegram_settings")

        if action == "sync_updates":
            linked = TelegramService.sync_updates()
            settings_obj = TelegramSettings.get_solo()
            if settings_obj.last_error:
                messages.error(request, settings_obj.last_error)
            else:
                names = ", ".join(user.username for user in linked) or "không có tài khoản mới"
                messages.success(request, f"Đã đồng bộ Telegram: {names}.")
            return redirect("telegram_settings")

        if action == "save_profile":
            form = TelegramProfileForm(request.POST, instance=request.user)
            if form.is_valid():
                form.save()
                messages.success(request, "Đã lưu cài đặt Telegram cá nhân.")
            else:
                messages.error(request, "Không thể lưu cài đặt Telegram cá nhân.")
            return redirect("telegram_settings")

        if action == "regenerate_token":
            import secrets

            request.user.telegram_link_token = secrets.token_urlsafe(24)
            request.user.telegram_chat_id = ""
            request.user.telegram_username = ""
            request.user.telegram_enabled = False
            request.user.save(update_fields=["telegram_link_token", "telegram_chat_id", "telegram_username", "telegram_enabled"])
            messages.success(request, "Đã tạo lại mã liên kết Telegram.")
            return redirect("telegram_settings")

        if action == "send_test":
            if not request.user.telegram_chat_id:
                messages.error(request, "Tài khoản của bạn chưa có Telegram chat ID.")
            else:
                try:
                    TelegramService.send_message(request.user.telegram_chat_id, "Tin nhắn thử từ hệ thống QLKH PHULINH.")
                except ValueError as exc:
                    messages.error(request, str(exc))
                else:
                    messages.success(request, "Đã gửi tin nhắn thử qua Telegram.")
            return redirect("telegram_settings")

        messages.error(request, "Thao tác Telegram không hợp lệ.")
        return redirect("telegram_settings")


class UserListView(AdminRequiredMixin, ListView):
    model = User
    template_name = "workflow/user_list.html"
    context_object_name = "users"
    paginate_by = 25

    def get_queryset(self):
        qs = User.objects.order_by("username")
        query = self.request.GET.get("q")
        role = self.request.GET.get("role")
        if query:
            qs = qs.filter(username__icontains=query)
        if role:
            qs = qs.filter(role=role)
        return qs

    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)
        context["roles"] = User.Role.choices
        return context


class UserCreateView(AdminRequiredMixin, CreateView):
    model = User
    form_class = UserCreateForm
    template_name = "workflow/user_form.html"
    success_url = reverse_lazy("user_list")

    def form_valid(self, form):
        messages.success(self.request, "Đã tạo người dùng.")
        return super().form_valid(form)


class UserUpdateView(AdminRequiredMixin, UpdateView):
    model = User
    form_class = UserUpdateForm
    template_name = "workflow/user_form.html"
    success_url = reverse_lazy("user_list")

    def form_valid(self, form):
        messages.success(self.request, "Đã cập nhật người dùng.")
        return super().form_valid(form)


class ProjectListApiView(LoginRequiredMixin, View):
    def get(self, request):
        qs = ProjectRepository.search_and_filter(ProjectRepository.visible_to(request.user), request.GET)
        data = [
            {
                "id": project.pk,
                "project_name": project.project_name,
                "project_link": project.project_link,
                "employee": project.current_employee.username if project.current_employee else None,
                "project_state": project.project_state,
                "status": project.status,
                "result": project.result,
                "created_at": project.created_at.isoformat(),
            }
            for project in qs[:100]
        ]
        return JsonResponse({"results": data})


class ProjectUpdateStatusApiView(LoginRequiredMixin, View):
    def post(self, request, pk):
        project = get_object_or_404(ProjectRepository.visible_to(request.user), pk=pk)
        status = request.POST.get("status")
        if status not in Project.Status.values:
            return JsonResponse({"error": "Trạng thái không hợp lệ"}, status=400)
        if not request.user.can_manage_projects and status not in {
            Project.Status.ASSIGNED,
            Project.Status.WORKING,
            Project.Status.DONE,
        }:
            return JsonResponse({"error": "Không có quyền thực hiện"}, status=403)
        ProjectService.update_status(project, status, request.user, request=request)
        return JsonResponse({"ok": True, "status": project.status})


class ProjectUpdateResultApiView(LoginRequiredMixin, View):
    def post(self, request, pk):
        require_manager(request.user)
        project = get_object_or_404(ProjectRepository.visible_to(request.user), pk=pk)
        result = request.POST.get("result")
        if result not in Project.Result.values:
            return JsonResponse({"error": "Kết quả không hợp lệ"}, status=400)
        ProjectService.update_result(project, result, request.user, request=request)
        return JsonResponse({"ok": True, "result": project.result})
