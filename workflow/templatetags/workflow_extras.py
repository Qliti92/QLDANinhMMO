from django import template

register = template.Library()

STATUS_BADGES = {
    "NEW": "status-badge status-new",
    "ASSIGNED": "status-badge status-assigned",
    "WORKING": "status-badge status-working",
    "DONE": "status-badge status-done",
    "CANCELLED": "status-badge status-cancelled",
}

RESULT_BADGES = {
    "PENDING": "status-badge result-pending",
    "PROFIT": "status-badge result-profit",
    "LOSS": "status-badge result-loss",
}

PROJECT_STATE_BADGES = {
    "ACTIVE": "status-badge project-state-active",
    "KEY_BANNED": "status-badge project-state-key-banned",
    "AF_LOCKED": "status-badge project-state-af-locked",
    "PAUSED": "status-badge project-state-paused",
}

STATUS_LABELS = {
    "NEW": "Mới",
    "ASSIGNED": "Đã giao",
    "WORKING": "Đang làm",
    "DONE": "Hoàn thành",
    "CANCELLED": "Đã hủy",
    "REVIEW": "Chờ duyệt",
    "OVERDUE": "Quá hạn",
}

RESULT_LABELS = {
    "PENDING": "Chờ duyệt",
    "PROFIT": "Lãi",
    "LOSS": "Lỗ",
}

PROJECT_STATE_LABELS = {
    "ACTIVE": "Hoạt động",
    "KEY_BANNED": "Cấm key",
    "AF_LOCKED": "Khoá Af",
    "PAUSED": "Tạm dừng",
}

PRIORITY_LABELS = {
    "LOW": "Thấp",
    "NORMAL": "Bình thường",
    "HIGH": "Cao",
    "URGENT": "Khẩn cấp",
}

ROLE_LABELS = {
    "ADMIN": "Quản trị",
    "MANAGER": "Quản lý",
    "STAFF": "Nhân viên",
}

ACTION_LABELS = {
    "PROJECT_CREATED": "Tạo dự án",
    "PROJECT_UPDATED": "Cập nhật dự án",
    "PROJECT_DELETED": "Xóa dự án",
    "PROJECT_ASSIGNED": "Giao dự án",
    "STATUS_CHANGED": "Đổi trạng thái",
    "RESULT_UPDATED": "Cập nhật kết quả",
    "PROJECT_IMPORTED": "Nhập dự án",
    "BULK_ACTION": "Thao tác hàng loạt",
}

COUNT_LABELS = {
    "total": "Tổng dự án",
    "new": "Mới",
    "assigned": "Đã giao",
    "working": "Đang làm",
    "completed": "Hoàn thành",
    "cancelled": "Đã hủy",
    "profit": "Lãi",
    "loss": "Lỗ",
    "pending_result": "Chờ duyệt",
    "overdue": "Quá hạn",
    "due_soon": "Sắp tới hạn",
    "no_deadline": "Chưa có hạn",
    "high_priority": "Ưu tiên cao",
    "urgent_priority": "Khẩn cấp",
    "updated_today": "Cập nhật hôm nay",
    "avg_progress": "Tiến trình TB",
    "completion_rate": "Tỷ lệ hoàn thành",
    "success_rate": "Tỷ lệ thành công",
}


@register.filter
def status_label(value):
    return STATUS_LABELS.get(value, value)


@register.filter
def result_label(value):
    return RESULT_LABELS.get(value, value)


@register.filter
def project_state_label(value):
    return PROJECT_STATE_LABELS.get(value, value)


@register.filter
def role_label(value):
    return ROLE_LABELS.get(value, value)


@register.filter
def priority_label(value):
    return PRIORITY_LABELS.get(value, value)


@register.filter
def action_label(value):
    return ACTION_LABELS.get(value, value)


@register.filter
def count_label(value):
    return COUNT_LABELS.get(value, value)


@register.filter
def status_badge(value):
    return STATUS_BADGES.get(value, "text-bg-secondary")


@register.filter
def result_badge(value):
    return RESULT_BADGES.get(value, "text-bg-light")


@register.filter
def project_state_badge(value):
    return PROJECT_STATE_BADGES.get(value, "text-bg-secondary")


@register.filter
def priority_badge(value):
    return {
        "LOW": "priority-badge priority-low",
        "NORMAL": "priority-badge priority-normal",
        "HIGH": "priority-badge priority-high",
        "URGENT": "priority-badge priority-urgent",
    }.get(value, "priority-badge priority-normal")


@register.filter
def deadline_badge(project):
    if not getattr(project, "deadline_at", None):
        return "deadline-badge deadline-none"
    if project.is_overdue:
        return "deadline-badge deadline-overdue"
    if project.is_due_soon:
        return "deadline-badge deadline-soon"
    return "deadline-badge deadline-ok"


@register.filter
def deadline_label(project):
    if not getattr(project, "deadline_at", None):
        return "Chưa có hạn"
    if project.is_overdue:
        return "Quá hạn"
    if project.is_due_soon:
        return "Sắp tới hạn"
    return "Đúng hạn"


@register.filter
def progress_bar_class(value):
    value = value or 0
    if value <= 30:
        return "bg-danger"
    if value <= 70:
        return "bg-warning"
    if value < 100:
        return "bg-info"
    return "bg-success"


@register.filter
def get_item(dictionary, key):
    return dictionary.get(key, "")


@register.filter
def source_label(value):
    return {
        "file": "Trong file nhập",
        "database": "Đã có trong hệ thống",
    }.get(value, value or "-")


@register.simple_tag(takes_context=True)
def querystring(context, **kwargs):
    query = context["request"].GET.copy()
    for key, value in kwargs.items():
        if value is None:
            query.pop(key, None)
        else:
            query[key] = value
    return query.urlencode()
