from datetime import timedelta

import pytest
from django.db import IntegrityError, transaction
from django.utils import timezone

from library.models import Book, Borrower, Copy, Loan, SchoolProfile


@pytest.mark.django_db
def test_copy_and_borrower_qr_payloads_are_generated():
    book = Book.objects.create(title="The Hobbit", authors="J. R. R. Tolkien")
    copy = Copy.objects.create(book=book, copy_number=1)
    borrower = Borrower.objects.create(first_name="Ana", last_name="Garcia", class_name="4A")

    assert copy.qr_code == f"COPY:{copy.id}"
    assert borrower.qr_code == f"BORROWER:{borrower.id}"


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

    borrower = Borrower.objects.create(username="student", first_name="Student", last_name="One")
    book = Book.objects.create(title="Configured Loan")
    copy = Copy.objects.create(book=book, copy_number=1)
    loan = Loan.objects.create(copy=copy, borrower=borrower)

    assert SchoolProfile.current().school_name == "Escola Test"
    assert loan.due_date == timezone.localdate() + timedelta(days=21)
