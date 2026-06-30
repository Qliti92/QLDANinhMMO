from django import forms
from django.contrib.auth import get_user_model
from django.contrib.auth.forms import UserCreationForm
from django.core.validators import URLValidator
from django.core.exceptions import ValidationError as DjangoValidationError

from .models import Project, ProjectProgress, Task, TaskProgress, TelegramSettings

User = get_user_model()


class MultipleFileInput(forms.ClearableFileInput):
    allow_multiple_selected = True


class MultipleFileField(forms.FileField):
    def __init__(self, *args, **kwargs):
        kwargs.setdefault("widget", MultipleFileInput())
        super().__init__(*args, **kwargs)

    def clean(self, data, initial=None):
        if isinstance(data, (list, tuple)):
            return [super(MultipleFileField, self).clean(item, initial) for item in data]
        return super().clean(data, initial)


class ProjectForm(forms.ModelForm):
    class Meta:
        model = Project
        fields = ["project_name", "project_link", "manager", "project_state", "status", "result", "note"]
        labels = {
            "project_name": "Tên dự án",
            "project_link": "Domain dự án",
            "manager": "Quản lý phụ trách",
            "project_state": "Trạng thái dự án",
            "status": "Trạng thái công việc",
            "result": "Kết quả",
            "note": "Ghi chú",
        }
        widgets = {"note": forms.Textarea(attrs={"rows": 4})}

    def __init__(self, *args, **kwargs):
        user = kwargs.pop("user", None)
        super().__init__(*args, **kwargs)
        self.fields["manager"].queryset = manager_queryset()
        if user and user.is_manager_role:
            self.fields.pop("manager")
        apply_bootstrap(self)


class StaffProjectUpdateForm(forms.ModelForm):
    class Meta:
        model = Project
        fields = ["project_state", "status", "result", "note"]
        labels = {"status": "Trạng thái công việc", "note": "Ghi chú"}
        widgets = {"note": forms.Textarea(attrs={"rows": 4})}

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        allowed = [Project.Status.ASSIGNED, Project.Status.WORKING, Project.Status.DONE]
        self.fields["status"].choices = [
            choice for choice in Project.Status.choices if choice[0] in allowed
        ]
        apply_bootstrap(self)


class ImportExcelForm(forms.Form):
    file = forms.FileField(label="Tệp Excel", required=False)
    links = forms.CharField(
        label="Dán link/domain thủ công",
        required=False,
        widget=forms.Textarea(attrs={"rows": 6, "placeholder": "Mỗi dòng một link hoặc domain dự án"}),
    )

    def clean_file(self):
        uploaded = self.cleaned_data.get("file")
        if not uploaded:
            return uploaded
        if not uploaded.name.lower().endswith(".xlsx"):
            raise forms.ValidationError("Chỉ chấp nhận file .xlsx.")
        if uploaded.size > 10 * 1024 * 1024:
            raise forms.ValidationError("Dung lượng file tối đa là 10MB.")
        return uploaded

    def clean(self):
        cleaned = super().clean()
        if not cleaned.get("file") and not cleaned.get("links", "").strip():
            raise forms.ValidationError("Vui lòng tải file Excel hoặc dán link thủ công.")
        return cleaned

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        apply_bootstrap(self)


class AssignmentForm(forms.Form):
    employee = forms.ModelChoiceField(queryset=User.objects.none(), label="Nhân viên")
    project_ids = forms.CharField(widget=forms.HiddenInput)
    deadline_at = forms.DateTimeField(label="Hạn xử lý", required=False, widget=forms.DateTimeInput(attrs={"type": "datetime-local"}))
    priority = forms.ChoiceField(label="Độ ưu tiên", choices=Project.Priority.choices, required=False)
    note = forms.CharField(label="Nội dung giao việc", required=False, widget=forms.Textarea(attrs={"rows": 3}))
    notify = forms.BooleanField(label="Thông báo cho nhân viên", required=False, initial=True)

    def __init__(self, *args, **kwargs):
        user = kwargs.pop("user", None)
        super().__init__(*args, **kwargs)
        self.fields["employee"].queryset = staff_queryset_for(user)
        apply_bootstrap(self)

    def clean_project_ids(self):
        value = self.cleaned_data["project_ids"]
        ids = [item.strip() for item in value.split(",") if item.strip()]
        if not ids:
            raise forms.ValidationError("Vui lòng chọn ít nhất một dự án.")
        return ids


