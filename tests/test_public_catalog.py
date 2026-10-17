import pytest
from django.urls import reverse
from library.models import Book, Borrower, Copy, Loan

pytestmark = pytest.mark.django_db


def test_missing_shelf_has_clear_label(client):
    book = Book.objects.create(title="Book without a shelf")
    Copy.objects.create(book=book, copy_number=1, shelf_location="")
    for url in [reverse("public_catalog"), reverse("public_book", args=[book.pk])]:
        response = client.get(url)
        assert "Aucune étagère attribuée".encode() in response.content
        assert "Emplacement non défini".encode() not in response.content


def test_public_catalog_shows_status_and_location_without_borrower_data(client):
    book = Book.objects.create(title="The library book", authors="A Writer", isbn13="9780306406157", review_notes="PRIVATE NOTES")
    available = Copy.objects.create(book=book, copy_number=1, shelf_location="Green section")
    checked_out = Copy.objects.create(book=book, copy_number=2, status="checked_out", shelf_location="Blue section")
    borrower = Borrower.objects.create(first_name="PRIVATE BORROWER", last_name="NAME", email="private@example.org")
    Loan.objects.create(copy=checked_out, borrower=borrower)
    for url in [reverse("public_catalog"), reverse("public_book", args=[book.pk])]:
        response = client.get(url)
        assert response.status_code == 200
        assert b"The library book" in response.content
        assert b"PRIVATE BORROWER" not in response.content
        assert b"private@example.org" not in response.content
        assert b"PRIVATE NOTES" not in response.content
        assert borrower.qr_payload.encode() not in response.content
        assert "Historique des emprunts".encode() not in response.content
    detail = client.get(reverse("public_book", args=[book.pk]))
    assert b"Green section" in detail.content
    assert "Emprunté".encode() in detail.content
    assert available.qr_payload.encode() not in detail.content
    assert client.get(reverse("copy_detail", args=[available.pk])).status_code == 302


def test_catalog_search_counts_and_archived_copies(client):
    book = Book.objects.create(title="Book", isbn13="9780306406157")
    Copy.objects.create(book=book, copy_number=1, shelf_location="Green")
    Copy.objects.create(book=book, copy_number=2, shelf_location="Green")
    archived = Book.objects.create(title="Archived book")
    Copy.objects.create(book=archived, copy_number=1, status="archived")
    response = client.get(reverse("public_catalog"), {"q": "Green"})
    assert response.context["catalog"].paginator.count == 1
    assert response.context["catalog"][0].public_available == 2
    assert client.get(reverse("public_book", args=[archived.pk])).status_code == 404
    assert client.get(reverse("public_catalog"), {"q": "978-0306406157"}).context["catalog"].paginator.count == 1
    assert client.post(reverse("public_catalog")).status_code == 405


def test_public_catalog_paginates(client):
    for index in range(25):
        Copy.objects.create(book=Book.objects.create(title=f"Book {index:02}"), copy_number=1)
    response = client.get(reverse("public_catalog"), {"page": 2, "sort": "invalid"})
    assert len(response.context["catalog"]) == 1
    assert response.context["sort"] == "title"


def test_filters_match_availability_at_selected_shelf(client):
    book = Book.objects.create(title="Different shelves", language="English")
    Copy.objects.create(book=book, copy_number=1, shelf_location="Red", status="checked_out")
    Copy.objects.create(book=book, copy_number=2, shelf_location="Green")
    url = reverse("public_catalog")
    response = client.get(url, {"available": "1", "shelf": "Red", "language": "English"})
    assert response.context["catalog"].paginator.count == 0
    response = client.get(url, {"available": "1", "shelf": "Green", "language": "English"})
    assert response.context["catalog"].paginator.count == 1
    assert response.context["catalog"][0].public_available == 1
    assert response.context["catalog"][0].public_locations == ["Green"]
    assert client.get(url, {"language": "Spanish"}).context["catalog"].paginator.count == 0


def test_pagination_preserves_filters(client):
    for index in range(25):
        Copy.objects.create(book=Book.objects.create(title=f"Book {index}", language="English"),
                            copy_number=1, shelf_location="Green & Blue")
    response = client.get(reverse("public_catalog"), {
        "q": "Book", "shelf": "Green & Blue", "language": "English",
        "available": "1", "sort": "availability", "page": "1",
    })
    from urllib.parse import parse_qs
    query = parse_qs(response.context["pagination_query"])
    assert query == {"q": ["Book"], "shelf": ["Green & Blue"], "language": ["English"],
                     "available": ["1"], "sort": ["availability"]}
