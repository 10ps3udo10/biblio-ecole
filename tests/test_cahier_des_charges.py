"""Critères de validation du cahier des charges (section 11, tests 1 à 8).

Chaque test rejoue le scénario par les écrans de l'application, comme le ferait
l'enseignante : formulaires, écran de prêt à la douchette, fiches et sauvegarde.
"""

import csv
import io
import sqlite3

import pytest
from django.db import connection
from django.urls import reverse
from django.utils import timezone

from library.models import Book, Borrower, Copy, Loan, SchoolClass, SchoolYear
from library.school_year import LEAVES_SCHOOL, next_year_defaults
from tools.library_backup import create_backup, restore_backup


@pytest.fixture
def maitresse(client, django_user_model):
    django_user_model.objects.create_user(username="maitresse", password="secret", is_staff=True)
    assert client.login(username="maitresse", password="secret")
    return client


@pytest.fixture
def ecole(db):
    cp = SchoolClass.objects.create(name="CP")
    lina = Borrower.objects.create(first_name="Lina", last_name="Martin", school_class=cp)
    book = Book.objects.create(title="Le Petit Prince", authors="Antoine de Saint-Exupéry")
    copy = Copy.objects.create(book=book, copy_number=1)
    return {"cp": cp, "lina": lina, "book": book, "copy": copy}


def scan(client, code):
    return client.post(reverse("desk"), {"code": code})


def emprunter(client, borrower, copy):
    scan(client, borrower.qr_code)
    scan(client, copy.qr_code)
    return Loan.objects.get(copy=copy, return_date__isnull=True)


def test_1_ajout_d_un_livre(maitresse):
    """Un livre est créé, un QR code lui est attribué et sa fiche est retrouvable par recherche."""
    response = maitresse.post(reverse("book_create"), {
        "title": "Max et les Maximonstres", "authors": "Maurice Sendak",
        "first_copy_shelf": "Albums", "first_copy_condition": Copy.Condition.GOOD,
    })

    assert response.status_code == 302
    copy = Book.objects.get(title="Max et les Maximonstres").copies.get()
    assert copy.qr_code == f"COPY:{copy.pk}"
    label = maitresse.get(reverse("label", args=["copy", copy.pk]))
    assert "<svg" in label.content.decode()
    found = maitresse.get(reverse("book_list"), {"q": "maximonstres"})
    assert "Max et les Maximonstres" in found.content.decode()


def test_2_emprunt_par_scan(maitresse, ecole):
    """L'élève est identifié par son QR code, puis le livre est scanné : emprunt enregistré à la date du jour."""
    loan = emprunter(maitresse, ecole["lina"], ecole["copy"])

    assert loan.borrower == ecole["lina"]
    assert loan.checkout_date == timezone.localdate()
    assert loan.school_class == ecole["cp"]
    assert Copy.objects.get(pk=ecole["copy"].pk).status == Copy.Status.CHECKED_OUT


def test_3_recherche_d_un_emprunteur(maitresse, ecole):
    """La recherche du titre du livre permet de retrouver l'élève qui le détient."""
    emprunter(maitresse, ecole["lina"], ecole["copy"])

    response = maitresse.get(reverse("desk"), {"q": "petit prince"})

    assert "emprunté par Lina Martin" in response.content.decode()


def test_4_consultation_des_emprunts_d_un_eleve(maitresse, ecole):
    """La fiche de l'élève affiche tous les livres qu'il n'a pas encore rendus."""
    second = Copy.objects.create(book=Book.objects.create(title="Le Gruffalo"), copy_number=1)
    returned = Copy.objects.create(book=Book.objects.create(title="Petit Ours Brun"), copy_number=1)
    emprunter(maitresse, ecole["lina"], ecole["copy"])
    emprunter(maitresse, ecole["lina"], second)
    Loan.objects.create(copy=returned, borrower=ecole["lina"], return_date=timezone.localdate())

    response = maitresse.get(reverse("borrower_detail", args=[ecole["lina"].pk]))

    assert {loan.copy for loan in response.context["active_loans"]} == {ecole["copy"], second}
    content = response.content.decode()
    assert "Le Petit Prince" in content and "Le Gruffalo" in content


def test_5_retour(maitresse, ecole):
    """Le retour est enregistré, le livre redevient disponible et l'historique est conservé."""
    loan = emprunter(maitresse, ecole["lina"], ecole["copy"])
    session = maitresse.session
    session["desk"]["last"] = None
    session.save()

    scan(maitresse, ecole["copy"].qr_code)

    loan.refresh_from_db()
    assert loan.return_date == timezone.localdate()
    assert Copy.objects.get(pk=ecole["copy"].pk).status == Copy.Status.AVAILABLE
    history = maitresse.get(reverse("borrower_detail", args=[ecole["lina"].pk])).context["loan_history"]
    assert loan in list(history)


