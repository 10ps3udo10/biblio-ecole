from datetime import timedelta

import pytest
from django.core.files.uploadedfile import SimpleUploadedFile
from django.urls import reverse
from django.utils import timezone

from library.forms import PhotoCirculationForm
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
    assert b'href="/admin/login/?next=/dashboard/"' in response.content
    assert b"Admin login" in response.content
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
def test_catalog_table_sorts_by_columns(logged_in_client):
    first = Book.objects.create(
        title="Alpha",
        authors="Zulu",
        isbn13="9780316381994",
        cover_image="covers/alpha.jpg",
        needs_information=True,
    )
    second = Book.objects.create(title="Beta", authors="Alpha", isbn13="9788408052524")
    Copy.objects.create(book=first, copy_number=1)
    Copy.objects.create(book=first, copy_number=2)
    Copy.objects.create(book=second, copy_number=1)

    by_author = logged_in_client.get(reverse("book_list"), {"sort": "author", "direction": "asc"})
    by_copies = logged_in_client.get(reverse("book_list"), {"sort": "copies", "direction": "desc"})
    by_cover = logged_in_client.get(reverse("book_list"), {"sort": "cover", "direction": "desc"})
    by_status = logged_in_client.get(reverse("book_list"), {"sort": "catalog_status", "direction": "desc"})

    assert [book.title for book in by_author.context["books"]] == ["Beta", "Alpha"]
    assert [book.title for book in by_copies.context["books"]] == ["Alpha", "Beta"]
    assert [book.title for book in by_cover.context["books"]] == ["Alpha", "Beta"]
    assert [book.title for book in by_status.context["books"]] == ["Alpha", "Beta"]
    assert b'aria-sort="descending"' in by_copies.content


@pytest.mark.django_db
def test_catalog_cover_fetch_selection_requires_a_valid_isbn(logged_in_client):
    eligible = Book.objects.create(title="Eligible cover", isbn13="9780316381994")
    no_isbn = Book.objects.create(title="ISBN still needed")

    response = logged_in_client.get(reverse("book_list"))
    eligibility = {book.pk: book.cover_fetch_eligible for book in response.context["books"]}

    assert eligibility == {eligible.pk: True, no_isbn.pk: False}
    assert b"ISBN needed" in response.content
    assert response.content.count(b'class="table-select cover-book-select"') == 1


@pytest.mark.django_db
def test_staff_fetches_only_missing_covers_for_selected_books(logged_in_client, tmp_path, settings, monkeypatch):
    settings.MEDIA_ROOT = tmp_path
    downloadable = Book.objects.create(
        title="Download cover",
        authors="Original Author",
        isbn13="9780316381994",
    )
    unavailable = Book.objects.create(title="Unavailable cover", isbn13="9788408052524")
    without_isbn = Book.objects.create(title="No ISBN")
    existing = Book.objects.create(
        title="Existing cover",
        isbn13="9780261103344",
        cover_image=SimpleUploadedFile("existing.jpg", b"existing cover", content_type="image/jpeg"),
    )
    calls = []

    def fake_download(isbn):
        calls.append(isbn)
        return (b"downloaded cover", "jpg") if isbn == downloadable.isbn13 else None

    monkeypatch.setattr("library.views.download_cover_by_isbn", fake_download)
    response = logged_in_client.post(
        reverse("fetch_book_covers"),
        {
            "books": [downloadable.pk, unavailable.pk, without_isbn.pk, existing.pk],
            "next": "/books/?sort=cover&direction=asc",
        },
        follow=True,
    )

    assert response.status_code == 200
    assert response.request["QUERY_STRING"] == "sort=cover&direction=asc"
    assert calls == [downloadable.isbn13, unavailable.isbn13]
    downloadable.refresh_from_db()
    existing.refresh_from_db()
    assert downloadable.authors == "Original Author"
    with downloadable.cover_image.open("rb") as cover:
        assert cover.read() == b"downloaded cover"
    with existing.cover_image.open("rb") as cover:
        assert cover.read() == b"existing cover"
    assert b"1 downloaded, 1 unavailable, 1 without a valid ISBN, 1 already present" in response.content


@pytest.mark.django_db
def test_cover_fetch_requires_a_selected_book(logged_in_client):
    response = logged_in_client.post(reverse("fetch_book_covers"), follow=True)

    assert response.status_code == 200
    assert b"Select at least one book with a missing cover." in response.content


