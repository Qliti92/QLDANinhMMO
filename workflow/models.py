from django.conf import settings
from django.contrib.auth.models import AbstractUser
from django.db import models
from django.urls import reverse
from django.utils import timezone
import secrets


class User(AbstractUser):
    class Role(models.TextChoices):
        ADMIN = "ADMIN", "Quản trị"
        MANAGER = "MANAGER", "Quản lý"
        STAFF = "STAFF", "Nhân viên"

    role = models.CharField(max_length=20, choices=Role.choices, default=Role.STAFF)
    telegram_chat_id = models.CharField(max_length=64, blank=True)
    telegram_username = models.CharField(max_length=64, blank=True)
    telegram_enabled = models.BooleanField(default=False)
    telegram_link_token = models.CharField(max_length=64, unique=True, blank=True, null=True)
    manager = models.ForeignKey(
        "self",
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="managed_staff",
        limit_choices_to={"role": Role.MANAGER},
    )
    created_at = models.DateTimeField(auto_now_add=True)

    def save(self, *args, **kwargs):
        if not self.telegram_link_token:
            self.telegram_link_token = secrets.token_urlsafe(24)
            update_fields = kwargs.get("update_fields")
            if update_fields is not None:
                kwargs["update_fields"] = set(update_fields) | {"telegram_link_token"}
        super().save(*args, **kwargs)

    @property
    def is_admin_role(self) -> bool:
        return self.role == self.Role.ADMIN or self.is_superuser

    @property
    def is_manager_role(self) -> bool:
        return self.role == self.Role.MANAGER

    @property
    def can_manage_projects(self) -> bool:
        return self.is_admin_role or self.is_manager_role


class ImportBatch(models.Model):
    uploaded_by = models.ForeignKey(
        settings.AUTH_USER_MODEL, on_delete=models.PROTECT, related_name="import_batches"
    )
    original_filename = models.CharField(max_length=255)
    total_rows = models.PositiveIntegerField(default=0)
    imported_rows = models.PositiveIntegerField(default=0)
    duplicate_rows = models.PositiveIntegerField(default=0)
    invalid_rows = models.PositiveIntegerField(default=0)
    duplicate_report = models.JSONField(default=list, blank=True)
    invalid_report = models.JSONField(default=list, blank=True)
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering = ["-created_at"]

    def __str__(self) -> str:
        return f"Import #{self.pk} - {self.original_filename}"


class ProjectQuerySet(models.QuerySet):
    def active(self):
        return self.filter(deleted_at__isnull=True)


