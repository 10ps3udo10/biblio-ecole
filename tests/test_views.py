from datetime import timedelta

import pytest
from django.core.files.uploadedfile import SimpleUploadedFile
from django.urls import reverse
from django.utils import timezone

from library.models import Book, Borrower, Copy, Loan, SchoolProfile


@pytest.fixture
def logged_in_client(client, django_user_model):
    django_user_model.objects.create_user(username="librarian", password="secret", is_staff=True)
    assert client.login(username="librarian", password="secret")
    return client


@pytest.mark.django_db
def test_add_book_creates_first_copy(logged_in_client):
    response = logged_in_client.post(
        reverse("book_create"),
        {
            "title": "The Hobbit",
            "authors": "J. R. R. Tolkien",
            "isbn13": "9780261103344",
            "first_copy_shelf": "A1",
            "first_copy_condition": Copy.Condition.GOOD,
        },
    )

    assert response.status_code == 302
    book = Book.objects.get(title="The Hobbit")
    copy = book.copies.get()
    assert copy.copy_number == 1
    assert copy.shelf_location == "A1"


@pytest.mark.django_db
def test_checkout_and_return_flow_updates_copy_status(logged_in_client):
    book = Book.objects.create(title="Matilda")
    copy = Copy.objects.create(book=book, copy_number=1)
    borrower = Borrower.objects.create(first_name="Ana", last_name="Garcia")
    due_date = timezone.localdate() + timedelta(days=7)

    checkout_response = logged_in_client.post(
        reverse("checkout"),
        {"borrower_code": borrower.qr_code, "copy_code": copy.qr_code, "due_date": due_date.isoformat()},
    )

    assert checkout_response.status_code == 302
    copy.refresh_from_db()
    assert copy.status == Copy.Status.CHECKED_OUT
    assert Loan.objects.filter(copy=copy, borrower=borrower, return_date__isnull=True).exists()

    return_response = logged_in_client.post(reverse("return_copy"), {"copy_code": copy.qr_code})

    assert return_response.status_code == 302
    copy.refresh_from_db()
    loan = Loan.objects.get(copy=copy)
    assert copy.status == Copy.Status.AVAILABLE
    assert loan.return_date == timezone.localdate()


@pytest.mark.django_db
def test_search_finds_books_by_shelf_status_and_author(logged_in_client):
    book = Book.objects.create(title="A Wrinkle in Time", authors="Madeleine L'Engle")
    Copy.objects.create(book=book, copy_number=1, shelf_location="Fiction-2")

    response = logged_in_client.get(reverse("book_list"), {"q": "Fiction-2"})

    assert response.status_code == 200
    assert b"A Wrinkle in Time" in response.content


@pytest.mark.django_db
def test_csv_import_and_export(logged_in_client):
    csv_file = SimpleUploadedFile(
        "books.csv",
        b"Title,Author,ISBN,Publisher,Year,Language,Copies,Shelf\n"
        b"Frindle,Andrew Clements,9780689818769,Simon,1996,en,2,B3\n",
        content_type="text/csv",
    )

    response = logged_in_client.post(reverse("import_books"), {"csv_file": csv_file})

    assert response.status_code == 302
    book = Book.objects.get(title="Frindle")
    assert book.copies.count() == 2

    export_response = logged_in_client.get(reverse("export_books_csv"))
    assert export_response.status_code == 200
    assert b"Frindle" in export_response.content


@pytest.mark.django_db
def test_photo_intake_creates_tracked_copy_without_paid_api(logged_in_client, tmp_path, settings, monkeypatch):
    settings.MEDIA_ROOT = tmp_path

    def fake_lookup(isbn):
        return {
            "title": "The Wild Robot",
            "authors": "Peter Brown",
            "isbn13": isbn,
            "publisher": "Little, Brown",
            "publication_year": 2016,
        }

    monkeypatch.setattr("library.views.lookup_book_by_isbn", fake_lookup)
    photo = SimpleUploadedFile("cover.jpg", b"fake image bytes", content_type="image/jpeg")

    response = logged_in_client.post(
        reverse("photo_intake"),
        {
            "photos": photo,
            "isbn": "9780316381994",
            "shelf_location": "Robots",
            "condition": Copy.Condition.GOOD,
        },
    )

    assert response.status_code == 302
    book = Book.objects.get(title="The Wild Robot")
    copy = book.copies.get()
    assert copy.qr_code == f"COPY:{copy.id}"
    assert copy.shelf_location == "Robots"
    assert book.cover_image.name.startswith("covers/")


@pytest.mark.django_db
def test_photo_intake_tracks_manual_title_when_isbn_is_missing(logged_in_client, tmp_path, settings):
    settings.MEDIA_ROOT = tmp_path
    photo = SimpleUploadedFile("cover.jpg", b"fake image bytes", content_type="image/jpeg")

    response = logged_in_client.post(
        reverse("photo_intake"),
        {"photos": photo, "title": "Classroom donation", "condition": Copy.Condition.WORN},
    )

    assert response.status_code == 302
    book = Book.objects.get(title="Classroom donation")
    copy = book.copies.get()
    assert copy.status == Copy.Status.AVAILABLE
    assert copy.condition == Copy.Condition.WORN


