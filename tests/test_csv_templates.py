import csv
from io import StringIO

import pytest
from django.core.files.uploadedfile import SimpleUploadedFile
from django.urls import reverse

from library.csv_templates import csv_columns
from library.models import Book, Borrower

pytestmark = pytest.mark.django_db


@pytest.mark.parametrize("kind", ["books", "borrowers"])
def test_template_download_and_import_round_trip(client, django_user_model, kind):
    url = reverse("download_csv_template", args=[kind])
    assert client.get(url).status_code == 302
    client.force_login(django_user_model.objects.create_user(username="operator", is_staff=True))
    response = client.get(url)
    assert response.status_code == 200
    assert f'shelf-school-{kind}-template.csv' in response["Content-Disposition"]
    records = list(csv.reader(StringIO(response.content.decode("utf-8-sig"))))
    assert records == [csv_columns(kind)["headers"]]
    assert client.post(url).status_code == 405
    row = {header: "" for header in records[0]}
    row.update({"Title": "Template book"} if kind == "books" else {
        "Borrower ID": "template-reader", "First name": "Sam", "Last name": "Reader",
    })
    output = StringIO()
    writer = csv.DictWriter(output, fieldnames=records[0])
    writer.writeheader()
    writer.writerow(row)
    imported = client.post(reverse(f"import_{kind}"), {
        "csv_file": SimpleUploadedFile("template.csv", output.getvalue().encode("utf-8")),
    })
    assert imported.status_code == 302
    if kind == "books":
        assert Book.objects.filter(title="Template book").exists()
        exported = client.get(reverse("export_books_csv"))
        assert set(next(csv.reader(StringIO(exported.content.decode())))) == set(records[0])
    else:
        assert Borrower.objects.filter(username="template-reader", staff_account__isnull=True).exists()


@pytest.mark.parametrize("kind", ["books", "borrowers"])
def test_field_reference_is_preserved_on_upload_errors(client, django_user_model, kind):
    client.force_login(django_user_model.objects.create_user(username="operator", is_staff=True))
    response = client.post(reverse(f"import_{kind}"), {})
    assert response.status_code == 200
    assert b"Download CSV template" in response.content
    assert b"Required columns" in response.content
    assert b"Optional columns" in response.content
    assert response.context["headers"] == csv_columns(kind)["headers"]


def test_unknown_template_is_not_downloadable(client, django_user_model):
    client.force_login(django_user_model.objects.create_user(username="operator", is_staff=True))
    assert client.get(reverse("download_csv_template", args=["unknown"])).status_code == 404