@pytest.mark.django_db
def test_borrower_table_sorts_by_name_class_loans_and_status(logged_in_client):
    alpha = Borrower.objects.create(username="alpha", first_name="Amy", last_name="Zulu", class_name="1A")
    beta = Borrower.objects.create(username="beta", first_name="Ben", last_name="Alpha", class_name="2B", active=False)
    book = Book.objects.create(title="Borrowed title")
    copy = Copy.objects.create(book=book, copy_number=1, status=Copy.Status.CHECKED_OUT)
    Loan.objects.create(copy=copy, borrower=alpha)

    by_name = logged_in_client.get(reverse("borrower_list"), {"sort": "borrower", "direction": "asc"})
    by_loans = logged_in_client.get(reverse("borrower_list"), {"sort": "loans", "direction": "desc"})
    by_status = logged_in_client.get(reverse("borrower_list"), {"sort": "status", "direction": "asc"})

    assert [borrower.id for borrower in by_name.context["borrowers"]] == [beta.id, alpha.id]
    assert [borrower.id for borrower in by_loans.context["borrowers"]] == [alpha.id, beta.id]
    assert [borrower.id for borrower in by_status.context["borrowers"]] == [beta.id, alpha.id]


@pytest.mark.django_db
def test_overdue_and_copy_tables_sort_by_columns(logged_in_client):
    from datetime import timedelta

    book = Book.objects.create(title="Sortable copies")
    first = Copy.objects.create(book=book, copy_number=1, shelf_location="Z9", status=Copy.Status.CHECKED_OUT)
    second = Copy.objects.create(book=book, copy_number=2, shelf_location="A1", status=Copy.Status.CHECKED_OUT)
    first_borrower = Borrower.objects.create(username="z-user", first_name="Zed", last_name="Zulu")
    second_borrower = Borrower.objects.create(username="a-user", first_name="Amy", last_name="Alpha")
    Loan.objects.create(copy=first, borrower=first_borrower, due_date=timezone.localdate() - timedelta(days=1))
    Loan.objects.create(copy=second, borrower=second_borrower, due_date=timezone.localdate() - timedelta(days=2))

    copies = logged_in_client.get(reverse("book_detail", args=[book.id]), {"sort": "shelf", "direction": "asc"})
    overdue = logged_in_client.get(reverse("overdue_loans"), {"sort": "borrower", "direction": "desc"})

    assert [copy.id for copy in copies.context["copies"]] == [second.id, first.id]
    assert [loan.borrower_id for loan in overdue.context["loans"]] == [first_borrower.id, second_borrower.id]


