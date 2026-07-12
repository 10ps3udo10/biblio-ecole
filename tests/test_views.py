from datetime import timedelta

import pytest
from django.core.files.uploadedfile import SimpleUploadedFile
from django.urls import reverse
from django.utils import timezone

from library.models import Book, Borrower, Copy, Loan, SchoolProfile
from library.photo_intake import is_valid_isbn


@pytest.fixture
def logged_in_client(client, django_user_model):
    django_user_model.objects.create_user(username="librarian", password="secret", is_staff=True)
    assert client.login(username="librarian", password="secret")
    return client


@pytest.mark.django_db
def test_unauthenticated_user_uses_single_admin_login(client):
    response = client.get(reverse("dashboard"))

    assert response.status_code == 302
    assert response.url.startswith("/admin/login/")


@pytest.mark.django_db
def test_public_circulation_desk_does_not_require_admin_login(client):
    Borrower.objects.create(username="student", first_name="Student", last_name="One")

    response = client.get(reverse("photo_circulation"))

    assert response.status_code == 200
    assert b"Borrow or return a book" in response.content
    assert b"/admin/login/" not in response.content
    assert b"The photo is read once and never saved" in response.content
    assert b"https://mrueda.github.io/shelf-school/" in response.content


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
def test_add_book_downloads_catalog_cover_from_isbn(logged_in_client, tmp_path, settings, monkeypatch):
    settings.MEDIA_ROOT = tmp_path
    monkeypatch.setattr("library.views.download_cover_by_isbn", lambda isbn: (b"downloaded cover", "jpg"))

    response = logged_in_client.post(
        reverse("book_create"),
        {
            "isbn13": "9788408052524",
            "title": "La sombra del viento",
            "authors": "Carlos Ruiz Zafon",
            "first_copy_condition": Copy.Condition.GOOD,
        },
    )

    assert response.status_code == 302
    book = Book.objects.get(isbn13="9788408052524")
    with book.cover_image.open("rb") as cover:
        assert cover.read() == b"downloaded cover"


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
    monkeypatch.setattr("library.views.download_cover_by_isbn", lambda isbn: (b"api cover bytes", "jpg"))
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
    with book.cover_image.open("rb") as stored_cover:
        assert stored_cover.read() == b"api cover bytes"


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
    assert book.cover_image
    with book.cover_image.open("rb") as stored_cover:
        assert stored_cover.read() == b"fake image bytes"


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
    assert not book.cover_image
    assert not list(tmp_path.rglob("*"))


@pytest.mark.django_db
def test_isbn_metadata_endpoint_returns_free_catalog_details(logged_in_client, monkeypatch):
    monkeypatch.setattr(
        "library.views.lookup_book_by_isbn",
        lambda isbn: {
            "title": "Automatic ISBN Title",
            "authors": "Free Catalog Author",
            "publisher": "Open Publisher",
            "publication_year": 2020,
        },
    )

    response = logged_in_client.get(reverse("isbn_metadata"), {"isbn": "9780316381994"})

    assert response.status_code == 200
    assert response.json()["title"] == "Automatic ISBN Title"
    assert response.json()["source"] == "open_library"


@pytest.mark.django_db
def test_valid_isbn_without_free_metadata_is_explained(logged_in_client, monkeypatch):
    monkeypatch.setattr("library.views.lookup_book_by_isbn", lambda isbn: {})

    response = logged_in_client.get(reverse("isbn_metadata"), {"isbn": "9798302434630"})

    assert is_valid_isbn("9798302434630")
    assert response.status_code == 200
    assert response.json()["source"] == "none"
    assert "ISBN is valid" in response.json()["message"]
    assert "9798302434630" in response.json()["search_url"]


