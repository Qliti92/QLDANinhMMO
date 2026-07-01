from django.contrib import admin
from django.contrib.auth.admin import UserAdmin

from .models import ActivityLog, Assignment, ImportBatch, Notification, Project, ProjectProgress, Task, TaskAttachment, TaskProgress, TelegramSettings, User


@admin.register(User)
class CustomUserAdmin(UserAdmin):
    fieldsets = UserAdmin.fieldsets + (
        ("Quy trình", {"fields": ("role", "manager")}),
        ("Telegram", {"fields": ("telegram_enabled", "telegram_chat_id", "telegram_username", "telegram_link_token")}),
    )
    readonly_fields = ("telegram_link_token",)
    list_display = ("username", "email", "role", "manager", "telegram_enabled", "telegram_chat_id", "is_active", "is_staff")
    list_filter = ("role", "manager", "telegram_enabled", "is_active", "is_staff")


class AssignmentInline(admin.TabularInline):
    model = Assignment
    extra = 0
    readonly_fields = ("assigned_at",)


@admin.register(Project)
class ProjectAdmin(admin.ModelAdmin):
    list_display = ("project_name", "manager", "status", "result", "current_employee", "created_at", "deleted_at")
    list_filter = ("manager", "status", "result", "current_employee")
    search_fields = ("project_name", "project_link")
    readonly_fields = ("created_at", "updated_at", "completed_at", "result_updated_at")
    inlines = [AssignmentInline]


@admin.register(Assignment)
class AssignmentAdmin(admin.ModelAdmin):
    list_display = ("project", "employee", "assigned_by", "assigned_at")
    list_filter = ("employee", "assigned_by")
    search_fields = ("project__project_name", "employee__username")


@admin.register(ActivityLog)
class ActivityLogAdmin(admin.ModelAdmin):
    list_display = ("action", "user", "project", "created_at")
    list_filter = ("action", "created_at")
    search_fields = ("description", "project__project_name", "user__username")
    readonly_fields = ("created_at",)


@admin.register(ImportBatch)
class ImportBatchAdmin(admin.ModelAdmin):
    list_display = ("original_filename", "uploaded_by", "total_rows", "imported_rows", "duplicate_rows", "invalid_rows", "created_at")
    readonly_fields = ("created_at",)


@admin.register(Notification)
class NotificationAdmin(admin.ModelAdmin):
    list_display = ("title", "recipient", "notification_type", "telegram_status", "is_read", "created_at")
    list_filter = ("notification_type", "telegram_status", "is_read")
    search_fields = ("title", "message", "recipient__username")


@admin.register(ProjectProgress)
class ProjectProgressAdmin(admin.ModelAdmin):
    list_display = ("project", "user", "progress_percent", "created_at")
    list_filter = ("user", "created_at")
    search_fields = ("project__project_name", "user__username", "status_note")


class TaskAttachmentInline(admin.TabularInline):
    model = TaskAttachment
    extra = 0
    readonly_fields = ("created_at",)


@admin.register(Task)
class TaskAdmin(admin.ModelAdmin):
    list_display = ("title", "manager", "assignee", "assigned_by", "status", "priority", "deadline_at", "created_at")
    list_filter = ("manager", "status", "priority", "assignee", "assigned_by")
    search_fields = ("title", "description", "manager__username", "assignee__username")
    readonly_fields = ("created_at", "updated_at", "completed_at")
    inlines = [TaskAttachmentInline]


@admin.register(TaskProgress)
class TaskProgressAdmin(admin.ModelAdmin):
    list_display = ("task", "user", "progress_percent", "created_at")
    list_filter = ("user", "created_at")
    search_fields = ("task__title", "user__username", "status_note")


@admin.register(TelegramSettings)
class TelegramSettingsAdmin(admin.ModelAdmin):
    list_display = ("enabled", "bot_username", "show_employee_ranking_to_staff", "last_sync_at", "updated_at")
    readonly_fields = ("last_update_id", "last_sync_at", "last_error", "updated_at")