@pytest.mark.django_db
def test_csv_import_and_export(logged_in_client):
    header = (
        "Source photo,Photo position,Title,Subtitle,Contributors,ISBN,Publisher,Publication year,Language,"
        "Pages,Format,Category,Topics,Description,Suggested Montessori level,Suggested age range,"
        "Suggested reading level,Identification confidence,Review notes,Bibliographic source URL\n"
    )
    csv_file = SimpleUploadedFile(
        "books.csv",
        (
            header
            + "photo-1.jpg,left,Frindle,,Andrew Clements,9780689818769,Simon,1996,en,105,Paperback,"
            "Fiction and imagination,school; words,A school story,Lower Elementary (6-9),7-10,"
            "Independent reader,high,,https://openlibrary.org/isbn/9780689818769\n"
            + "photo-1.jpg,right,Frindle,,Andrew Clements,9780689818769,Simon,1996,en,105,Paperback,"
            "Fiction and imagination,school; words,A school story,Lower Elementary (6-9),7-10,"
            "Independent reader,high,,https://openlibrary.org/isbn/9780689818769\n"
            + "photo-2.jpg,top right,,,,,,Catalan,,Picture book,Fiction and imagination,adventure,"
            "An unidentified illustrated book,Children's House (3-6),4-7,Read-aloud,low,"
            "Inspect the physical book,\n"
        ).encode("utf-8"),
        content_type="text/csv",
    )

    response = logged_in_client.post(reverse("import_books"), {"csv_file": csv_file})

    assert response.status_code == 302
    assert Book.objects.count() == 2
    assert Copy.objects.count() == 3
    book = Book.objects.get(title="Frindle")
    assert book.copies.count() == 2
    assert book.page_count == 105
    assert book.category == "Fiction and imagination"
    assert book.topics == "school; words"
    assert book.montessori_levels == "Lower Elementary (6-9)"
    assert book.needs_information is False
    assert book.copies.order_by("copy_number").first().source_position == "left"
    unidentified = Book.objects.exclude(pk=book.pk).get()
    assert unidentified.title == "Unidentified book (photo-2.jpg, top right)"
    assert unidentified.needs_information is True

    export_response = logged_in_client.get(reverse("export_books_csv"))
    assert export_response.status_code == 200
    assert b"Frindle" in export_response.content
    assert export_response.content.count(b"photo-1.jpg") == 2
    assert export_response.content.startswith(b"Source photo,Photo position,Title")

    repeated_file = SimpleUploadedFile(
        "books.csv",
        (header + "photo-1.jpg,left,Frindle,,Andrew Clements,9780689818769,Simon,1996,en,,,,,,,,,,,\n").encode(),
        content_type="text/csv",
    )
    repeated = logged_in_client.post(reverse("import_books"), {"csv_file": repeated_file})

    assert repeated.status_code == 302
    assert Copy.objects.count() == 3


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
def test_staff_can_edit_book_copy_and_borrower(logged_in_client):
    book = Book.objects.create(title="Original title", isbn13="9780316381994")
    copy = Copy.objects.create(book=book, copy_number=1, shelf_location="Old")
    borrower = Borrower.objects.create(username="old-user", first_name="Old", last_name="Name")

    response = logged_in_client.post(
        reverse("book_edit", args=[book.id]),
        {
            "title": "Corrected title",
            "isbn13": "9780316381994",
            "isbn10": "",
            "subtitle": "",
            "authors": "Correct Author",
            "publisher": "",
            "publication_year": "",
            "language": "",
            "description": "",
        },
    )
    assert response.status_code == 302
    book.refresh_from_db()
    assert book.title == "Corrected title"

    response = logged_in_client.post(
        reverse("copy_edit", args=[copy.id]),
        {"shelf_location": "B4", "condition": Copy.Condition.WORN, "status": Copy.Status.AVAILABLE},
    )
    assert response.status_code == 302
    copy.refresh_from_db()
    assert copy.shelf_location == "B4"
    assert copy.condition == Copy.Condition.WORN

    response = logged_in_client.post(
        reverse("borrower_edit", args=[borrower.id]),
        {
            "username": "correct-user",
            "first_name": "Correct",
            "last_name": "Name",
            "class_name": "4A",
            "email": "correct@example.org",
        },
    )
    assert response.status_code == 302
    borrower.refresh_from_db()
    assert borrower.username == "correct-user"
    assert borrower.full_name == "Correct Name"
    assert borrower.active is False


@pytest.mark.django_db
def test_book_edit_rejects_isbn_used_by_another_book(logged_in_client):
    Book.objects.create(title="Existing ISBN", isbn13="9780316381994")
    book = Book.objects.create(title="Book to edit")

    response = logged_in_client.post(
        reverse("book_edit", args=[book.id]),
        {
            "title": "Book to edit",
            "isbn13": "9780316381994",
            "isbn10": "",
            "subtitle": "",
            "authors": "",
            "publisher": "",
            "publication_year": "",
            "language": "",
            "description": "",
        },
    )

    assert response.status_code == 200
    assert b"belongs to another cataloged book" in response.content
    book.refresh_from_db()
    assert book.isbn13 == ""


@pytest.mark.django_db
def test_manual_book_form_normalizes_dashed_isbn(logged_in_client):
    response = logged_in_client.post(
        reverse("book_create"),
        {
            "title": "Dashed ISBN",
            "isbn13": "979-8324731472",
            "isbn10": "",
            "subtitle": "",
            "authors": "",
            "publisher": "",
            "publication_year": "",
            "language": "",
            "description": "",
            "first_copy_shelf": "",
            "first_copy_condition": Copy.Condition.GOOD,
        },
    )

    assert response.status_code == 302
    assert Book.objects.get(title="Dashed ISBN").isbn13 == "9798324731472"