@pytest.mark.django_db
def test_staff_can_delete_stored_intake_photo(logged_in_client, tmp_path, settings):
    settings.MEDIA_ROOT = tmp_path
    book = Book.objects.create(
        title="Stored cover",
        cover_image=SimpleUploadedFile("stored.jpg", b"stored photo", content_type="image/jpeg"),
    )
    storage = book.cover_image.storage
    stored_name = book.cover_image.name
    assert storage.exists(stored_name)

    response = logged_in_client.post(reverse("delete_book_photo", args=[book.id]))

    assert response.status_code == 302
    book.refresh_from_db()
    assert not book.cover_image
    assert not storage.exists(stored_name)


@pytest.mark.django_db
def test_deleting_book_removes_stored_intake_photo(tmp_path, settings):
    settings.MEDIA_ROOT = tmp_path
    book = Book.objects.create(
        title="Deleted book",
        cover_image=SimpleUploadedFile("deleted.jpg", b"stored photo", content_type="image/jpeg"),
    )
    storage = book.cover_image.storage
    stored_name = book.cover_image.name

    book.delete()

    assert not storage.exists(stored_name)


@pytest.mark.django_db
def test_staff_can_delete_book_without_loan_history(logged_in_client, tmp_path, settings):
    settings.MEDIA_ROOT = tmp_path
    book = Book.objects.create(
        title="Delete this title",
        cover_image=SimpleUploadedFile("delete-me.jpg", b"cover", content_type="image/jpeg"),
    )
    Copy.objects.create(book=book, copy_number=1)
    stored_name = book.cover_image.name
    storage = book.cover_image.storage

    response = logged_in_client.post(reverse("delete_book", args=[book.id]))

    assert response.status_code == 302
    assert not Book.objects.filter(pk=book.id).exists()
    assert not storage.exists(stored_name)


@pytest.mark.django_db
def test_returned_book_and_loan_history_can_be_deleted(logged_in_client):
    book = Book.objects.create(title="Delete returned history")
    copy = Copy.objects.create(book=book, copy_number=1)
    borrower = Borrower.objects.create(username="history", first_name="History", last_name="Reader")
    Loan.objects.create(copy=copy, borrower=borrower, return_date=timezone.localdate())

    response = logged_in_client.post(reverse("delete_book", args=[book.id]))

    assert response.status_code == 302
    assert not Book.objects.filter(pk=book.id).exists()
    assert not Loan.objects.filter(copy_id=copy.id).exists()


@pytest.mark.django_db
def test_checked_out_book_cannot_be_deleted(logged_in_client):
    book = Book.objects.create(title="Currently checked out")
    copy = Copy.objects.create(book=book, copy_number=1, status=Copy.Status.CHECKED_OUT)
    borrower = Borrower.objects.create(username="active", first_name="Active", last_name="Reader")
    Loan.objects.create(copy=copy, borrower=borrower)

    response = logged_in_client.post(reverse("delete_book", args=[book.id]), follow=True)

    assert response.status_code == 200
    assert Book.objects.filter(pk=book.id).exists()
    assert b"cannot be deleted while a copy is checked out" in response.content