class BulkActionForm(forms.Form):
    ACTION_ASSIGN = "assign"
    ACTION_ASSIGN_MANAGER = "assign_manager"
    ACTION_CHANGE_PROJECT_STATE = "change_project_state"
    ACTION_MARK_PROFIT = "mark_profit"
    ACTION_MARK_LOSS = "mark_loss"
    ACTION_CHANGE_STATUS = "change_status"
    ACTION_DELETE = "delete"

    ACTION_CHOICES = [
        (ACTION_ASSIGN, "Giao nhân viên"),
        (ACTION_ASSIGN_MANAGER, "Giao quản lý"),
        (ACTION_CHANGE_PROJECT_STATE, "Đổi trạng thái dự án"),
        (ACTION_MARK_PROFIT, "Đánh dấu lãi"),
        (ACTION_MARK_LOSS, "Đánh dấu lỗ"),
        (ACTION_CHANGE_STATUS, "Đổi trạng thái công việc"),
        (ACTION_DELETE, "Xóa"),
    ]

    action = forms.ChoiceField(choices=ACTION_CHOICES, label="Hành động")
    project_ids = forms.MultipleChoiceField(required=True)
    employee = forms.ModelChoiceField(queryset=User.objects.none(), required=False, label="Nhân viên")
    manager = forms.ModelChoiceField(queryset=User.objects.none(), required=False, label="Quản lý")
    project_state = forms.ChoiceField(choices=Project.ProjectState.choices, required=False, label="Trạng thái dự án")
    status = forms.ChoiceField(choices=Project.Status.choices, required=False, label="Trạng thái công việc")
    deadline_at = forms.DateTimeField(label="Hạn xử lý", required=False, widget=forms.DateTimeInput(attrs={"type": "datetime-local"}))
    priority = forms.ChoiceField(label="Độ ưu tiên", choices=Project.Priority.choices, required=False)
    note = forms.CharField(label="Nội dung giao việc", required=False)
    notify = forms.BooleanField(label="Thông báo cho nhân viên", required=False, initial=True)

    def __init__(self, *args, **kwargs):
        project_queryset = kwargs.pop("project_queryset", Project.objects.none())
        user = kwargs.pop("user", None)
        super().__init__(*args, **kwargs)
        self.fields["project_ids"].choices = [(str(project.pk), project.project_name) for project in project_queryset]
        self.fields["employee"].queryset = staff_queryset_for(user)
        self.fields["manager"].queryset = manager_queryset() if user and user.is_admin_role else User.objects.none()

    def clean(self):
        cleaned = super().clean()
        action = cleaned.get("action")
        if action == self.ACTION_ASSIGN and not cleaned.get("employee"):
            self.add_error("employee", "Vui lòng chọn nhân viên để giao việc.")
        if action == self.ACTION_ASSIGN_MANAGER and not cleaned.get("manager"):
            self.add_error("manager", "Vui lòng chọn quản lý phụ trách.")
        if action == self.ACTION_CHANGE_PROJECT_STATE and not cleaned.get("project_state"):
            self.add_error("project_state", "Vui lòng chọn trạng thái dự án.")
        if action == self.ACTION_CHANGE_STATUS and not cleaned.get("status"):
            self.add_error("status", "Vui lòng chọn trạng thái công việc.")
        return cleaned


class QuickProjectStateForm(forms.Form):
    project_state = forms.ChoiceField(choices=Project.ProjectState.choices, label="Trạng thái dự án")

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        apply_bootstrap(self)


class QuickStatusForm(forms.Form):
    status = forms.ChoiceField(choices=Project.Status.choices, label="Trạng thái công việc")

    def __init__(self, *args, **kwargs):
        staff_only = kwargs.pop("staff_only", False)
        super().__init__(*args, **kwargs)
        if staff_only:
            allowed = {Project.Status.ASSIGNED, Project.Status.WORKING, Project.Status.DONE}
            self.fields["status"].choices = [
                choice for choice in Project.Status.choices if choice[0] in allowed
            ]
        apply_bootstrap(self)


class QuickResultForm(forms.Form):
    result = forms.ChoiceField(choices=Project.Result.choices, label="Kết quả")

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        apply_bootstrap(self)


class QuickProjectUpdateForm(forms.Form):
    project_state = forms.ChoiceField(choices=Project.ProjectState.choices, label="Trạng thái dự án")
    status = forms.ChoiceField(choices=Project.Status.choices, label="Trạng thái công việc")
    result = forms.ChoiceField(choices=Project.Result.choices, label="Kết quả")

    def __init__(self, *args, **kwargs):
        staff_only = kwargs.pop("staff_only", False)
        super().__init__(*args, **kwargs)
        if staff_only:
            allowed = {Project.Status.ASSIGNED, Project.Status.WORKING, Project.Status.DONE}
            self.fields["status"].choices = [
                choice for choice in Project.Status.choices if choice[0] in allowed
            ]
        apply_bootstrap(self)


