from io import BytesIO

from django.contrib.auth import get_user_model
from django.test import TestCase
from django.urls import reverse
from openpyxl import Workbook, load_workbook

from .models import ActivityLog, Assignment, Notification, Project, ProjectProgress, Task, TaskProgress, TelegramSettings
from .repositories import ProjectRepository
from .services import ImportService, NotificationService, ProgressService, ProjectService, TaskService, build_projects_workbook

User = get_user_model()


class WorkflowServiceTests(TestCase):
    def setUp(self):
        self.manager = User.objects.create_user("manager", password="pass", role=User.Role.MANAGER)
        self.staff = User.objects.create_user("staff", password="pass", role=User.Role.STAFF)

    def test_assign_updates_current_employee_and_keeps_history(self):
        project = Project.objects.create(
            project_name="A",
            project_link="https://example.com/a",
            created_by=self.manager,
        )

        ProjectService.assign([project], self.staff, self.manager)
        project.refresh_from_db()

        self.assertEqual(project.current_employee, self.staff)
        self.assertEqual(project.status, Project.Status.ASSIGNED)
        self.assertEqual(Assignment.objects.count(), 1)
        self.assertEqual(ActivityLog.objects.filter(action=ActivityLog.Action.PROJECT_ASSIGNED).count(), 1)

    def test_assign_creates_deadline_priority_note_and_notification(self):
        from django.utils import timezone

        project = Project.objects.create(
            project_name="Deadline",
            project_link="https://example.com/deadline",
            created_by=self.manager,
        )
        deadline = timezone.now() + timezone.timedelta(days=1)

        ProjectService.assign(
            [project],
            self.staff,
            self.manager,
            deadline_at=deadline,
            priority=Project.Priority.URGENT,
            note="Lam gap",
            notify=True,
        )
        project.refresh_from_db()
        assignment = Assignment.objects.get(project=project)

        self.assertEqual(project.priority, Project.Priority.URGENT)
        self.assertEqual(project.deadline_at, deadline)
        self.assertEqual(assignment.note, "Lam gap")
        notice = Notification.objects.get(recipient=self.staff, notification_type=Notification.Type.PROJECT_ASSIGNED)
        self.assertIn(self.manager.username, notice.title)
        self.assertIn(project.project_name, notice.message)
        self.assertIn("Khẩn cấp", notice.message)

    def test_staff_progress_creates_update_and_manager_notification(self):
        project = Project.objects.create(
            project_name="Progress",
            project_link="https://example.com/progress",
            created_by=self.manager,
            current_employee=self.staff,
        )

        ProgressService.add_progress(project, self.staff, 45, "Dang xu ly", "Can tai khoan")

        self.assertEqual(ProjectProgress.objects.filter(project=project, progress_percent=45).count(), 1)
        notice = Notification.objects.get(notification_type=Notification.Type.PROGRESS_UPDATED)
        self.assertIn(self.staff.username, notice.title)
        self.assertIn(project.project_name, notice.message)
        self.assertIn("45%", notice.message)

    def test_staff_status_update_notifies_manager(self):
        project = Project.objects.create(
            project_name="Status Update",
            project_link="https://example.com/status-update",
            created_by=self.manager,
            current_employee=self.staff,
            status=Project.Status.ASSIGNED,
        )

        ProjectService.update_status(project, Project.Status.WORKING, self.staff)

        notice = Notification.objects.get(notification_type=Notification.Type.STATUS_UPDATED)
        self.assertEqual(notice.recipient, self.manager)
        self.assertEqual(notice.actor, self.staff)
        self.assertIn(project.project_name, notice.message)
        self.assertFalse(Notification.objects.filter(recipient=self.staff, notification_type=Notification.Type.STATUS_UPDATED).exists())

    def test_task_progress_notification_identifies_actor_and_task(self):
        task = Task.objects.create(
            title="Soạn báo cáo tuần",
            description="Tổng hợp số liệu",
            assignee=self.staff,
            assigned_by=self.manager,
            priority=Task.Priority.HIGH,
        )

        TaskService.add_progress(task, self.staff, 60, "Đã tổng hợp dữ liệu", "Chờ duyệt số liệu")

        self.assertEqual(TaskProgress.objects.filter(task=task, progress_percent=60).count(), 1)
        notice = Notification.objects.get(notification_type=Notification.Type.TASK_PROGRESS_UPDATED)
        self.assertIn(self.staff.username, notice.title)
        self.assertIn(task.title, notice.message)
        self.assertIn("60%", notice.message)
        self.assertIn("Chờ duyệt số liệu", notice.message)

    def test_staff_only_sees_assigned_projects(self):
        assigned = Project.objects.create(
            project_name="Assigned",
            project_link="https://example.com/assigned",
            created_by=self.manager,
            current_employee=self.staff,
        )
        Project.objects.create(
            project_name="Hidden",
            project_link="https://example.com/hidden",
            created_by=self.manager,
        )

        self.assertEqual(list(ProjectRepository.visible_to(self.staff)), [assigned])

    def test_import_counts_database_and_file_duplicates(self):
        Project.objects.create(
            project_name="Existing",
            project_link="https://existing.example.com/path",
            created_by=self.manager,
        )
        workbook = Workbook()
        sheet = workbook.active
        sheet.append(["Project Name", "Project Link"])
        sheet.append(["New", "https://new.example.com/path"])
        sheet.append(["Existing", "https://www.existing.example.com/other-path"])
        sheet.append(["New duplicate", "https://new.example.com/another-path"])
        sheet.append(["Missing link", ""])
        buffer = BytesIO()
        workbook.save(buffer)
        buffer.seek(0)
        buffer.name = "projects.xlsx"

        summary = ImportService.import_xlsx(buffer, self.manager)

        self.assertEqual(summary.batch.total_rows, 4)
        self.assertEqual(summary.batch.imported_rows, 1)
        self.assertEqual(summary.batch.duplicate_rows, 2)
        self.assertEqual(summary.batch.invalid_rows, 1)
        self.assertTrue(Project.objects.filter(project_link="new.example.com").exists())

    def test_import_accepts_link_only_and_generates_domain_project_name(self):
        workbook = Workbook()
        sheet = workbook.active
        sheet.append(["Link"])
        sheet.append(["https://example.com/my-new-project"])
        buffer = BytesIO()
        workbook.save(buffer)
        buffer.seek(0)
        buffer.name = "links.xlsx"

        summary = ImportService.import_xlsx(buffer, self.manager)
        project = summary.imported_projects[0]

        self.assertEqual(summary.batch.imported_rows, 1)
        self.assertEqual(project.project_name, "example.com")
        self.assertEqual(project.project_link, "example.com")

    def test_import_normalizes_domain_variants(self):
        summary = ImportService.import_pasted_links(
            "https://the5ers.com/\nhttps://WWW. the5ers.com/\n[https://the5ers.com/](https://the5ers.com/)",
            self.manager,
        )

        self.assertEqual(summary.batch.imported_rows, 1)
        self.assertEqual(summary.batch.duplicate_rows, 2)
        self.assertEqual(summary.imported_projects[0].project_link, "the5ers.com")

    def test_import_accepts_column_a_without_header(self):
        workbook = Workbook()
        sheet = workbook.active
        sheet.append(["https://headerless.example.com/project"])
        buffer = BytesIO()
        workbook.save(buffer)
        buffer.seek(0)
        buffer.name = "column-a.xlsx"

        summary = ImportService.import_xlsx(buffer, self.manager)
        project = summary.imported_projects[0]

        self.assertEqual(summary.batch.imported_rows, 1)
        self.assertEqual(project.project_name, "headerless.example.com")

    def test_import_accepts_pasted_links(self):
        summary = ImportService.import_pasted_links(
            "https://manual-one.example.com/path\nhttps://manual-two.example.com/path",
            self.manager,
        )

        self.assertEqual(summary.batch.imported_rows, 2)
        self.assertTrue(Project.objects.filter(project_name="manual-one.example.com").exists())

    def test_export_escapes_excel_formula_values(self):
        project = Project.objects.create(
            project_name="=HYPERLINK(\"https://example.com\")",
            project_link="https://example.com/formula",
            created_by=self.manager,
        )

        workbook = build_projects_workbook(Project.objects.filter(pk=project.pk))
        buffer = BytesIO()
        workbook.save(buffer)
        buffer.seek(0)
        exported = load_workbook(buffer, data_only=False)

        self.assertEqual(exported.active["A2"].value, "'=HYPERLINK(\"https://example.com\")")

    def test_import_rejects_too_many_rows(self):
        workbook = Workbook()
        sheet = workbook.active
        sheet.append(["Link"])
        for index in range(ImportService.MAX_ROWS + 1):
            sheet.append([f"https://example.com/{index}"])
        buffer = BytesIO()
        workbook.save(buffer)
        buffer.seek(0)
        buffer.name = "too-many.xlsx"

        with self.assertRaises(ValueError):
            ImportService.import_xlsx(buffer, self.manager)


