from datetime import timedelta

import pytest
from django.db import IntegrityError, transaction
from django.utils import timezone

from library.forms import BorrowerForm
from library.models import SchoolClass, Book, Borrower, Copy, Loan, SchoolProfile


@pytest.mark.django_db
def test_copy_and_borrower_qr_payloads_are_generated():
    book = Book.objects.create(title="The Hobbit", authors="J. R. R. Tolkien")
    copy = Copy.objects.create(book=book, copy_number=1)
    borrower = Borrower.objects.create(first_name="Ana", last_name="Garcia", school_class=SchoolClass.objects.get_or_create(name="4A")[0])

    assert copy.qr_code == f"COPY:{copy.id}"
    assert borrower.qr_code == f"BORROWER:{borrower.id}"


@pytest.mark.django_db
def test_borrower_ids_are_generated_sequentially_and_not_editable():
    first = Borrower.objects.create(first_name="Ana", last_name="Garcia")
    second = Borrower.objects.create(first_name="Leo", last_name="Martinez")

    assert first.borrower_id == "B000001"
    assert second.borrower_id == "B000002"
    assert "borrower_id" not in BorrowerForm().fields


@pytest.mark.django_db
def test_optional_school_id_is_case_insensitively_unique_in_staff_form():
    existing = Borrower.objects.create(school_id="S-100", first_name="Ana", last_name="Garcia")
    form = BorrowerForm({
        "school_id": "s-100", "first_name": "Leo", "last_name": "Martinez",
        "school_role": "student", "active": "on",
    })
    assert not form.is_valid()
    assert "déjà attribué" in form.errors["school_id"][0]
    edit = BorrowerForm({
        "school_id": "s-100", "first_name": "Ana", "last_name": "Garcia",
        "school_role": "student", "active": "on",
    }, instance=existing)
    assert edit.is_valid()


@pytest.mark.django_db
def test_staff_account_automatically_creates_matching_borrower(django_user_model):
    account = django_user_model.objects.create_user(
        username="teacher",
        first_name="Teresa",
        last_name="Reader",
        email="teacher@example.org",
        is_staff=True,
    )

    borrower = account.borrower_profile
    assert borrower.borrower_id == "B000001"
    assert borrower.borrower_id != account.username
    assert borrower.school_id is None
    assert borrower.first_name == account.first_name
    assert borrower.last_name == account.last_name
    assert borrower.email == account.email
    assert borrower.school_class is None
    assert borrower.school_role == Borrower.SchoolRole.EMPLOYEE


@pytest.mark.django_db
def test_staff_account_does_not_link_borrowers_by_matching_free_text(django_user_model):
    existing = Borrower.objects.create(
        borrower_id="B009999",
        first_name="Old",
        last_name="Name",
        school_class=SchoolClass.objects.get_or_create(name="Staff")[0],
    )

    account = django_user_model.objects.create_user(
        username="teacher",
        first_name="Teresa",
        last_name="Reader",
        email="teacher@example.org",
        is_staff=True,
    )

    existing.refresh_from_db()
    assert account.borrower_profile != existing
    assert existing.full_name == "Old Name"
    assert existing.email == ""
    assert existing.school_class.name == "Staff"


@pytest.mark.django_db
def test_staff_identity_changes_are_synchronized_to_borrower(django_user_model):
    account = django_user_model.objects.create_user(
        username="teacher",
        first_name="Teresa",
        last_name="Reader",
        is_staff=True,
    )
    account.username = "treader"
    account.first_name = "Tess"
    account.email = "tess@example.org"
    account.save()

    borrower = account.borrower_profile
    borrower.refresh_from_db()
    borrower_id = borrower.borrower_id
    assert borrower_id.startswith("B")
    assert borrower.borrower_id != "treader"
    assert borrower.full_name == "Tess Reader"
    assert borrower.email == "tess@example.org"

    borrower.first_name = "Different"
    borrower.last_name = "Person"
    borrower.email = "different@example.org"
    borrower.save()
    borrower.refresh_from_db()
    assert borrower.borrower_id == borrower_id
    assert borrower.full_name == "Tess Reader"
    assert borrower.email == "tess@example.org"


@pytest.mark.django_db
def test_nonstaff_account_does_not_create_borrower(django_user_model):
    account = django_user_model.objects.create_user(username="student-login")

    assert not Borrower.objects.filter(staff_account=account).exists()


@pytest.mark.django_db
def test_only_one_active_loan_per_copy_is_allowed():
    book = Book.objects.create(title="Matilda")
    copy = Copy.objects.create(book=book, copy_number=1)
    first = Borrower.objects.create(first_name="First", last_name="Reader")
    second = Borrower.objects.create(first_name="Second", last_name="Reader")

    Loan.objects.create(copy=copy, borrower=first)
    with pytest.raises(IntegrityError):
        with transaction.atomic():
            Loan.objects.create(copy=copy, borrower=second)


@pytest.mark.django_db
def test_returned_copy_can_be_loaned_again():
    book = Book.objects.create(title="Wonder")
    copy = Copy.objects.create(book=book, copy_number=1)
    first = Borrower.objects.create(first_name="First", last_name="Reader")
    second = Borrower.objects.create(first_name="Second", last_name="Reader")
    loan = Loan.objects.create(copy=copy, borrower=first)

    loan.return_date = timezone.localdate()
    loan.save(update_fields=["return_date"])
    next_loan = Loan.objects.create(copy=copy, borrower=second)

    assert next_loan.is_active


@pytest.mark.django_db
def test_school_profile_is_singleton_and_controls_default_due_date():
    profile = SchoolProfile.current()
    profile.school_name = "Escola Test"
    profile.default_loan_days = 21
    profile.save()

    borrower = Borrower.objects.create(borrower_id="student", first_name="Student", last_name="One")
    book = Book.objects.create(title="Configured Loan")
    copy = Copy.objects.create(book=book, copy_number=1)
    loan = Loan.objects.create(copy=copy, borrower=borrower)

    assert SchoolProfile.current().school_name == "Escola Test"
    assert loan.due_date == timezone.localdate() + timedelta(days=21)