def test_6_changement_de_classe(maitresse, ecole):
    """Un élève change de classe sans perdre son identité, son QR code ni son historique."""
    loan = emprunter(maitresse, ecole["lina"], ecole["copy"])
    ce1 = SchoolClass.objects.create(name="CE1")
    before = Borrower.objects.get(pk=ecole["lina"].pk)

    response = maitresse.post(reverse("borrower_edit", args=[before.pk]), {
        "first_name": "Lina", "last_name": "Martin", "school_role": "student",
        "school_class": ce1.pk, "active": "on",
    })

    assert response.status_code == 302
    after = Borrower.objects.get(pk=before.pk)
    assert after.school_class == ce1
    assert (after.borrower_id, after.qr_code) == (before.borrower_id, before.qr_code)
    assert list(after.loans.all()) == [loan]
    loan.refresh_from_db()
    assert loan.school_class == ecole["cp"]
    assert scan(maitresse, after.qr_code).context["borrower"] == after


def test_7_nouvelle_annee_scolaire(maitresse, ecole):
    """Les nouvelles classes sont créées sans supprimer le catalogue ni les historiques précédents."""
    loan = emprunter(maitresse, ecole["lina"], ecole["copy"])
    leaver = Borrower.objects.create(first_name="Noé", last_name="Petit", school_class=ecole["cp"])
    old_year = SchoolYear.current()
    name, start, end = next_year_defaults()

    maitresse.post(reverse("school_year_new"), {
        "step": "confirm", "name": name, "start_date": start, "end_date": end, "class_names": "CE1\nCP",
        f"placement_{ecole['lina'].pk}": "CE1", f"placement_{leaver.pk}": LEAVES_SCHOOL,
    })

    new_year = SchoolYear.current()
    assert new_year.name == name and new_year != old_year
    assert set(SchoolClass.objects.filter(school_year=new_year).values_list("name", flat=True)) == {"CE1", "CP"}
    assert SchoolClass.objects.filter(pk=ecole["cp"].pk, school_year=old_year).exists()
    assert Book.objects.filter(pk=ecole["book"].pk, archived_on__isnull=True).exists()
    assert Borrower.objects.get(pk=ecole["lina"].pk).school_class.name == "CE1"
    assert not Borrower.objects.get(pk=leaver.pk).active
    loan.refresh_from_db()
    assert loan.return_date is None and loan.school_year == old_year and loan.school_class == ecole["cp"]
    assert loan in maitresse.get(reverse("school_year_overview")).context["open_loans"]


@pytest.mark.filterwarnings("ignore:Overriding setting DATABASES")
@pytest.mark.django_db(transaction=True)
def test_8_sauvegarde_export_et_restauration(maitresse, tmp_path, settings):
    """Les données peuvent être exportées et restaurées en cas de problème."""
    cp = SchoolClass.objects.create(name="CP")
    lina = Borrower.objects.create(first_name="Lina", last_name="Martin", school_class=cp)
    copy = Copy.objects.create(book=Book.objects.create(title="Le Petit Prince"), copy_number=1)
    emprunter(maitresse, lina, copy)

    export = maitresse.get(reverse("export_books_csv"))
    rows = list(csv.DictReader(io.StringIO(export.content.decode())))
    assert [row["Title"] for row in rows] == ["Le Petit Prince"]

    # The live library database is a file on the school PC; mirror the test database into one.
    live = tmp_path / "db.sqlite3"
    connection.ensure_connection()
    with sqlite3.connect(live) as target:
        connection.connection.backup(target)
    settings.DATABASES = {**settings.DATABASES, "default": {**settings.DATABASES["default"], "NAME": str(live)}}

    download = maitresse.get(reverse("backup_sqlite"))
    downloaded = tmp_path / "telechargement.sqlite3"
    downloaded.write_bytes(b"".join(download.streaming_content))

    media = tmp_path / "media"
    media.mkdir()
    (tmp_path / "sauvegardes").mkdir()
    archive = create_backup(downloaded, media, tmp_path / "sauvegardes")
    restored = restore_backup(archive, tmp_path / "restauration")

    with sqlite3.connect(restored / "db.sqlite3") as db:
        assert ("Lina", "Martin") in db.execute("SELECT first_name, last_name FROM library_borrower").fetchall()
        assert db.execute("SELECT title FROM library_book").fetchall() == [("Le Petit Prince",)]
        assert db.execute("SELECT COUNT(*) FROM library_loan WHERE return_date IS NULL").fetchone() == (1,)