class WorkflowViewTests(TestCase):
    def setUp(self):
        self.admin = User.objects.create_user(
            "admin",
            password="pass",
            role=User.Role.ADMIN,
            is_staff=True,
            is_superuser=True,
        )
        self.manager = User.objects.create_user("manager2", password="pass", role=User.Role.MANAGER)
        self.staff = User.objects.create_user("staff2", password="pass", role=User.Role.STAFF)
        self.project = Project.objects.create(
            project_name="View Project",
            project_link="https://example.com/view",
            created_by=self.manager,
        )

    def test_admin_can_open_user_management(self):
        self.client.login(username="admin", password="pass")
        response = self.client.get(reverse("user_list"))

        self.assertEqual(response.status_code, 200)
        self.assertContains(response, "Tạo người dùng")

    def test_manager_can_assign_from_project_detail_action(self):
        self.client.login(username="manager2", password="pass")
        response = self.client.post(
            reverse("assign_projects"),
            {"project_ids": str(self.project.pk), "employee": self.staff.pk},
        )
        self.project.refresh_from_db()

        self.assertEqual(response.status_code, 302)
        self.assertEqual(self.project.current_employee, self.staff)

    def test_bulk_assign_accepts_deadline_priority_note_and_notification(self):
        from django.utils import timezone

        self.client.login(username="manager2", password="pass")
        deadline = timezone.now() + timezone.timedelta(days=2)
        response = self.client.post(
            reverse("bulk_action"),
            {
                "action": "assign",
                "project_ids": [str(self.project.pk)],
                "employee": str(self.staff.pk),
                "deadline_at": deadline.strftime("%Y-%m-%dT%H:%M"),
                "priority": Project.Priority.HIGH,
                "note": "Lam theo checklist",
                "notify": "on",
            },
        )
        self.project.refresh_from_db()
        assignment = Assignment.objects.get(project=self.project)

        self.assertEqual(response.status_code, 302)
        self.assertEqual(self.project.priority, Project.Priority.HIGH)
        self.assertEqual(assignment.note, "Lam theo checklist")
        self.assertTrue(Notification.objects.filter(recipient=self.staff, project=self.project).exists())

    def test_manager_can_bulk_change_project_state(self):
        self.client.login(username="manager2", password="pass")

        response = self.client.post(
            reverse("bulk_action"),
            {
                "action": "change_project_state",
                "project_ids": [str(self.project.pk)],
                "project_state": Project.ProjectState.PAUSED,
            },
        )
        self.project.refresh_from_db()

        self.assertEqual(response.status_code, 302)
        self.assertEqual(self.project.project_state, Project.ProjectState.PAUSED)

    def test_manager_can_update_project_state_from_detail(self):
        self.client.login(username="manager2", password="pass")

        response = self.client.post(
            reverse("project_state_update", args=[self.project.pk]),
            {"project_state": Project.ProjectState.AF_LOCKED},
        )
        self.project.refresh_from_db()

        self.assertEqual(response.status_code, 302)
        self.assertEqual(self.project.project_state, Project.ProjectState.AF_LOCKED)

    def test_report_page_renders_chart_data(self):
        self.client.login(username="manager2", password="pass")
        response = self.client.get(reverse("reports"))

        self.assertEqual(response.status_code, 200)
        self.assertContains(response, "du-lieu-trang-thai")

    def test_staff_can_submit_progress_for_assigned_project(self):
        self.project.current_employee = self.staff
        self.project.save(update_fields=["current_employee"])
        self.client.login(username="staff2", password="pass")

        response = self.client.post(
            reverse("project_progress_update", args=[self.project.pk]),
            {"progress_percent": 70, "status_note": "Gan xong", "blocker_note": ""},
        )

        self.assertEqual(response.status_code, 302)
        self.assertTrue(ProjectProgress.objects.filter(project=self.project, progress_percent=70).exists())

    def test_staff_cannot_submit_progress_for_unassigned_project(self):
        self.client.login(username="staff2", password="pass")

        response = self.client.post(
            reverse("project_progress_update", args=[self.project.pk]),
            {"progress_percent": 70, "status_note": "Khong duoc"},
        )

        self.assertEqual(response.status_code, 404)

    def test_notification_mark_read(self):
        notice = Notification.objects.create(
            recipient=self.staff,
            actor=self.manager,
            project=self.project,
            title="Test",
            message="Msg",
        )
        self.client.login(username="staff2", password="pass")

        response = self.client.post(reverse("notification_read", args=[notice.pk]))
        notice.refresh_from_db()

        self.assertEqual(response.status_code, 302)
        self.assertTrue(notice.is_read)

    def test_telegram_settings_page_renders_instructions(self):
        TelegramSettings.objects.create(bot_username="demo_bot")
        self.client.login(username="staff2", password="pass")

        response = self.client.get(reverse("telegram_settings"))

        self.assertEqual(response.status_code, 200)
        self.assertContains(response, "Hướng dẫn cho nhân viên")
        self.assertContains(response, "/start")

    def test_notification_records_skipped_telegram_when_not_linked(self):
        notice = NotificationService.create(
            recipient=self.staff,
            actor=self.manager,
            project=self.project,
            title="Test Telegram",
            message="Msg",
        )

        self.assertEqual(notice.telegram_status, "SKIPPED")
        self.assertIn("chưa bật", notice.telegram_error)

    def test_staff_dashboard_only_shows_visible_blockers(self):
        self.project.current_employee = self.staff
        self.project.save(update_fields=["current_employee"])
        hidden = Project.objects.create(
            project_name="Hidden blocker",
            project_link="https://example.com/hidden-blocker",
            created_by=self.manager,
        )
        ProjectProgress.objects.create(project=self.project, user=self.staff, progress_percent=10, status_note="Visible", blocker_note="visible blocker")
        ProjectProgress.objects.create(project=hidden, user=self.manager, progress_percent=20, status_note="Hidden", blocker_note="hidden blocker")
        self.client.login(username="staff2", password="pass")

        response = self.client.get(reverse("dashboard"))

        self.assertEqual(response.status_code, 200)
        blockers = list(response.context["blocked_progress"])
        self.assertEqual(len(blockers), 1)
        self.assertEqual(blockers[0].project, self.project)
