import pytest
from django.core.files.uploadedfile import SimpleUploadedFile
from django.db.models.deletion import ProtectedError
from django.urls import reverse

from library.borrower_import import import_borrower_rows
from library.forms import BorrowerForm
from library.models import SchoolClass, Borrower, EmployeePosition


pytestmark = pytest.mark.django_db


def test_default_positions():
    assert set(EmployeePosition.objects.values_list("name", flat=True)) == {
        "Teacher", "Teaching assistant", "Librarian", "School secretary", "Head of school",
    }


@pytest.mark.parametrize("role,position_name,visible", [
    ("employee", "Administration", True),
    ("employee", None, False),
    ("student", None, False),
])
def test_profile_position_badge(client, django_user_model, role, position_name, visible):
    client.force_login(django_user_model.objects.create_user(username="operator", is_staff=True))
    position = EmployeePosition.objects.create(name=position_name) if position_name else None
    borrower = Borrower.objects.create(first_name="Pat", last_name="Reader", school_role=role, position=position)
    response = client.get(borrower.get_absolute_url())
    assert response.status_code == 200
    assert (b'class="status-badge position"' in response.content) is visible
    if visible:
        assert b'class="status-badge position">Administration</span>' in response.content


def test_positions_can_be_renamed_deactivated_and_not_deleted_when_used(client, django_user_model):
    account = django_user_model.objects.create_user(username="admin", is_staff=True)
    client.force_login(account)
    position = EmployeePosition.objects.get(name="Teacher")
    borrower = Borrower.objects.create(first_name="Pat", last_name="Reader", school_role="employee", position=position)
    response = client.post(reverse("employee_position_edit", args=[position.pk]), {"name": "Educator"})
    assert response.status_code == 302
    borrower.refresh_from_db()
    assert borrower.position.name == "Educator"
    assert not borrower.position.active
    with pytest.raises(ProtectedError):
        borrower.position.delete()
    response = client.post(reverse("employee_position_edit", args=[position.pk]), {"action": "delete"}, follow=True)
    assert b"Deactivate it instead" in response.content


def test_inactive_position_can_be_retained_but_not_assigned():
    position = EmployeePosition.objects.create(name="Former position", active=False)
    borrower = Borrower.objects.create(first_name="Pat", last_name="Reader", school_role="employee", position=position)
    data = {"first_name": "Pat", "last_name": "Reader", "school_role": "employee", "position": position.pk}
    assert BorrowerForm(data, instance=borrower).is_valid()
    assert not BorrowerForm(data).is_valid()
    data["school_role"] = "student"
    assert not BorrowerForm(data, instance=borrower).is_valid()


def test_csv_employee_has_position_but_no_login(django_user_model):
    import_borrower_rows([{
        "Borrower ID": "employee1", "First name": "Pat", "Last name": "Reader",
        "School role": "EMPLOYEE", "Position": "teacher", "Class": "4A",
    }])
    borrower = Borrower.objects.get(username="employee1")
    assert borrower.school_role == "employee"
    assert borrower.position.name == "Teacher"
    assert borrower.school_class is None
    assert borrower.staff_account_id is None
    assert not django_user_model.objects.exists()
    import_borrower_rows([{"Borrower ID": "employee1", "First name": "Pat", "Last name": "Updated"}])
    borrower.refresh_from_db()
    assert borrower.position.name == "Teacher"
    assert borrower.school_role == "employee"
    import_borrower_rows([{"Borrower ID": "employee1", "First name": "Pat", "Last name": "Updated", "Position": ""}])
    borrower.refresh_from_db()
    assert borrower.position_id is None


def test_csv_bad_position_rolls_back_all_rows():
    rows = [
        {"Borrower ID": "one", "First name": "A", "Last name": "Reader", "Position": "Teacher"},
        {"Borrower ID": "two", "First name": "B", "Last name": "Reader", "Position": "Typo"},
    ]
    with pytest.raises(ValueError, match="Row 3: Unknown position"):
        import_borrower_rows([{**row, "School role": "Employee"} for row in rows])
    assert not Borrower.objects.exists()
    assert not EmployeePosition.objects.filter(name="Typo").exists()


def test_borrower_csv_imports_employees_and_is_protected(client, django_user_model):
    url = reverse("import_borrowers")
    assert client.get(url).status_code == 302
    account = django_user_model.objects.create_user(username="admin", is_staff=True)
    client.force_login(account)
    response = client.post(url, {"csv_file": SimpleUploadedFile(
        "borrowers.csv", b"Borrower ID,First name,Last name,School role,Position\nnew,Pat,Reader,Employee,Librarian\n",
    )})
    assert response.status_code == 302
    borrower = Borrower.objects.get(username="new")
    assert borrower.school_role == "employee"
    assert borrower.position.name == "Librarian"
    assert borrower.staff_account_id is None
    assert django_user_model.objects.count() == 1


def test_student_with_login_keeps_student_role_on_account_save(django_user_model):
    borrower = Borrower.objects.create(username="student-admin", first_name="Student", last_name="Helper")
    account = django_user_model.objects.create_user(username="student-admin", is_staff=True)
    account.save()
    borrower.refresh_from_db()
    assert borrower.school_role == "student"
    assert borrower.staff_account_id == account.pk


@pytest.mark.parametrize("class_name", ["3A", ""])
def test_student_class_badge(client, django_user_model, class_name):
    client.force_login(django_user_model.objects.create_user(username="operator", is_staff=True))
    school_class = SchoolClass.objects.create(name=class_name) if class_name else None
    borrower = Borrower.objects.create(first_name="Student", last_name="Reader", school_class=school_class)
    response = client.get(borrower.get_absolute_url())
    assert (b'class="status-badge school-class"' in response.content) is bool(class_name)
    if class_name:
        assert b'class="status-badge school-class">3A</span>' in response.content