@pytest.mark.django_db
def test_manual_book_form_rejects_invalid_dashed_isbn(logged_in_client):
    response = logged_in_client.post(
        reverse("book_create"),
        {
            "title": "Invalid ISBN",
            "isbn13": "979-8324731473",
            "isbn10": "",
            "subtitle": "",
            "authors": "",
            "publisher": "",
            "publication_year": "",
            "language": "",
            "description": "",
            "first_copy_shelf": "",
            "first_copy_condition": Copy.Condition.GOOD,
        },
    )

    assert response.status_code == 200
    assert b"Enter a valid ISBN-13" in response.content
    assert not Book.objects.filter(title="Invalid ISBN").exists()


@pytest.mark.django_db
def test_checked_out_copy_edit_cannot_change_circulation_status(logged_in_client):
    book = Book.objects.create(title="Checked out edit")
    copy = Copy.objects.create(book=book, copy_number=1, status=Copy.Status.CHECKED_OUT)
    borrower = Borrower.objects.create(username="status-reader", first_name="Status", last_name="Reader")
    Loan.objects.create(copy=copy, borrower=borrower)

    response = logged_in_client.post(
        reverse("copy_edit", args=[copy.id]),
        {"shelf_location": "New shelf", "condition": Copy.Condition.WORN, "status": Copy.Status.AVAILABLE},
    )

    assert response.status_code == 302
    copy.refresh_from_db()
    assert copy.shelf_location == "New shelf"
    assert copy.condition == Copy.Condition.WORN
    assert copy.status == Copy.Status.CHECKED_OUT


@pytest.mark.django_db
def test_staff_can_delete_one_of_multiple_copies_and_its_returned_history(logged_in_client):
    book = Book.objects.create(title="Several physical copies")
    first = Copy.objects.create(book=book, copy_number=1)
    second = Copy.objects.create(book=book, copy_number=2)
    borrower = Borrower.objects.create(username="copy-history", first_name="Copy", last_name="History")
    Loan.objects.create(copy=second, borrower=borrower, return_date=timezone.localdate())

    response = logged_in_client.post(reverse("delete_copy", args=[second.id]), follow=True)

    assert response.status_code == 200
    assert Book.objects.filter(pk=book.id).exists()
    assert Copy.objects.filter(pk=first.id).exists()
    assert not Copy.objects.filter(pk=second.id).exists()
    assert not Loan.objects.filter(copy_id=second.id).exists()
    assert b"Deleted copy #2 of Several physical copies" in response.content


@pytest.mark.django_db
def test_checked_out_copy_cannot_be_deleted(logged_in_client):
    book = Book.objects.create(title="Loaned duplicate")
    Copy.objects.create(book=book, copy_number=1)
    loaned = Copy.objects.create(book=book, copy_number=2, status=Copy.Status.CHECKED_OUT)
    borrower = Borrower.objects.create(username="copy-active", first_name="Active", last_name="Copy")
    Loan.objects.create(copy=loaned, borrower=borrower)

    response = logged_in_client.post(reverse("delete_copy", args=[loaned.id]), follow=True)

    assert response.status_code == 200
    assert Copy.objects.filter(pk=loaned.id).exists()
    assert b"cannot be deleted while it is checked out" in response.content


@pytest.mark.django_db
def test_last_copy_must_be_deleted_with_book(logged_in_client):
    book = Book.objects.create(title="Only physical copy")
    copy = Copy.objects.create(book=book, copy_number=1)

    response = logged_in_client.post(reverse("delete_copy", args=[copy.id]), follow=True)

    assert response.status_code == 200
    assert Copy.objects.filter(pk=copy.id).exists()
    assert b"last copy cannot be deleted separately" in response.content


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
def test_public_circulation_does_not_embed_borrower_records(client):
    borrower = Borrower.objects.create(
        username="private-student",
        first_name="Private",
        last_name="Student",
        email="private@example.org",
    )

    response = client.get(reverse("photo_circulation"))

    assert response.status_code == 200
    assert borrower.full_name.encode() not in response.content
    assert borrower.email.encode() not in response.content
    assert borrower.qr_code.encode() not in response.content
    assert b'role="combobox"' in response.content


@pytest.mark.django_db
def test_borrower_search_is_limited_and_returns_only_public_identity_fields(client):
    for index in range(10):
        Borrower.objects.create(
            username=f"reader-{index}",
            first_name="Reader",
            last_name=f"Student {index}",
            email=f"reader-{index}@example.org",
        )

    too_short = client.get(reverse("circulation_borrower_search"), {"q": "r", "action": "checkout"})
    response = client.get(reverse("circulation_borrower_search"), {"q": "reader", "action": "checkout"})

    assert too_short.json() == {"results": []}
    results = response.json()["results"]
    assert len(results) == 8
    assert set(results[0]) == {"id", "name", "username", "class_name"}
    assert "email" not in response.content.decode()
    assert "BORROWER:" not in response.content.decode()


