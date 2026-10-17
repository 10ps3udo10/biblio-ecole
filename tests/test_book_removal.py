import pytest
from django.urls import reverse

from library.models import Book, Borrower, Copy, Loan
from library.views import _perform_circulation


@pytest.fixture
def staff_client(client, django_user_model):
    django_user_model.objects.create_user(username="maitresse", password="secret", is_staff=True)
    assert client.login(username="maitresse", password="secret")
    return client


@pytest.fixture
def borrowed(db):
    book = Book.objects.create(title="Le Gruffalo")
    first = Copy.objects.create(book=book, copy_number=1)
    second = Copy.objects.create(book=book, copy_number=2)
    borrower = Borrower.objects.create(first_name="Lina", last_name="Martin")
    _perform_circulation(first, borrower, "checkout")
    returned = Loan.objects.create(copy=second, borrower=borrower)
    returned.return_date = returned.checkout_date
    returned.save()
    return {"book": book, "first": first, "second": second, "borrower": borrower}


def test_removing_a_book_archives_it_and_keeps_history(staff_client, borrowed):
    borrowed["first"].refresh_from_db()
    _perform_circulation(borrowed["first"], borrowed["borrower"], "checkin")

    response = staff_client.post(reverse("delete_book", args=[borrowed["book"].pk]))

    assert response.status_code == 302
    book = Book.objects.get(pk=borrowed["book"].pk)
    assert book.archived_on is not None
    assert set(book.copies.values_list("status", flat=True)) == {Copy.Status.ARCHIVED}
    assert Loan.objects.filter(copy__book=book).count() == 2
    assert book not in staff_client.get(reverse("book_list")).context["books"]
    assert book in staff_client.get(reverse("book_list") + "?archived=1").context["books"]


def test_removing_a_borrowed_book_requires_confirmation(staff_client, borrowed):
    url = reverse("delete_book", args=[borrowed["book"].pk])

    warning = staff_client.post(url)

    assert warning.status_code == 200
    assert "est emprunté" in warning.content.decode()
    assert "Lina Martin" in warning.content.decode()
    assert Book.objects.get(pk=borrowed["book"].pk).archived_on is None

    staff_client.post(url, {"confirm_borrowed": "1"})

    first = Copy.objects.get(pk=borrowed["first"].pk)
    assert first.archived_on is not None
    assert first.status == Copy.Status.CHECKED_OUT
    assert first.active_loan is not None


def test_returning_a_removed_copy_archives_it(borrowed):
    copy = borrowed["first"]
    copy.refresh_from_db()
    copy.archived_on = copy.loans.first().checkout_date
    copy.save()

    _perform_circulation(copy, borrowed["borrower"], "checkin")

    copy.refresh_from_db()
    assert copy.status == Copy.Status.ARCHIVED


def test_removing_a_borrowed_copy_requires_confirmation_and_keeps_history(staff_client, borrowed):
    url = reverse("delete_copy", args=[borrowed["first"].pk])

    warning = staff_client.post(url)
    assert warning.status_code == 200
    assert Copy.objects.get(pk=borrowed["first"].pk).archived_on is None

    staff_client.post(url, {"confirm_borrowed": "1"})
    assert Copy.objects.get(pk=borrowed["first"].pk).archived_on is not None
    assert Loan.objects.filter(copy=borrowed["first"]).count() == 1


def test_removing_a_returned_copy_needs_no_confirmation(staff_client, borrowed):
    response = staff_client.post(reverse("delete_copy", args=[borrowed["second"].pk]))

    assert response.status_code == 302
    second = Copy.objects.get(pk=borrowed["second"].pk)
    assert second.status == Copy.Status.ARCHIVED
    assert second.loans.count() == 1


def test_restoring_a_book_puts_copies_back(staff_client, borrowed):
    staff_client.post(reverse("delete_book", args=[borrowed["book"].pk]), {"confirm_borrowed": "1"})

    staff_client.post(reverse("restore_book", args=[borrowed["book"].pk]))

    book = Book.objects.get(pk=borrowed["book"].pk)
    assert book.archived_on is None
    assert Copy.objects.get(pk=borrowed["second"].pk).status == Copy.Status.AVAILABLE
    assert Copy.objects.get(pk=borrowed["first"].pk).status == Copy.Status.CHECKED_OUT