@pytest.mark.django_db
def test_photo_intake_uses_server_side_barcode_decode(logged_in_client, tmp_path, settings, monkeypatch):
    settings.MEDIA_ROOT = tmp_path
    monkeypatch.setattr("library.views.decode_isbn_from_image", lambda photo: "9780316381994")
    monkeypatch.setattr("library.views.lookup_book_by_isbn", lambda isbn: {"title": "Decoded Barcode Book", "isbn13": isbn})
    photo = SimpleUploadedFile("barcode.jpg", b"fake image bytes", content_type="image/jpeg")

    response = logged_in_client.post(
        reverse("photo_intake"),
        {"photos": photo, "condition": Copy.Condition.GOOD},
    )

    assert response.status_code == 302
    book = Book.objects.get(title="Decoded Barcode Book")
    assert book.isbn13 == "9780316381994"
    assert book.copies.count() == 1


@pytest.mark.django_db
def test_photo_intake_requires_isbn_or_title_after_failed_barcode_read(logged_in_client):
    photo = SimpleUploadedFile("cover.jpg", b"fake image bytes", content_type="image/jpeg")

    response = logged_in_client.post(
        reverse("photo_intake"),
        {"photos": photo, "condition": Copy.Condition.GOOD},
    )

    assert response.status_code == 200
    assert b"No ISBN barcode was detected" in response.content
    assert Book.objects.count() == 0


@pytest.mark.django_db
def test_photo_circulation_checkout_and_checkin_with_borrower_dropdown(logged_in_client, monkeypatch):
    book = Book.objects.create(title="Real Library Workflow", isbn13="9781234567897")
    copy = Copy.objects.create(book=book, copy_number=1)
    borrower = Borrower.objects.create(username="mia", first_name="Mia", last_name="Lopez")
    monkeypatch.setattr("library.views.decode_barcodes_from_image", lambda photo: [copy.qr_code])
    photo = SimpleUploadedFile("copy-qr.png", b"fake image bytes", content_type="image/png")

    checkout = logged_in_client.post(
        reverse("photo_circulation"),
        {
            "action": "checkout",
            "borrower": str(borrower.id),
            "book_photo": photo,
            "due_date": (timezone.localdate() + timedelta(days=14)).isoformat(),
        },
    )

    assert checkout.status_code == 302
    copy.refresh_from_db()
    assert copy.status == Copy.Status.CHECKED_OUT
    assert Loan.objects.filter(copy=copy, borrower=borrower, return_date__isnull=True).exists()

    photo = SimpleUploadedFile("copy-qr.png", b"fake image bytes", content_type="image/png")
    checkin = logged_in_client.post(
        reverse("photo_circulation"),
        {"action": "checkin", "borrower": str(borrower.id), "book_photo": photo},
    )

    assert checkin.status_code == 302
    copy.refresh_from_db()
    loan = Loan.objects.get(copy=copy, borrower=borrower)
    assert copy.status == Copy.Status.AVAILABLE
    assert loan.return_date == timezone.localdate()


@pytest.mark.django_db
def test_photo_circulation_rejects_checkin_for_wrong_borrower(logged_in_client, monkeypatch):
    book = Book.objects.create(title="Borrower mismatch")
    copy = Copy.objects.create(book=book, copy_number=1, status=Copy.Status.CHECKED_OUT)
    borrower = Borrower.objects.create(username="mia", first_name="Mia", last_name="Lopez")
    other = Borrower.objects.create(username="leo", first_name="Leo", last_name="Garcia")
    Loan.objects.create(copy=copy, borrower=borrower)
    monkeypatch.setattr("library.views.decode_barcodes_from_image", lambda photo: [copy.qr_code])
    photo = SimpleUploadedFile("copy-qr.png", b"fake image bytes", content_type="image/png")

    response = logged_in_client.post(
        reverse("photo_circulation"),
        {"action": "checkin", "borrower": str(other.id), "book_photo": photo},
    )

    assert response.status_code == 200
    assert b"checked out to a different borrower" in response.content
    copy.refresh_from_db()
    assert copy.status == Copy.Status.CHECKED_OUT


@pytest.mark.django_db
def test_school_profile_branding_appears_in_header_and_label(logged_in_client):
    profile = SchoolProfile.current()
    profile.school_name = "Escola Montserrat"
    profile.short_name = "Montserrat Library"
    profile.label_footer = "Return to reception"
    profile.save()
    book = Book.objects.create(title="Branded Label")
    copy = Copy.objects.create(book=book, copy_number=1)

    dashboard = logged_in_client.get(reverse("dashboard"))
    assert b"Montserrat Library" in dashboard.content

    label = logged_in_client.get(reverse("label", args=["copy", copy.id]))
    assert b"Montserrat Library" in label.content
    assert b"Return to reception" in label.content