@pytest.mark.django_db
def test_photo_intake_adds_copy_to_existing_isbn_instead_of_duplicate_book(logged_in_client, tmp_path, settings, monkeypatch):
    settings.MEDIA_ROOT = tmp_path
    book = Book.objects.create(title="Existing title", isbn13="9780316381994")
    Copy.objects.create(book=book, copy_number=1)
    monkeypatch.setattr("library.views.decode_isbn_from_image", lambda photo: "9780316381994")
    monkeypatch.setattr("library.views.lookup_book_by_isbn", lambda isbn: pytest.fail("metadata lookup should not run"))
    photo = SimpleUploadedFile("barcode.jpg", b"fake image bytes", content_type="image/jpeg")

    response = logged_in_client.post(
        reverse("photo_intake"),
        {"photos": photo, "condition": Copy.Condition.GOOD, "shelf_location": "B2"},
    )

    assert response.status_code == 302
    assert Book.objects.count() == 1
    assert book.copies.count() == 2
    assert book.copies.get(copy_number=2).shelf_location == "B2"


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

    assert checkout.status_code == 200
    assert checkout.context["confirmation"] is True
    assert Loan.objects.count() == 0
    checkout = logged_in_client.post(
        reverse("photo_circulation"),
        {"confirmation_token": checkout.context["confirmation_token"]},
    )

    assert checkout.status_code == 302
    copy.refresh_from_db()
    assert copy.status == Copy.Status.CHECKED_OUT
    assert Loan.objects.filter(copy=copy, borrower=borrower, return_date__isnull=True).exists()

    checkin = logged_in_client.post(
        reverse("photo_circulation"),
        {"action": "checkin", "borrower": str(borrower.id), "return_copies": [str(copy.id)]},
    )

    assert checkin.status_code == 200
    assert Loan.objects.get(copy=copy).return_date is None
    checkin = logged_in_client.post(
        reverse("photo_circulation"),
        {"confirmation_token": checkin.context["confirmation_token"]},
    )

    assert checkin.status_code == 302
    copy.refresh_from_db()
    loan = Loan.objects.get(copy=copy, borrower=borrower)
    assert copy.status == Copy.Status.AVAILABLE
    assert loan.return_date == timezone.localdate()


@pytest.mark.django_db
def test_circulation_photo_is_not_saved_to_media(client, tmp_path, settings, monkeypatch):
    settings.MEDIA_ROOT = tmp_path
    book = Book.objects.create(title="Temporary circulation photo")
    copy = Copy.objects.create(book=book, copy_number=1)
    borrower = Borrower.objects.create(username="student", first_name="Student", last_name="One")
    monkeypatch.setattr("library.views.decode_barcodes_from_image", lambda photo: [copy.qr_code])
    photo = SimpleUploadedFile("circulation.png", b"temporary bytes", content_type="image/png")

    response = client.post(
        reverse("photo_circulation"),
        {
            "action": "checkout",
            "borrower": str(borrower.id),
            "book_photo": photo,
            "due_date": (timezone.localdate() + timedelta(days=14)).isoformat(),
        },
    )

    assert response.status_code == 200
    assert response.context["confirmation"] is True
    assert not list(tmp_path.rglob("*"))


@pytest.mark.django_db
def test_circulation_accepts_exact_copy_from_manual_fallback(client):
    book = Book.objects.create(title="Manual fallback", authors="Searchable Author")
    copy = Copy.objects.create(book=book, copy_number=1, shelf_location="A4")
    borrower = Borrower.objects.create(username="reader", first_name="Test", last_name="Reader")

    response = client.post(
        reverse("photo_circulation"),
        {
            "action": "checkout",
            "borrower": str(borrower.id),
            "manual_copy": str(copy.id),
            "due_date": (timezone.localdate() + timedelta(days=14)).isoformat(),
        },
    )

    assert response.status_code == 200
    assert response.context["confirmation"] is True
    assert response.context["copy"] == copy


@pytest.mark.django_db
def test_photo_circulation_rejects_checkin_for_wrong_borrower(logged_in_client):
    book = Book.objects.create(title="Borrower mismatch")
    copy = Copy.objects.create(book=book, copy_number=1, status=Copy.Status.CHECKED_OUT)
    borrower = Borrower.objects.create(username="mia", first_name="Mia", last_name="Lopez")
    other = Borrower.objects.create(username="leo", first_name="Leo", last_name="Garcia")
    Loan.objects.create(copy=copy, borrower=borrower)
    response = logged_in_client.post(
        reverse("photo_circulation"),
        {"action": "checkin", "borrower": str(other.id), "return_copies": [str(copy.id)]},
    )

    assert response.status_code == 200
    assert b"Select a valid choice" in response.content
    copy.refresh_from_db()
    assert copy.status == Copy.Status.CHECKED_OUT