class UserCreateForm(UserCreationForm):
    class Meta(UserCreationForm.Meta):
        model = User
        fields = ("username", "email", "role", "manager", "is_active")
        labels = {
            "username": "Tên đăng nhập",
            "email": "Thư điện tử",
            "role": "Vai trò",
            "manager": "Quản lý trực tiếp",
            "is_active": "Đang hoạt động",
        }
        help_texts = {
            "username": "",
            "email": "",
            "role": "",
            "manager": "Chọn khi tài khoản là nhân viên.",
            "is_active": "",
        }

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self.fields["password1"].label = "Mật khẩu"
        self.fields["password2"].label = "Nhập lại mật khẩu"
        self.fields["password1"].help_text = ""
        self.fields["password2"].help_text = ""
        self.fields["manager"].queryset = manager_queryset()
        apply_bootstrap(self)

    def clean(self):
        cleaned = super().clean()
        if cleaned.get("role") != User.Role.STAFF:
            cleaned["manager"] = None
        return cleaned


class UserUpdateForm(forms.ModelForm):
    class Meta:
        model = User
        fields = ("username", "email", "role", "manager", "is_active", "is_staff")
        labels = {
            "username": "Tên đăng nhập",
            "email": "Thư điện tử",
            "role": "Vai trò",
            "manager": "Quản lý trực tiếp",
            "is_active": "Đang hoạt động",
            "is_staff": "Cho phép vào Django admin",
        }
        help_texts = {
            "username": "",
            "email": "",
            "role": "",
            "manager": "Chọn khi tài khoản là nhân viên.",
            "is_active": "",
            "is_staff": "",
        }

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self.fields["manager"].queryset = manager_queryset().exclude(pk=getattr(self.instance, "pk", None))
        apply_bootstrap(self)

    def clean(self):
        cleaned = super().clean()
        if cleaned.get("role") != User.Role.STAFF:
            cleaned["manager"] = None
        return cleaned


class TelegramSettingsForm(forms.ModelForm):
    class Meta:
        model = TelegramSettings
        fields = ("enabled", "bot_token", "bot_username")
        labels = {
            "enabled": "Bật gửi thông báo Telegram",
            "bot_token": "Bot token",
            "bot_username": "Username của bot",
        }
        widgets = {
            "bot_token": forms.PasswordInput(render_value=True),
        }

    def clean_bot_username(self):
        value = self.cleaned_data.get("bot_username", "").strip()
        return value[1:] if value.startswith("@") else value

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self.fields["bot_token"].help_text = "Lấy token từ @BotFather. Token chỉ hiển thị cho admin/quản lý."
        self.fields["bot_username"].help_text = "Ví dụ: ten_bot_cua_ban_bot, không bắt buộc nhập dấu @."
        apply_bootstrap(self)


class GeneralSettingsForm(forms.ModelForm):
    class Meta:
        model = TelegramSettings
        fields = ("show_employee_ranking_to_staff", "notification_template")
        labels = {
            "show_employee_ranking_to_staff": "Hiển thị bảng xếp hạng cho nhân viên",
            "notification_template": "Mẫu nội dung thông báo Telegram",
        }
        widgets = {
            "notification_template": forms.Textarea(attrs={"rows": 7}),
        }

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        apply_bootstrap(self)


class TelegramProfileForm(forms.ModelForm):
    class Meta:
        model = User
        fields = ("telegram_enabled", "telegram_chat_id")
        labels = {
            "telegram_enabled": "Nhận thông báo qua Telegram",
            "telegram_chat_id": "Telegram chat ID",
        }

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self.fields["telegram_chat_id"].required = False
        self.fields["telegram_chat_id"].help_text = "Có thể để trống nếu bạn liên kết bằng nút /start trong Telegram."
        apply_bootstrap(self)


def apply_bootstrap(form):
    for field in form.fields.values():
        widget = field.widget
        if isinstance(widget, forms.CheckboxInput):
            widget.attrs.setdefault("class", "form-check-input")
        elif isinstance(widget, forms.FileInput):
            widget.attrs.setdefault("class", "form-control")
        elif isinstance(widget, forms.Select):
            widget.attrs.setdefault("class", "form-select")
        else:
            widget.attrs.setdefault("class", "form-control")


def manager_queryset():
    return User.objects.filter(role=User.Role.MANAGER, is_active=True)


def staff_queryset_for(user):
    qs = User.objects.filter(role=User.Role.STAFF, is_active=True)
    if user and user.is_manager_role:
        return qs.filter(manager=user)
    return qs


