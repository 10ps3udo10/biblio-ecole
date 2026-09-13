import pytest
from django.core.files.uploadedfile import SimpleUploadedFile
from django.urls import reverse

from library.borrower_import import import_borrower_rows
from library.forms import BorrowerForm, SchoolClassForm
from library.models import Borrower, SchoolClass

pytestmark = pytest.mark.django_db


def test_class_management_preserves_assignments_and_protects_used_classes(client, django_user_model):
    url = reverse("school_classes")
    assert client.get(url).status_code == 302
    client.force_login(django_user_model.objects.create_user(username="operator", is_staff=True))
    assert client.post(url, {"name": "3A", "active": "on"}).status_code == 302
    school_class = SchoolClass.objects.get(name="3A")
    borrower = Borrower.objects.create(first_name="Sam", last_name="Reader", school_class=school_class)
    edit = reverse("school_class_edit", args=[school_class.pk])
    assert client.post(edit, {"name": "Upper elementary"}).status_code == 302
    borrower.refresh_from_db()
    assert borrower.school_class.name == "Upper elementary"
    assert not borrower.school_class.active
    response = client.post(edit, {"action": "delete"}, follow=True)
    assert b"Deactivate it instead" in response.content
    borrower.school_class = None
    borrower.save()
    client.post(edit, {"action": "delete"})
    assert not SchoolClass.objects.exists()


def test_class_form_choices_and_role_switch():
    school_class = SchoolClass.objects.create(name="3A", active=False)
    borrower = Borrower.objects.create(first_name="Sam", last_name="Reader", school_class=school_class)
    data = {"first_name": "Sam", "last_name": "Reader", "school_role": "student", "school_class": school_class.pk}
    assert BorrowerForm(data, instance=borrower).is_valid()
    assert not BorrowerForm(data).is_valid()
    assert not SchoolClassForm({"name": "3a", "active": "on"}).is_valid()
    data["school_role"] = "employee"
    form = BorrowerForm(data, instance=borrower)
    assert form.is_valid()
    assert form.save().school_class is None


def test_class_csv_validation_preservation_and_clearing():
    school_class = SchoolClass.objects.create(name="3A")
    row = {"Borrower ID": "sam", "First name": "Sam", "Last name": "Reader"}
    import_borrower_rows([{**row, "Class": "3a"}])
    borrower = Borrower.objects.get(username="sam")
    assert borrower.school_class == school_class
    school_class.active = False
    school_class.save()
    import_borrower_rows([{**row, "Class": "3A"}])
    import_borrower_rows([row])
    borrower.refresh_from_db()
    assert borrower.school_class == school_class
    with pytest.raises(ValueError, match="inactive"):
        import_borrower_rows([{**row, "Borrower ID": "new", "Class": "3A"}])
    with pytest.raises(ValueError, match="Row 3: Unknown class"):
        import_borrower_rows([{**row, "Borrower ID": "new"}, {**row, "Class": "Typo"}])
    assert not Borrower.objects.filter(username="new").exists()
    import_borrower_rows([{**row, "Class": ""}])
    borrower.refresh_from_db()
    assert borrower.school_class is None


def test_single_csv_import_accepts_students_and_employees(client, django_user_model):
    SchoolClass.objects.create(name="3A")
    client.force_login(django_user_model.objects.create_user(username="operator", is_staff=True))
    upload = SimpleUploadedFile("borrowers.csv",
        b"Borrower ID,First name,Last name,School role,Position,Class\n"
        b"student,Sam,Reader,Student,,3A\n"
        b"employee,Pat,Reader,Employee,Teacher,\n")
    response = client.post(reverse("import_borrowers"), {"csv_file": upload})
    assert response.status_code == 302
    assert Borrower.objects.get(username="student").school_class.name == "3A"
    assert Borrower.objects.get(username="employee").position.name == "Teacher"
    assert django_user_model.objects.count() == 1
    assert client.get("/employees/import/").status_code == 404
    assert client.get("/employees/").status_code == 404
    settings = client.get(reverse("school_settings"))
    assert b">Employees</a>" not in settings.content
    assert b"Import borrowers CSV" in settings.content
    listing = client.get(reverse("borrower_list"))
    assert b"Add borrower" in listing.content
    assert b"Add employee" not in listing.content
