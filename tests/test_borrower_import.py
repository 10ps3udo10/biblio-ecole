import pytest
from django.urls import reverse

from library.borrower_import import import_borrower_rows, preview_borrower_rows
from library.models import Borrower


pytestmark = pytest.mark.django_db


def test_preview_holds_back_existing_and_in_file_duplicates():
    existing = Borrower.objects.create(school_id="S-001", first_name="Ana", last_name="Garcia")
    preview = preview_borrower_rows([
        {"First name": "Ana", "Last name": "Garcia", "School ID": "different"},
        {"First name": "Other", "Last name": "Person", "School ID": "s-001"},
        {"First name": "New", "Last name": "Reader", "School ID": "S-002"},
        {"First name": "New", "Last name": "Reader", "School ID": "S-003"},
    ])

    assert len(preview.rows) == 1
    assert len(preview.duplicates) == 3
    assert existing.borrower_id in preview.duplicates[0]["reason"]
    assert "already assigned" in preview.duplicates[1]["reason"]
    assert "more than once" in preview.duplicates[2]["reason"]


def test_create_only_import_never_changes_existing_borrower():
    existing = Borrower.objects.create(school_id="S-001", first_name="Ana", last_name="Garcia")
    result = import_borrower_rows([
        {"First name": "Changed", "Last name": "Name", "School ID": "S-001", "Email": "changed@example.org"},
        {"First name": "New", "Last name": "Reader", "School ID": "S-002"},
    ])

    existing.refresh_from_db()
    assert result.created == 1
    assert len(result.duplicates) == 1
    assert existing.full_name == "Ana Garcia"
    assert existing.email == ""
    assert Borrower.objects.get(school_id="S-002").borrower_id.startswith("B")


def test_import_confirmation_requires_a_preview_for_the_same_staff_user(client, django_user_model):
    first = django_user_model.objects.create_user(username="first", is_staff=True)
    second = django_user_model.objects.create_user(username="second", is_staff=True)
    client.force_login(first)
    response = client.post(reverse("import_borrowers"), {"action": "confirm"})
    assert response.status_code == 200
    assert b"preview expired" in response.content

    session = client.session
    session["borrower_import_preview"] = {
        "user_id": first.pk,
        "rows": [{"First name": "New", "Last name": "Reader"}],
    }
    session.save()
    client.force_login(second)
    response = client.post(reverse("import_borrowers"), {"action": "confirm"})
    assert b"preview expired" in response.content
    assert not Borrower.objects.filter(first_name="New", last_name="Reader").exists()