class Project(models.Model):
    class Status(models.TextChoices):
        NEW = "NEW", "Mới"
        ASSIGNED = "ASSIGNED", "Đã giao"
        WORKING = "WORKING", "Đang làm"
        DONE = "DONE", "Hoàn thành"
        CANCELLED = "CANCELLED", "Đã hủy"

    class ProjectState(models.TextChoices):
        ACTIVE = "ACTIVE", "Hoạt động"
        KEY_BANNED = "KEY_BANNED", "Cấm key"
        AF_LOCKED = "AF_LOCKED", "Khoá Af"
        PAUSED = "PAUSED", "Tạm dừng"

    class Result(models.TextChoices):
        PENDING = "PENDING", "Đang làm"
        PROFIT = "PROFIT", "Lãi"
        LOSS = "LOSS", "Lỗ"

    class Priority(models.TextChoices):
        LOW = "LOW", "Thấp"
        NORMAL = "NORMAL", "Bình thường"
        HIGH = "HIGH", "Cao"
        URGENT = "URGENT", "Khẩn cấp"

    project_name = models.CharField(max_length=255)
    project_link = models.URLField(unique=True, max_length=1000)
    project_state = models.CharField(max_length=20, choices=ProjectState.choices, default=ProjectState.ACTIVE)
    status = models.CharField(max_length=20, choices=Status.choices, default=Status.NEW)
    result = models.CharField(max_length=20, choices=Result.choices, default=Result.PENDING)
    priority = models.CharField(max_length=20, choices=Priority.choices, default=Priority.NORMAL)
    deadline_at = models.DateTimeField(null=True, blank=True)
    registration_success_link = models.URLField(blank=True, max_length=1000)
    login_link = models.URLField(blank=True, max_length=1000)
    note = models.TextField(blank=True)
    current_employee = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="current_projects",
    )
    manager = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="managed_projects",
    )
    import_batch = models.ForeignKey(
        ImportBatch,
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="projects",
    )
    created_by = models.ForeignKey(
        settings.AUTH_USER_MODEL, on_delete=models.PROTECT, related_name="created_projects"
    )
    completed_at = models.DateTimeField(null=True, blank=True)
    result_updated_at = models.DateTimeField(null=True, blank=True)
    deleted_at = models.DateTimeField(null=True, blank=True)
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    objects = ProjectQuerySet.as_manager()

    class Meta:
        ordering = ["-created_at"]
        indexes = [
            models.Index(fields=["project_link"], name="wf_pr_link_idx"),
            models.Index(fields=["project_state"], name="wf_pr_state_idx"),
            models.Index(fields=["status"], name="wf_pr_status_idx"),
            models.Index(fields=["result"], name="wf_pr_result_idx"),
            models.Index(fields=["priority"], name="wf_pr_priority_idx"),
            models.Index(fields=["deadline_at"], name="wf_pr_deadline_idx"),
            models.Index(fields=["current_employee"], name="wf_pr_employee_idx"),
            models.Index(fields=["manager"], name="wf_pr_manager_idx"),
            models.Index(fields=["created_at"], name="wf_pr_created_idx"),
        ]

    def __str__(self) -> str:
        return self.project_name

    def get_absolute_url(self):
        return reverse("project_detail", kwargs={"pk": self.pk})

    def soft_delete(self, user=None) -> None:
        self.deleted_at = timezone.now()
        self.save(update_fields=["deleted_at", "updated_at"])

    @property
    def is_overdue(self) -> bool:
        return bool(
            self.deadline_at
            and self.deadline_at < timezone.now()
            and self.status not in {self.Status.DONE, self.Status.CANCELLED}
        )

    @property
    def is_due_soon(self) -> bool:
        if not self.deadline_at or self.status in {self.Status.DONE, self.Status.CANCELLED}:
            return False
        now = timezone.now()
        return now <= self.deadline_at <= now + timezone.timedelta(hours=24)

    @property
    def latest_progress(self):
        return self.progress_updates.order_by("-created_at").first()


class Assignment(models.Model):
    project = models.ForeignKey(Project, on_delete=models.CASCADE, related_name="assignments")
    employee = models.ForeignKey(
        settings.AUTH_USER_MODEL, on_delete=models.PROTECT, related_name="assignments"
    )
    assigned_by = models.ForeignKey(
        settings.AUTH_USER_MODEL, on_delete=models.PROTECT, related_name="assigned_projects"
    )
    note = models.TextField(blank=True)
    deadline_at = models.DateTimeField(null=True, blank=True)
    priority = models.CharField(max_length=20, choices=Project.Priority.choices, default=Project.Priority.NORMAL)
    assigned_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering = ["-assigned_at"]
        indexes = [
            models.Index(fields=["project", "-assigned_at"], name="wf_as_project_assigned_idx"),
            models.Index(fields=["employee"], name="wf_as_employee_idx"),
        ]

    def __str__(self) -> str:
        return f"{self.project} -> {self.employee}"


class ActivityLog(models.Model):
    class Action(models.TextChoices):
        PROJECT_CREATED = "PROJECT_CREATED", "Tạo dự án"
        PROJECT_UPDATED = "PROJECT_UPDATED", "Cập nhật dự án"
        PROJECT_DELETED = "PROJECT_DELETED", "Xóa dự án"
        PROJECT_ASSIGNED = "PROJECT_ASSIGNED", "Giao dự án"
        STATUS_CHANGED = "STATUS_CHANGED", "Đổi trạng thái"
        RESULT_UPDATED = "RESULT_UPDATED", "Cập nhật kết quả"
        PROJECT_IMPORTED = "PROJECT_IMPORTED", "Nhập dự án"
        BULK_ACTION = "BULK_ACTION", "Thao tác hàng loạt"
        PROGRESS_UPDATED = "PROGRESS_UPDATED", "Cập nhật tiến trình"
        DEADLINE_UPDATED = "DEADLINE_UPDATED", "Cập nhật hạn xử lý"
        TASK_CREATED = "TASK_CREATED", "Tạo nhiệm vụ"
        TASK_UPDATED = "TASK_UPDATED", "Cập nhật nhiệm vụ"
        TASK_PROGRESS_UPDATED = "TASK_PROGRESS_UPDATED", "Cập nhật tiến độ nhiệm vụ"

    user = models.ForeignKey(
        settings.AUTH_USER_MODEL, on_delete=models.SET_NULL, null=True, related_name="activity_logs"
    )
    project = models.ForeignKey(
        Project, on_delete=models.SET_NULL, null=True, blank=True, related_name="activity_logs"
    )
    action = models.CharField(max_length=50, choices=Action.choices)
    description = models.TextField()
    metadata = models.JSONField(default=dict, blank=True)
    ip_address = models.GenericIPAddressField(null=True, blank=True)
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering = ["-created_at"]
        indexes = [
            models.Index(fields=["action"], name="wf_ac_action_idx"),
            models.Index(fields=["created_at"], name="wf_ac_created_idx"),
            models.Index(fields=["user"], name="wf_ac_user_idx"),
        ]

    def __str__(self) -> str:
        return f"{self.action} by {self.user}"


