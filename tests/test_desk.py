from datetime import timedelta

import pytest
from django.urls import reverse
from django.utils import timezone

from library import desk
from library.models import Book, Borrower, Copy, Loan, SchoolClass, SchoolProfile

PC_AZERTY = str.maketrans({
    "1": "&", "2": "é", "3": '"', "4": "'", "5": "(", "6": "-", "7": "è", "8": "_", "9": "ç", "0": "à",
    "-": ")", ":": "M", "a": "q", "q": "a", "w": "z", "z": "w", "A": "Q", "Q": "A", "W": "Z", "Z": "W",
})
MAC_AZERTY = str.maketrans({
    "1": "&", "2": "é", "3": '"', "4": "'", "5": "(", "6": "§", "7": "è", "8": "!", "9": "ç", "0": "à",
    "-": ")", ":": "M", "a": "q", "q": "a", "w": "z", "z": "w", "A": "Q", "Q": "A", "W": "Z", "Z": "W",
})


@pytest.fixture
def staff_client(client, django_user_model):
    django_user_model.objects.create_user(username="maitresse", password="secret", is_staff=True)
    assert client.login(username="maitresse", password="secret")
    return client


@pytest.fixture
def school(db):
    cp = SchoolClass.objects.create(name="CP")
    lina = Borrower.objects.create(first_name="Lina", last_name="Martin", school_class=cp)
    noe = Borrower.objects.create(first_name="Noé", last_name="Petit", school_class=cp)
    book = Book.objects.create(title="Le Gruffalo")
    copy = Copy.objects.create(book=book, copy_number=1)
    return {"cp": cp, "lina": lina, "noe": noe, "book": book, "copy": copy}


def scan(client, code):
    return client.post(reverse("desk"), {"code": code})


def test_desk_requires_staff_login(client):
    response = client.get(reverse("desk"))

    assert response.status_code == 302


def test_desk_shows_a_single_focused_scan_field(staff_client):
    response = staff_client.get(reverse("desk"))

    content = response.content.decode()
    assert response.status_code == 200
    assert 'name="code"' in content and "autofocus" in content


def test_scan_student_then_book_records_loan_with_automatic_due_date(staff_client, school):
    SchoolProfile.objects.filter(pk=SchoolProfile.current().pk).update(default_loan_days=21)

    selected = scan(staff_client, school["lina"].qr_code)
    assert "Lina" in selected.content.decode()
    assert Loan.objects.count() == 0

    done = scan(staff_client, school["copy"].qr_code)

    loan = Loan.objects.get()
    assert loan.borrower == school["lina"]
    assert loan.checkout_date == timezone.localdate()
    assert loan.due_date == timezone.localdate() + timedelta(days=21)
    assert loan.school_class == school["cp"]
    assert Copy.objects.get(pk=school["copy"].pk).status == Copy.Status.CHECKED_OUT
    assert "Prêt enregistré" in done.content.decode()
    assert staff_client.session[desk.SESSION_KEY].get("borrower") is None


def test_scan_book_alone_returns_it_and_keeps_history(staff_client, school):
    scan(staff_client, school["lina"].qr_code)
    scan(staff_client, school["copy"].qr_code)
    desk_state = staff_client.session[desk.SESSION_KEY]
    desk_state["last"]["at"] -= desk.DUPLICATE_SECONDS + 1
    session = staff_client.session
    session[desk.SESSION_KEY] = desk_state
    session.save()

    response = scan(staff_client, school["copy"].qr_code)

    loan = Loan.objects.get()
    assert loan.return_date == timezone.localdate()
    assert Copy.objects.get(pk=school["copy"].pk).status == Copy.Status.AVAILABLE
    assert "Retour enregistré" in response.content.decode()


def test_double_scan_right_after_a_loan_is_ignored(staff_client, school):
    scan(staff_client, school["lina"].qr_code)
    scan(staff_client, school["copy"].qr_code)

    response = scan(staff_client, school["copy"].qr_code)

    assert Loan.objects.get().return_date is None
    assert "déjà enregistré" in response.content.decode()


