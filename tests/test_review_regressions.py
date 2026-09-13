import sqlite3
import uuid
from types import SimpleNamespace

import pytest
from django.urls import reverse
from django.utils import timezone

from library.catalog_import import import_catalog_rows
from library.forms import CopyForm, CopyEditForm
from library.models import Book, Borrower, Copy, Loan
from library.urls import urlpatterns


@pytest.mark.django_db
def test_demoted_staff_cannot_access_management_routes(client, django_user_model):
    account = django_user_model.objects.create_user(username="staff", is_staff=True)
    client.force_login(account)
    account.is_staff = False
    account.save()

    public = {
        "photo_circulation", "circulation_alias",
        "circulation_borrower_search", "circulation_borrower_loans",
        "public_catalog", "public_book",
    }
    for route in urlpatterns:
        if route.name in public:
            continue
        kwargs = {
            key: (uuid.uuid4() if converter.__class__.__name__ == "UUIDConverter"
                  else 1 if converter.__class__.__name__ == "IntConverter" else "copy")
            for key, converter in route.pattern.converters.items()
        }
        url = reverse(route.name, kwargs=kwargs)
        for response in (client.get(url), client.post(url)):
            assert response.status_code == 302, route.name
            assert response.url.startswith("/staff/login/"), route.name


@pytest.mark.django_db
def test_import_different_isbn_keeps_editions_separate():
    original = Book.objects.create(title="Same title", isbn13="9780306406157")
    result = import_catalog_rows([{"Title": "Same title", "ISBN": "9780140328721"}])
    assert result.titles_created == 1
    assert not original.copies.exists()
    assert Book.objects.get(isbn13="9780140328721").copies.count() == 1


@pytest.mark.django_db
def test_import_can_enrich_an_unidentified_edition():
    original = Book.objects.create(title="Same title")
    result = import_catalog_rows([{"Title": "Same title", "ISBN": "9780140328721"}])
    original.refresh_from_db()
    assert result.titles_created == 0
    assert original.isbn13 == "9780140328721"
    assert original.copies.count() == 1


@pytest.mark.django_db
def test_copy_forms_reject_checkout_without_a_loan():
    copy = Copy.objects.create(book=Book.objects.create(title="Book"), copy_number=1)
    data = {"shelf_location": "A", "condition": "good", "status": "checked_out"}
    for form in (CopyForm(data), CopyEditForm(data, instance=copy)):
        assert not form.is_valid()
        assert "status" in form.errors


@pytest.mark.django_db
@pytest.mark.parametrize("action", ["checkout", "return_copy"])
def test_staff_circulation_rolls_back_when_copy_save_fails(client, django_user_model, monkeypatch, action):
    staff = django_user_model.objects.create_user(username="staff", is_staff=True)
    client.force_login(staff)
    borrower = Borrower.objects.create(first_name="Reader", last_name="One")
    copy = Copy.objects.create(book=Book.objects.create(title="Book"), copy_number=1)
    if action == "return_copy":
        loan = Loan.objects.create(copy=copy, borrower=borrower)
        copy.status = Copy.Status.CHECKED_OUT
        copy.save()

    def fail_save(*args, **kwargs):
        raise RuntimeError("Simulated write failure")

    monkeypatch.setattr(Copy, "save", fail_save)
    with pytest.raises(RuntimeError, match="Simulated write failure"):
        client.post(reverse(action), {
            "copy_code": copy.qr_payload,
            "borrower_code": borrower.qr_payload,
            "due_date": timezone.localdate().isoformat(),
        })
    copy.refresh_from_db()
    if action == "checkout":
        assert not Loan.objects.exists()
        assert copy.status == Copy.Status.AVAILABLE
    else:
        loan.refresh_from_db()
        assert loan.return_date is None
        assert copy.status == Copy.Status.CHECKED_OUT


@pytest.mark.django_db
def test_backup_includes_wal_data_and_is_independent_of_later_writes(
    client, django_user_model, settings, tmp_path, monkeypatch
):
    account = django_user_model.objects.create_user(username="staff", is_staff=True)
    client.force_login(account)
    database = tmp_path / "source.sqlite3"
    source = sqlite3.connect(database)
    try:
        source.execute("PRAGMA journal_mode=WAL")
        source.execute("CREATE TABLE records (title TEXT)")
        source.execute("INSERT INTO records VALUES ('Before backup')")
        source.commit()
        # Only the backup view reads this setting; Django's existing test
        # connection remains in place for authentication.
        monkeypatch.setattr("library.views.settings", SimpleNamespace(DATABASES={"default": {
            **settings.DATABASES["default"], "NAME": str(database),
        }}))
        response = client.get(reverse("backup_sqlite"))
        assert response.status_code == 200
        source.execute("INSERT INTO records VALUES ('After backup')")
        source.commit()
        downloaded = tmp_path / "download.sqlite3"
        downloaded.write_bytes(b"".join(response.streaming_content))
        response.close()
        snapshot = sqlite3.connect(downloaded)
        try:
            assert snapshot.execute("PRAGMA integrity_check").fetchone() == ("ok",)
            assert snapshot.execute("SELECT title FROM records").fetchall() == [("Before backup",)]
        finally:
            snapshot.close()
    finally:
        source.close()