class Notification(models.Model):
    class Type(models.TextChoices):
        PROJECT_ASSIGNED = "PROJECT_ASSIGNED", "Được giao dự án"
        TASK_ASSIGNED = "TASK_ASSIGNED", "Được giao nhiệm vụ"
        DEADLINE_UPDATED = "DEADLINE_UPDATED", "Cập nhật hạn xử lý"
        STATUS_UPDATED = "STATUS_UPDATED", "Cập nhật trạng thái"
        RESULT_UPDATED = "RESULT_UPDATED", "Cập nhật kết quả"
        PROJECT_OVERDUE = "PROJECT_OVERDUE", "Quá hạn"
        PROGRESS_UPDATED = "PROGRESS_UPDATED", "Cập nhật tiến trình"
        TASK_PROGRESS_UPDATED = "TASK_PROGRESS_UPDATED", "Cập nhật tiến độ nhiệm vụ"
        SYSTEM = "SYSTEM", "Hệ thống"

    recipient = models.ForeignKey(settings.AUTH_USER_MODEL, on_delete=models.CASCADE, related_name="notifications")
    actor = models.ForeignKey(settings.AUTH_USER_MODEL, on_delete=models.SET_NULL, null=True, blank=True, related_name="sent_notifications")
    project = models.ForeignKey(Project, on_delete=models.SET_NULL, null=True, blank=True, related_name="notifications")
    task = models.ForeignKey("Task", on_delete=models.SET_NULL, null=True, blank=True, related_name="notifications")
    title = models.CharField(max_length=255)
    message = models.TextField()
    notification_type = models.CharField(max_length=50, choices=Type.choices, default=Type.SYSTEM)
    is_read = models.BooleanField(default=False)
    telegram_status = models.CharField(max_length=20, default="PENDING")
    telegram_sent_at = models.DateTimeField(null=True, blank=True)
    telegram_error = models.TextField(blank=True)
    created_at = models.DateTimeField(auto_now_add=True)
    read_at = models.DateTimeField(null=True, blank=True)

    class Meta:
        ordering = ["-created_at"]
        indexes = [
            models.Index(fields=["recipient"], name="wf_nt_recipient_idx"),
            models.Index(fields=["is_read"], name="wf_nt_read_idx"),
            models.Index(fields=["created_at"], name="wf_nt_created_idx"),
            models.Index(fields=["notification_type"], name="wf_nt_type_idx"),
        ]

    def mark_read(self):
        if not self.is_read:
            self.is_read = True
            self.read_at = timezone.now()
            self.save(update_fields=["is_read", "read_at"])