def test_book_already_borrowed_by_someone_else_is_refused(staff_client, school):
    scan(staff_client, school["lina"].qr_code)
    scan(staff_client, school["copy"].qr_code)

    scan(staff_client, school["noe"].qr_code)
    response = scan(staff_client, school["copy"].qr_code)

    assert Loan.objects.count() == 1
    assert Loan.objects.get().borrower == school["lina"]
    assert "déjà emprunté par Lina" in response.content.decode()


def test_available_book_without_student_is_not_lent(staff_client, school):
    response = scan(staff_client, school["copy"].qr_code)

    assert Loan.objects.count() == 0
    assert "scannez d'abord la carte" in response.context["outcome"]["text"]


def test_archived_student_cannot_borrow(staff_client, school):
    school["noe"].active = False
    school["noe"].save()

    response = scan(staff_client, school["noe"].qr_code)

    assert "archivé" in response.content.decode()
    assert staff_client.session[desk.SESSION_KEY].get("borrower") is None


def test_student_selection_expires(staff_client, school):
    scan(staff_client, school["lina"].qr_code)
    session = staff_client.session
    state = session[desk.SESSION_KEY]
    state["borrower_at"] -= desk.BORROWER_TIMEOUT_SECONDS + 1
    session[desk.SESSION_KEY] = state
    session.save()

    scan(staff_client, school["copy"].qr_code)

    assert Loan.objects.count() == 0


def test_clear_button_forgets_the_student(staff_client, school):
    scan(staff_client, school["lina"].qr_code)

    staff_client.post(reverse("desk"), {"action": "clear"})
    scan(staff_client, school["copy"].qr_code)

    assert Loan.objects.count() == 0


@pytest.mark.parametrize("layout", [PC_AZERTY, MAC_AZERTY])
def test_codes_typed_by_a_qwerty_scanner_on_an_azerty_keyboard_are_understood(school, layout):
    garbled_copy = school["copy"].qr_code.translate(layout)
    garbled_borrower = school["lina"].qr_code.translate(layout)
    assert garbled_copy != school["copy"].qr_code

    assert desk.parse_scan(garbled_copy) == ("COPY", school["copy"].pk)
    assert desk.parse_scan(garbled_borrower) == ("BORROWER", school["lina"].pk)


def test_plain_text_is_not_a_code():
    assert desk.parse_scan("martin") is None


def test_manual_search_finds_students_by_name_and_books_by_title(staff_client, school):
    by_name = scan(staff_client, "mart")
    by_title = scan(staff_client, "gruff")

    assert school["lina"] in by_name.context["found_borrowers"]
    assert by_title.context["found_books"] == [school["book"]]
    assert f'value="{school["copy"].qr_code}"' in by_title.content.decode()
    assert f'value="{school["lina"].qr_code}"' in by_name.content.decode()


def test_manual_method_selecting_results_records_a_loan(staff_client, school):
    scan(staff_client, "Lina")
    scan(staff_client, school["lina"].qr_code)
    scan(staff_client, "Gruffalo")
    scan(staff_client, school["copy"].qr_code)

    assert Loan.objects.get().borrower == school["lina"]


def test_removed_copy_cannot_be_lent(staff_client, school):
    school["copy"].status = Copy.Status.ARCHIVED
    school["copy"].save()

    scan(staff_client, school["lina"].qr_code)
    response = scan(staff_client, school["copy"].qr_code)

    assert Loan.objects.count() == 0
    assert "prêt impossible" in response.content.decode()


def test_student_card_shows_current_loans(staff_client, school):
    scan(staff_client, school["lina"].qr_code)
    scan(staff_client, school["copy"].qr_code)

    response = scan(staff_client, school["lina"].qr_code)

    assert "Le Gruffalo" in response.content.decode()


def test_mark_as_returned_button_from_the_student_card(staff_client, school):
    scan(staff_client, school["lina"].qr_code)
    scan(staff_client, school["copy"].qr_code)
    scan(staff_client, school["lina"].qr_code)

    staff_client.post(reverse("desk"), {"action": "return", "copy": str(school["copy"].pk)})

    assert Loan.objects.get().return_date == timezone.localdate()


def test_dashboard_global_search_opens_results_on_desk(staff_client, school):
    response = staff_client.get(reverse("desk"), {"q": "Gruffalo"})

    assert response.context["found_books"] == [school["book"]]
    assert "Rechercher un livre ou un élève" in staff_client.get(reverse("dashboard")).content.decode()
