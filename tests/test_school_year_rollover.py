import pytest
from django.urls import reverse
from django.utils import timezone

from library.models import Book, Borrower, Copy, Loan, SchoolClass, SchoolYear
from library.school_year import LEAVES_SCHOOL, next_year_defaults, open_loans_from_previous_years, start_new_school_year


@pytest.fixture
def school(db):
    SchoolClass.objects.all().delete()
    year = SchoolYear.current()
    cp = SchoolClass.objects.create(name="CP")
    cm2 = SchoolClass.objects.create(name="CM2")
    lina = Borrower.objects.create(first_name="Lina", last_name="Martin", school_class=cp)
    noe = Borrower.objects.create(first_name="Noé", last_name="Petit", school_class=cm2)
    book = Book.objects.create(title="Le Petit Prince")
    copy = Copy.objects.create(book=book, copy_number=1, status=Copy.Status.CHECKED_OUT)
    loan = Loan.objects.create(copy=copy, borrower=noe)
    return {"year": year, "cp": cp, "cm2": cm2, "lina": lina, "noe": noe, "book": book, "loan": loan}


def test_next_year_defaults_follow_current_year(school):
    name, start, end = next_year_defaults()
    first = school["year"].start_date.year + 1

    assert name == f"{first}-{first + 1}"
    assert start.year == first and end.year == first + 1


def test_rollover_moves_students_archives_leavers_and_keeps_history(school):
    name, start, end = next_year_defaults()

    new_year, summary = start_new_school_year(
        name=name, start_date=start, end_date=end,
        class_names=["CE1", "CM2"],
        placements={str(school["lina"].pk): "CE1", str(school["noe"].pk): LEAVES_SCHOOL},
    )

    assert SchoolYear.current() == new_year
    school["year"].refresh_from_db()
    assert not school["year"].is_current

    lina = Borrower.objects.get(pk=school["lina"].pk)
    assert lina.school_class.name == "CE1" and lina.school_class.school_year == new_year
    assert lina.qr_code == school["lina"].qr_code

    noe = Borrower.objects.get(pk=school["noe"].pk)
    assert not noe.active and noe.archived_on == timezone.localdate()
    assert noe.school_class == school["cm2"]

    assert not SchoolClass.objects.get(pk=school["cp"].pk).active
    assert SchoolClass.objects.filter(school_year=new_year).count() == 2
    assert Book.objects.filter(pk=school["book"].pk).exists()

    loan = Loan.objects.get(pk=school["loan"].pk)
    assert loan.return_date is None and loan.school_class == school["cm2"] and loan.school_year == school["year"]
    assert summary["open_loans"] == 1
    assert list(open_loans_from_previous_years()) == [loan]


def test_rollover_rejects_unknown_destination_class(school):
    name, start, end = next_year_defaults()

    with pytest.raises(ValueError):
        start_new_school_year(name=name, start_date=start, end_date=end, class_names=["CE1"], placements={str(school["lina"].pk): "CE2"})

    assert SchoolYear.current() == school["year"]


def test_rollover_rejects_existing_year_name(school):
    with pytest.raises(ValueError):
        start_new_school_year(name=school["year"].name, start_date=school["year"].start_date, end_date=school["year"].end_date, class_names=["CE1"], placements={})


@pytest.fixture
def staff_client(client, django_user_model):
    django_user_model.objects.create_user(username="maitresse", password="secret", is_staff=True)
    assert client.login(username="maitresse", password="secret")
    return client


def test_rollover_wizard_end_to_end(school, staff_client):
    name, start, end = next_year_defaults()
    url = reverse("school_year_new")

    first = staff_client.get(url)
    assert first.status_code == 200
    assert "CM2" in first.content.decode()

    placements_page = staff_client.post(url, {"step": "classes", "name": name, "start_date": start, "end_date": end, "class_names": "CE1\nCM2"})
    content = placements_page.content.decode()
    assert placements_page.status_code == 200
    assert "Lina" in content and "Le Petit Prince" in content

    done = staff_client.post(url, {
        "step": "confirm", "name": name, "start_date": start, "end_date": end, "class_names": "CE1\nCM2",
        f"placement_{school['lina'].pk}": "CE1",
        f"placement_{school['noe'].pk}": LEAVES_SCHOOL,
    }, follow=True)

    assert done.status_code == 200
    assert SchoolYear.current().name == name
    assert "Le Petit Prince" in done.content.decode()
    assert Borrower.objects.get(pk=school["lina"].pk).school_class.name == "CE1"


@pytest.mark.parametrize("old, new_classes, expected", [
    ("CP", ["CE1", "CE2"], "CE1"),
    ("GS-CP", ["CP", "CE1"], "CE1"),
    ("Classe de PS", ["MS", "GS"], "MS"),
    ("CM2", ["CM1", "CM2"], LEAVES_SCHOOL),
    ("Les Lutins", ["CE1"], ""),
    ("CE2", ["CP"], ""),
])
def test_suggested_destination_follows_french_levels(old, new_classes, expected):
    from library.views import _suggested_destination

    assert _suggested_destination(old, new_classes) == expected


def test_dashboard_flags_open_loans_from_previous_years(school, staff_client):
    name, start, end = next_year_defaults()
    start_new_school_year(name=name, start_date=start, end_date=end, class_names=["CE1"], placements={})

    response = staff_client.get(reverse("dashboard"))

    assert response.context["previous_year_open_loans"] == 1
    assert "Emprunts non rendus à récupérer" in response.content.decode()