class ProgressUpdateForm(forms.ModelForm):
    STAGE_CHOICES = [
        ("PENDING_REVIEW", "Chờ Duyệt"),
        ("REGISTERED_SUCCESS", "ĐK Thành Công"),
        ("CAMP_SET", "Đã Set Camp"),
        ("SPENT", "Đã Chi Tiêu"),
    ]
    STAGE_PROGRESS = {
        "PENDING_REVIEW": 25,
        "REGISTERED_SUCCESS": 50,
        "CAMP_SET": 75,
        "SPENT": 100,
    }

    progress_stage = forms.ChoiceField(choices=STAGE_CHOICES, label="Tiến trình")
    registration_success_link = forms.CharField(
        label="Link ĐK thành công",
        required=False,
        widget=forms.URLInput(attrs={"placeholder": "https://example.com/..."}),
    )

    class Meta:
        model = ProjectProgress
        fields = ["blocker_note"]
        labels = {
            "progress_percent": "Tiến trình (%)",
            "status_note": "Nội dung cập nhật",
            "blocker_note": "Vướng mắc",
        }
        widgets = {
            "progress_percent": forms.NumberInput(attrs={"min": 0, "max": 100, "step": 5}),
            "status_note": forms.Textarea(attrs={"rows": 3}),
            "blocker_note": forms.Textarea(attrs={"rows": 2}),
        }

    def clean(self):
        cleaned = super().clean()
        stage = cleaned.get("progress_stage")
        if stage:
            cleaned["progress_percent"] = self.STAGE_PROGRESS[stage]
            cleaned["status_note"] = dict(self.STAGE_CHOICES)[stage]
        link = (cleaned.get("registration_success_link") or "").strip()
        if stage == "REGISTERED_SUCCESS":
            if not link:
                self.add_error("registration_success_link", "Vui lòng nhập link khi cập nhật ĐK Thành Công.")
            else:
                if "://" not in link:
                    link = f"https://{link}"
                try:
                    URLValidator()(link)
                except DjangoValidationError:
                    self.add_error("registration_success_link", "Link không hợp lệ.")
                else:
                    cleaned["registration_success_link"] = link
        else:
            cleaned["registration_success_link"] = ""
        return cleaned

    def clean_progress_percent(self):
        value = self.cleaned_data["progress_percent"]
        if value < 0 or value > 100:
            raise forms.ValidationError("Tiến trình phải nằm trong khoảng 0-100.")
        return value

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        apply_bootstrap(self)


class TaskForm(forms.ModelForm):
    attachments = MultipleFileField(
        label="File đính kèm",
        required=False,
    )

    class Meta:
        model = Task
        fields = ["title", "description", "assignee", "priority", "deadline_at", "status"]
        labels = {
            "title": "Tiêu đề nhiệm vụ",
            "description": "Mô tả",
            "assignee": "Nhân viên nhận",
            "priority": "Độ ưu tiên",
            "deadline_at": "Deadline",
            "status": "Trạng thái",
        }
        widgets = {
            "description": forms.Textarea(attrs={"rows": 5}),
            "deadline_at": forms.DateTimeInput(attrs={"type": "datetime-local"}),
        }

    def __init__(self, *args, **kwargs):
        user = kwargs.pop("user", None)
        super().__init__(*args, **kwargs)
        self.fields["assignee"].queryset = staff_queryset_for(user)
        apply_bootstrap(self)


class StaffTaskUpdateForm(forms.ModelForm):
    class Meta:
        model = Task
        fields = ["status"]
        labels = {"status": "Trạng thái"}

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        allowed = [Task.Status.NEW, Task.Status.WORKING, Task.Status.REVIEW, Task.Status.DONE]
        self.fields["status"].choices = [choice for choice in Task.Status.choices if choice[0] in allowed]
        apply_bootstrap(self)


class TaskProgressUpdateForm(forms.ModelForm):
    class Meta:
        model = TaskProgress
        fields = ["progress_percent", "status_note", "blocker_note"]
        labels = {
            "progress_percent": "Tiến độ (%)",
            "status_note": "Nội dung cập nhật",
            "blocker_note": "Vướng mắc",
        }
        widgets = {
            "progress_percent": forms.NumberInput(attrs={"min": 0, "max": 100, "step": 5}),
            "status_note": forms.Textarea(attrs={"rows": 3}),
            "blocker_note": forms.Textarea(attrs={"rows": 2}),
        }

    def clean_progress_percent(self):
        value = self.cleaned_data["progress_percent"]
        if value < 0 or value > 100:
            raise forms.ValidationError("Tiến độ phải nằm trong khoảng 0-100.")
        return value

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        apply_bootstrap(self)