@pytest.mark.django_db
def test_borrower_can_return_multiple_active_loans_together(client):
    borrower = Borrower.objects.create(username="reader", first_name="Test", last_name="Reader")
    other = Borrower.objects.create(username="other", first_name="Other", last_name="Reader")
    first = Copy.objects.create(book=Book.objects.create(title="First return"), copy_number=1, status=Copy.Status.CHECKED_OUT)
    second = Copy.objects.create(book=Book.objects.create(title="Second return"), copy_number=1, status=Copy.Status.CHECKED_OUT)
    other_copy = Copy.objects.create(book=Book.objects.create(title="Not this borrower"), copy_number=1, status=Copy.Status.CHECKED_OUT)
    Loan.objects.create(copy=first, borrower=borrower)
    Loan.objects.create(copy=second, borrower=borrower)
    Loan.objects.create(copy=other_copy, borrower=other)

    response = client.post(
        reverse("photo_circulation"),
        {
            "action": "checkin",
            "borrower": str(borrower.id),
            "return_copies": [str(first.id), str(second.id)],
        },
    )

    assert response.status_code == 200
    assert response.context["copies"] == [first, second]
    response = client.post(
        reverse("photo_circulation"),
        {"confirmation_token": response.context["confirmation_token"]},
    )

    assert response.status_code == 302
    assert not Loan.objects.filter(copy__in=[first, second], return_date__isnull=True).exists()
    assert Loan.objects.filter(copy=other_copy, return_date__isnull=True).exists()


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


@pytest.mark.django_db
def test_staff_can_complete_school_setup(logged_in_client):
    response = logged_in_client.post(
        reverse("school_settings"),
        {
            "school_name": "Escola Montserrat",
            "short_name": "Montserrat Library",
            "address": "1 School Road",
            "contact_email": "library@example.org",
            "contact_phone": "123456789",
            "default_loan_days": 21,
            "label_footer": "Return to reception",
        },
    )

    assert response.status_code == 302
    profile = SchoolProfile.current()
    assert profile.setup_completed is True
    assert profile.default_loan_days == 21
    assert profile.display_name == "Montserrat Library"


@pytest.mark.django_db
def test_staff_can_import_and_update_borrowers(logged_in_client):
    Borrower.objects.create(username="mrueda", first_name="Old", last_name="Name")
    csv_file = SimpleUploadedFile(
        "borrowers.csv",
        b"Username,First name,Last name,Class,Email,Active\n"
        b"mrueda,Manuel,Rueda,Staff,mrueda@example.org,yes\n"
        b"ana,Ana,Garcia,4A,ana@example.org,true\n",
        content_type="text/csv",
    )

    response = logged_in_client.post(reverse("import_borrowers"), {"csv_file": csv_file})

    assert response.status_code == 302
    assert Borrower.objects.count() == 2
    assert Borrower.objects.get(username="mrueda").first_name == "Manuel"
    assert Borrower.objects.get(username="ana").class_name == "4A"


@pytest.mark.django_db
def test_overdue_report_and_csv_only_include_overdue_active_loans(logged_in_client):
    borrower = Borrower.objects.create(username="ana", first_name="Ana", last_name="Garcia")
    overdue_copy = Copy.objects.create(book=Book.objects.create(title="Late book"), copy_number=1, status=Copy.Status.CHECKED_OUT)
    current_copy = Copy.objects.create(book=Book.objects.create(title="Current book"), copy_number=1, status=Copy.Status.CHECKED_OUT)
    Loan.objects.create(copy=overdue_copy, borrower=borrower, due_date=timezone.localdate() - timedelta(days=1))
    Loan.objects.create(copy=current_copy, borrower=borrower, due_date=timezone.localdate() + timedelta(days=1))

    response = logged_in_client.get(reverse("overdue_loans"))
    export = logged_in_client.get(reverse("overdue_loans_csv"))

    assert response.status_code == 200
    assert b"Late book" in response.content
    assert b"Current book" not in response.content
    assert b"Late book" in export.content
    assert b"Current book" not in export.content