class TelegramSettings(models.Model):
    DEFAULT_NOTIFICATION_TEMPLATE = "🔔 {title}\n\n{message}{object_line}"

    bot_token = models.CharField(max_length=255, blank=True)
    bot_username = models.CharField(max_length=128, blank=True)
    enabled = models.BooleanField(default=False)
    show_employee_ranking_to_staff = models.BooleanField(default=True)
    notification_template = models.TextField(default=DEFAULT_NOTIFICATION_TEMPLATE, blank=True)
    last_update_id = models.BigIntegerField(null=True, blank=True)
    last_sync_at = models.DateTimeField(null=True, blank=True)
    last_error = models.TextField(blank=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        verbose_name = "Telegram settings"
        verbose_name_plural = "Telegram settings"

    def __str__(self) -> str:
        return "Telegram settings"

    @classmethod
    def get_solo(cls):
        obj, _ = cls.objects.get_or_create(pk=1)
        return obj


class ProjectProgress(models.Model):
    project = models.ForeignKey(Project, on_delete=models.CASCADE, related_name="progress_updates")
    user = models.ForeignKey(settings.AUTH_USER_MODEL, on_delete=models.PROTECT, related_name="progress_updates")
    progress_percent = models.PositiveSmallIntegerField(default=0)
    status_note = models.TextField()
    blocker_note = models.TextField(blank=True)
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering = ["-created_at"]
        indexes = [
            models.Index(fields=["project"], name="wf_pg_project_idx"),
            models.Index(fields=["user"], name="wf_pg_user_idx"),
            models.Index(fields=["created_at"], name="wf_pg_created_idx"),
        ]


class TaskQuerySet(models.QuerySet):
    def active(self):
        return self.filter(deleted_at__isnull=True)


class Task(models.Model):
    class Status(models.TextChoices):
        NEW = "NEW", "Mới giao"
        WORKING = "WORKING", "Đang làm"
        REVIEW = "REVIEW", "Chờ duyệt"
        DONE = "DONE", "Hoàn thành"
        OVERDUE = "OVERDUE", "Quá hạn"
        CANCELLED = "CANCELLED", "Đã hủy"

    class Priority(models.TextChoices):
        LOW = "LOW", "Thấp"
        NORMAL = "NORMAL", "Bình thường"
        HIGH = "HIGH", "Cao"
        URGENT = "URGENT", "Khẩn cấp"

    title = models.CharField(max_length=255)
    description = models.TextField()
    assignee = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="assigned_tasks",
    )
    manager = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="managed_tasks",
    )
    assigned_by = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.PROTECT,
        related_name="created_tasks",
    )
    priority = models.CharField(max_length=20, choices=Priority.choices, default=Priority.NORMAL)
    deadline_at = models.DateTimeField(null=True, blank=True)
    status = models.CharField(max_length=20, choices=Status.choices, default=Status.NEW)
    deleted_at = models.DateTimeField(null=True, blank=True)
    completed_at = models.DateTimeField(null=True, blank=True)
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    objects = TaskQuerySet.as_manager()

    class Meta:
        ordering = ["-created_at"]
        indexes = [
            models.Index(fields=["assignee"], name="wf_tk_assignee_idx"),
            models.Index(fields=["manager"], name="wf_tk_manager_idx"),
            models.Index(fields=["assigned_by"], name="wf_tk_assigned_by_idx"),
            models.Index(fields=["status"], name="wf_tk_status_idx"),
            models.Index(fields=["priority"], name="wf_tk_priority_idx"),
            models.Index(fields=["deadline_at"], name="wf_tk_deadline_idx"),
            models.Index(fields=["created_at"], name="wf_tk_created_idx"),
        ]

    def __str__(self) -> str:
        return self.title

    def get_absolute_url(self):
        return reverse("task_detail", kwargs={"pk": self.pk})

    def soft_delete(self, user=None) -> None:
        self.deleted_at = timezone.now()
        self.save(update_fields=["deleted_at", "updated_at"])

    @property
    def is_overdue(self) -> bool:
        return bool(
            self.deadline_at
            and self.deadline_at < timezone.now()
            and self.status not in {self.Status.DONE, self.Status.CANCELLED}
        )

    @property
    def is_due_soon(self) -> bool:
        if not self.deadline_at or self.status in {self.Status.DONE, self.Status.CANCELLED}:
            return False
        now = timezone.now()
        return now <= self.deadline_at <= now + timezone.timedelta(hours=24)

    @property
    def latest_progress(self):
        return self.progress_updates.order_by("-created_at").first()


class TaskAttachment(models.Model):
    task = models.ForeignKey(Task, on_delete=models.CASCADE, related_name="attachments")
    file = models.FileField(upload_to="task_attachments/%Y/%m/")
    original_filename = models.CharField(max_length=255)
    uploaded_by = models.ForeignKey(
        settings.AUTH_USER_MODEL, on_delete=models.PROTECT, related_name="task_attachments"
    )
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering = ["-created_at"]

    def __str__(self) -> str:
        return self.original_filename


class TaskProgress(models.Model):
    task = models.ForeignKey(Task, on_delete=models.CASCADE, related_name="progress_updates")
    user = models.ForeignKey(settings.AUTH_USER_MODEL, on_delete=models.PROTECT, related_name="task_progress_updates")
    progress_percent = models.PositiveSmallIntegerField(default=0)
    status_note = models.TextField()
    blocker_note = models.TextField(blank=True)
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering = ["-created_at"]
        indexes = [
            models.Index(fields=["task"], name="wf_tpg_task_idx"),
            models.Index(fields=["user"], name="wf_tpg_user_idx"),
            models.Index(fields=["created_at"], name="wf_tpg_created_idx"),
        ]