@pytest.mark.django_db
def test_return_search_includes_inactive_borrower_with_active_loan(client):
    book = Book.objects.create(title="Outstanding inactive loan")
    copy = Copy.objects.create(book=book, copy_number=1, status=Copy.Status.CHECKED_OUT)
    borrower = Borrower.objects.create(username="former-reader", first_name="Former", last_name="Reader", active=False)
    Loan.objects.create(copy=copy, borrower=borrower)

    checkout = client.get(reverse("circulation_borrower_search"), {"q": "former", "action": "checkout"})
    checkin = client.get(reverse("circulation_borrower_search"), {"q": "former", "action": "checkin"})
    loans = client.get(reverse("circulation_borrower_loans", args=[borrower.id]))

    assert checkout.json() == {"results": []}
    assert checkin.json()["results"][0]["id"] == str(borrower.id)
    assert loans.json()["loans"] == [
        {
            "copy_id": str(copy.id),
            "title": book.title,
            "copy_number": 1,
            "due_date": Loan.objects.get(copy=copy).due_date.isoformat(),
            "overdue": False,
        }
    ]


@pytest.mark.django_db
def test_inactive_borrower_can_return_outstanding_loan(client):
    book = Book.objects.create(title="Inactive return")
    copy = Copy.objects.create(book=book, copy_number=1, status=Copy.Status.CHECKED_OUT)
    borrower = Borrower.objects.create(username="inactive-return", first_name="Inactive", last_name="Reader", active=False)
    Loan.objects.create(copy=copy, borrower=borrower)

    response = client.post(
        reverse("photo_circulation"),
        {"action": "checkin", "borrower": str(borrower.id), "return_copies": [str(copy.id)]},
    )

    assert response.status_code == 200
    assert response.context["confirmation"] is True


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
    assert response.context["copies"] == [copy]


@pytest.mark.django_db
def test_manual_checkout_choices_show_only_useful_metadata_for_available_copies():
    book = Book.objects.create(title="Clean option", authors="Named Contributor", isbn13="9780316381994")
    available = Copy.objects.create(book=book, copy_number=1)
    Copy.objects.create(book=book, copy_number=2, shelf_location="Blue-4", status=Copy.Status.CHECKED_OUT)

    choices = list(PhotoCirculationForm().fields["manual_copy"].choices)

    assert [value for value, _label in choices] == ["", available.id]
    label = choices[1][1]
    assert label == "Clean option - Named Contributor - Copy #1 - ISBN 9780316381994"
    assert "no shelf" not in label.lower()
    assert "available" not in label.lower()


@pytest.mark.django_db
def test_borrower_can_checkout_multiple_books_in_one_atomic_basket(client):
    borrower = Borrower.objects.create(username="basket-reader", first_name="Basket", last_name="Reader")
    first = Copy.objects.create(book=Book.objects.create(title="First basket book"), copy_number=1)
    second = Copy.objects.create(book=Book.objects.create(title="Second basket book"), copy_number=1)

    first_review = client.post(
        reverse("photo_circulation"),
        {"action": "checkout", "borrower": str(borrower.id), "manual_copy": str(first.id)},
    )
    add_another = client.post(
        reverse("photo_circulation"),
        {"confirmation_token": first_review.context["confirmation_token"], "intent": "add_another"},
    )
    second_review = client.post(
        reverse("photo_circulation"),
        {
            "action": "checkout",
            "borrower": str(borrower.id),
            "manual_copy": str(second.id),
            "basket_token": add_another.context["basket_token"],
        },
    )

    assert add_another.context["resume_checkout"] is True
    assert add_another.context["basket_copies"] == [first]
    assert second_review.context["copies"] == [first, second]
    assert Loan.objects.count() == 0

    confirmed = client.post(
        reverse("photo_circulation"),
        {"confirmation_token": second_review.context["confirmation_token"], "intent": "confirm"},
        follow=True,
    )

    assert b"Checked out 2 books to Basket Reader." in confirmed.content
    assert Loan.objects.filter(borrower=borrower, copy__in=[first, second], return_date__isnull=True).count() == 2


