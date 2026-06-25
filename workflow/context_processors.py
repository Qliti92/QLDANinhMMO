from .models import Notification


def notifications(request):
    if not request.user.is_authenticated:
        return {}
    qs = Notification.objects.select_related("project", "task").filter(recipient=request.user)
    return {
        "unread_notifications_count": qs.filter(is_read=False).count(),
        "latest_notifications": qs[:10],
    }
