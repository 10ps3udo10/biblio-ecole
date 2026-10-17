import pytest
from django.urls import reverse

from library.models import Book, Borrower, Copy, SchoolClass


@pytest.fixture
def staff_client(client, django_user_model):
    django_user_model.objects.create_user(username="maitresse", password="secret", is_staff=True)
    assert client.login(username="maitresse", password="secret")
    return client


@pytest.mark.django_db
def test_class_sheet_lists_each_active_student_with_name_and_qr(staff_client):
    cp = SchoolClass.objects.create(name="CP")
    students = [Borrower.objects.create(first_name=f"Élève{index}", last_name=f"Nom{index:02d}", school_class=cp) for index in range(26)]
    Borrower.objects.create(first_name="Parti", last_name="Archive", school_class=cp, active=False)

    response = staff_client.get(reverse("class_label_sheet", args=[cp.pk]))

    content = response.content.decode()
    assert response.status_code == 200
    assert response.context["label_count"] == 26
    assert [len(sheet) for sheet in response.context["sheets"]] == [24, 2]
    assert "Élève0" in content and "NOM00" in content and "Parti" not in content
    assert content.count("<svg") == 26


@pytest.mark.django_db
def test_student_qr_contains_only_the_technical_identifier(staff_client):
    cp = SchoolClass.objects.create(name="CP")
    student = Borrower.objects.create(first_name="Lina", last_name="Martin", school_class=cp)

    assert student.qr_code == f"BORROWER:{student.pk}"
    assert "Lina" not in student.qr_code and "Martin" not in student.qr_code


@pytest.mark.django_db
def test_sheet_can_start_on_a_partially_used_page(staff_client):
    cp = SchoolClass.objects.create(name="CE1")
    Borrower.objects.create(first_name="Lina", last_name="Martin", school_class=cp)

    response = staff_client.get(reverse("class_label_sheet", args=[cp.pk]), {"start": 5})

    sheet = response.context["sheets"][0]
    assert sheet[:4] == [None] * 4 and sheet[4]["title"] == "Lina"


@pytest.mark.django_db
def test_copy_sheet_prints_every_copy_of_a_book_except_removed_ones(staff_client):
    book = Book.objects.create(title="Le Gruffalo")
    Copy.objects.create(book=book, copy_number=1)
    Copy.objects.create(book=book, copy_number=2)
    Copy.objects.create(book=book, copy_number=3, status=Copy.Status.ARCHIVED)

    response = staff_client.get(reverse("copy_label_sheet"), {"book": book.pk})

    assert response.context["label_count"] == 2
    assert "Exemplaire n°2" in response.content.decode()


@pytest.mark.django_db
def test_copy_sheet_ignores_invalid_ids(staff_client):
    response = staff_client.get(reverse("copy_label_sheet"), {"copy": ["pas-un-uuid"]})

    assert response.status_code == 200
    assert response.context["label_count"] == 0
