import pytest
from django.urls import reverse

from library.models import Book

pytestmark = pytest.mark.django_db


@pytest.fixture
def catalog_client(client, django_user_model):
    client.force_login(django_user_model.objects.create_user(username="operator", is_staff=True))
    return client


def test_thousand_titles_render_only_one_page(catalog_client):
    Book.objects.bulk_create([Book(title=f"Book {index:04}", isbn13="9780306406157") for index in range(1000)])
    response = catalog_client.get(reverse("book_list"))
    page = response.context["books"]
    assert page.paginator.count == 1000
    assert page.paginator.num_pages == 20
    assert len(page) == 50
    assert page[0].title == "Book 0000"
    assert page[-1].title == "Book 0049"
    assert response.content.count(b'class="table-select cover-book-select"') == 50
    assert b"1 to 50 of 1000 titles" in response.content
    assert b"Book 0050" not in response.content


def test_search_sort_and_stable_page_boundaries(catalog_client):
    Book.objects.bulk_create([Book(title=f"Match {index:03}", authors="Same author") for index in range(105)])
    Book.objects.create(title="Other")
    url = reverse("book_list")
    response = catalog_client.get(url, {"q": "Match", "sort": "author", "direction": "desc", "page": 2})
    page = response.context["books"]
    assert page.number == 2 and page.paginator.count == 105
    assert page[0].title == "Match 050" and page[-1].title == "Match 099"
    assert b"q=Match&amp;sort=author&amp;direction=desc&amp;page=3" in response.content
    last = catalog_client.get(url, {"q": "Match", "page": 3}).context["books"]
    assert len(last) == 5
    assert not set(book.pk for book in page) & set(book.pk for book in last)


@pytest.mark.parametrize("requested,expected", [("invalid", 1), ("999", 2), ("-1", 2)])
def test_invalid_page_falls_back(catalog_client, requested, expected):
    Book.objects.bulk_create([Book(title=f"Book {index}") for index in range(51)])
    assert catalog_client.get(reverse("book_list"), {"page": requested}).context["books"].number == expected


def test_empty_catalog(catalog_client):
    response = catalog_client.get(reverse("book_list"))
    assert response.status_code == 200
    assert b"0 titles" in response.content
    assert b"No books found" in response.content
    assert b'aria-label="Catalog pages"' not in response.content