@pytest.mark.django_db
def test_multi_book_checkout_rolls_back_if_one_copy_becomes_unavailable(client):
    borrower = Borrower.objects.create(username="atomic-reader", first_name="Atomic", last_name="Reader")
    other = Borrower.objects.create(username="other-reader", first_name="Other", last_name="Reader")
    first = Copy.objects.create(book=Book.objects.create(title="Atomic first"), copy_number=1)
    second = Copy.objects.create(book=Book.objects.create(title="Atomic second"), copy_number=1)
    due_date = timezone.localdate() + timedelta(days=14)
    from django.core import signing
    from library.views import CIRCULATION_SALT

    token = signing.dumps(
        {
            "copy_ids": [str(first.id), str(second.id)],
            "borrower_id": str(borrower.id),
            "action": "checkout",
            "due_date": due_date.isoformat(),
        },
        salt=CIRCULATION_SALT,
    )
    Loan.objects.create(copy=second, borrower=other, due_date=due_date)
    second.status = Copy.Status.CHECKED_OUT
    second.save(update_fields=["status"])

    response = client.post(reverse("photo_circulation"), {"confirmation_token": token}, follow=True)

    assert b"no longer available" in response.content
    assert not Loan.objects.filter(copy=first).exists()
    first.refresh_from_db()
    assert first.status == Copy.Status.AVAILABLE


@pytest.mark.django_db
def test_checkout_basket_rejects_duplicate_and_allows_removal(client):
    borrower = Borrower.objects.create(username="edit-basket", first_name="Edit", last_name="Basket")
    first = Copy.objects.create(book=Book.objects.create(title="Keep in basket"), copy_number=1)
    second = Copy.objects.create(book=Book.objects.create(title="Remove from basket"), copy_number=1)

    first_review = client.post(
        reverse("photo_circulation"),
        {"action": "checkout", "borrower": str(borrower.id), "manual_copy": str(first.id)},
    )
    scan = client.post(
        reverse("photo_circulation"),
        {"confirmation_token": first_review.context["confirmation_token"], "intent": "add_another"},
    )
    duplicate = client.post(
        reverse("photo_circulation"),
        {
            "action": "checkout",
            "borrower": str(borrower.id),
            "manual_copy": str(first.id),
            "basket_token": scan.context["basket_token"],
        },
    )
    assert b"already in the checkout basket" in duplicate.content

    second_review = client.post(
        reverse("photo_circulation"),
        {
            "action": "checkout",
            "borrower": str(borrower.id),
            "manual_copy": str(second.id),
            "basket_token": scan.context["basket_token"],
        },
    )
    removed = client.post(
        reverse("photo_circulation"),
        {"confirmation_token": second_review.context["confirmation_token"], "remove_copy_id": str(second.id)},
    )

    assert removed.context["copies"] == [first]
    assert b"Remove from basket" not in removed.content


@pytest.mark.django_db
def test_staff_can_correct_borrower_on_active_loan(logged_in_client):
    wrong = Borrower.objects.create(username="wrong", first_name="Wrong", last_name="Student")
    correct = Borrower.objects.create(username="correct", first_name="Correct", last_name="Student", class_name="3B")
    copy = Copy.objects.create(book=Book.objects.create(title="Mistaken borrower"), copy_number=1, status=Copy.Status.CHECKED_OUT)
    loan = Loan.objects.create(copy=copy, borrower=wrong)

    page = logged_in_client.get(reverse("correct_loan_borrower", args=[loan.id]))
    response = logged_in_client.post(
        reverse("correct_loan_borrower", args=[loan.id]),
        {"borrower": str(correct.id)},
        follow=True,
    )

    assert page.status_code == 200
    assert b"wrong - Wrong Student" in page.content
    assert b"correct - Correct Student - 3B" in page.content
    assert b"Changed the borrower" in response.content
    loan.refresh_from_db()
    assert loan.borrower == correct


@pytest.mark.django_db
def test_returned_loan_cannot_be_reassigned(logged_in_client):
    borrower = Borrower.objects.create(username="returned", first_name="Returned", last_name="Reader")
    copy = Copy.objects.create(book=Book.objects.create(title="Already returned"), copy_number=1)
    loan = Loan.objects.create(copy=copy, borrower=borrower, return_date=timezone.localdate())

    response = logged_in_client.get(reverse("correct_loan_borrower", args=[loan.id]))

    assert response.status_code == 404


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
