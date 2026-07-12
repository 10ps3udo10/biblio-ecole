import pytest
from playwright.sync_api import expect

from library.models import Book, Borrower, Copy, Loan


pytestmark = pytest.mark.playwright


@pytest.mark.django_db(transaction=True)
def test_librarian_can_checkout_and_return_copy_in_browser(page, live_server, django_user_model):
    django_user_model.objects.create_superuser(username="librarian", password="secret", email="")
    book = Book.objects.create(title="The Wild Robot", authors="Peter Brown")
    copy = Copy.objects.create(book=book, copy_number=1, shelf_location="R1")
    borrower = Borrower.objects.create(first_name="Mia", last_name="Lopez", class_name="3B")

    page.goto(f"{live_server.url}/admin/login/?next=/dashboard/")
    page.locator("input[name='username']").fill("librarian")
    page.locator("input[name='password']").fill("secret")
    page.locator("input[type='submit']").click()
    expect(page.get_by_role("heading", name="Library dashboard")).to_be_visible()

    page.goto(f"{live_server.url}/checkout/")
    page.locator("input[name='borrower_code']").fill(borrower.qr_code)
    page.locator("input[name='copy_code']").fill(copy.qr_code)
    page.get_by_role("button", name="Create loan").click()
    expect(page.get_by_text("Checked out The Wild Robot to Mia Lopez.")).to_be_visible()

    copy.refresh_from_db()
    assert copy.status == Copy.Status.CHECKED_OUT
    assert Loan.objects.filter(copy=copy, borrower=borrower, return_date__isnull=True).exists()

    page.goto(f"{live_server.url}/return/")
    page.locator("input[name='copy_code']").fill(copy.qr_code)
    page.get_by_role("button", name="Return copy").click()
    expect(page.get_by_text("Returned The Wild Robot.")).to_be_visible()

    copy.refresh_from_db()
    loan = Loan.objects.get(copy=copy)
    assert copy.status == Copy.Status.AVAILABLE
    assert loan.return_date is not None


@pytest.mark.django_db(transaction=True)
def test_librarian_can_track_book_from_photo_in_browser(page, live_server, django_user_model, tmp_path, settings, monkeypatch):
    page_errors = []
    page.on("pageerror", lambda error: page_errors.append(str(error)))
    settings.MEDIA_ROOT = tmp_path / "media"
    monkeypatch.setattr(
        "library.views.lookup_book_by_isbn",
        lambda isbn: {"title": "Classroom Photo Book", "authors": "A. Reader", "isbn13": isbn},
    )
    django_user_model.objects.create_superuser(username="photo", password="secret", email="")
    image_path = tmp_path / "cover.jpg"
    image_path.write_bytes(b"fake image bytes")

    page.goto(f"{live_server.url}/admin/login/?next=/books/photo-intake/")
    page.locator("input[name='username']").fill("photo")
    page.locator("input[name='password']").fill("secret")
    page.locator("input[type='submit']").click()

    expect(page.get_by_role("heading", name="Photo intake")).to_be_visible()
    expect(page.locator(".photo-capture")).to_be_visible()
    expect(page.get_by_role("button", name="Track this book")).to_be_visible()
    expect(page.locator("html")).to_have_attribute("data-photo-intake-ready", "true")
    expect(page.locator("#isbn-web-search")).to_be_hidden()
    page.locator("input[name='photos']").set_input_files(str(image_path))
    assert not page_errors, page_errors
    expect(page.locator("#photo-preview")).to_have_class("visible")
    expect(page.get_by_text("A valid ISBN automatically fills")).to_be_visible()
    page.locator("input[name='isbn']").fill("9780316381994")
    expect(page.locator("input[name='title']")).to_have_value("Classroom Photo Book")
    page.locator("input[name='shelf_location']").fill("New")
    page.get_by_role("button", name="Track this book").click()

    expect(page.get_by_text("Photo intake created a tracked copy.")).to_be_visible()
    expect(page.get_by_role("heading", name="Classroom Photo Book #1")).to_be_visible()
    book = Book.objects.get(title="Classroom Photo Book")
    copy = book.copies.get()
    assert copy.qr_code == f"COPY:{copy.id}"
    assert copy.shelf_location == "New"


@pytest.mark.django_db(transaction=True)
def test_student_can_self_circulate_copy_without_admin_login(page, live_server, tmp_path):
    import qrcode

    book = Book.objects.create(title="Dropdown Circulation")
    copy = Copy.objects.create(book=book, copy_number=1)
    borrower = Borrower.objects.create(username="mia", first_name="Mia", last_name="Lopez")
    qr_path = tmp_path / "copy-qr.png"
    qrcode.make(copy.qr_code).save(qr_path)

    page.goto(live_server.url)
    expect(page.get_by_role("heading", name="Borrow or return a book")).to_be_visible()
    expect(page.get_by_role("navigation")).not_to_be_visible()
    expect(page.get_by_role("link", name="Docs")).to_have_attribute("href", "https://mrueda.github.io/shelf-school/")

    page.locator("select[name='borrower']").select_option(str(borrower.id))
    page.locator("input[name='action'][value='checkout']").check()
    page.get_by_role("button", name="Continue").click()
    expect(page.get_by_text("The photo is read once and never saved.")).to_be_visible()
    page.locator("input[name='book_photo']").set_input_files(str(qr_path))
    page.get_by_role("button", name="Identify book").click()
    expect(page.get_by_role("heading", name="Borrow or return a book")).to_be_visible()
    expect(page.get_by_text("Dropdown Circulation", exact=True)).to_be_visible()
    assert Loan.objects.count() == 0
    page.get_by_role("button", name="Confirm checkout").click()
    expect(page.get_by_text("Checked out Dropdown Circulation to Mia Lopez.")).to_be_visible()
    expect(page.locator("select[name='borrower']")).to_have_value(str(borrower.id))

    copy.refresh_from_db()
    assert copy.status == Copy.Status.CHECKED_OUT

    page.locator("input[name='action'][value='checkin']").check()
    page.get_by_role("button", name="Continue").click()
    page.locator("input[name='book_photo']").set_input_files(str(qr_path))
    page.get_by_role("button", name="Identify book").click()
    expect(page.get_by_text("Dropdown Circulation", exact=True)).to_be_visible()
    assert Loan.objects.get(copy=copy).return_date is None
    page.get_by_role("button", name="Confirm return").click()
    expect(page.get_by_text("Checked in Dropdown Circulation from Mia Lopez.")).to_be_visible()

    copy.refresh_from_db()
    loan = Loan.objects.get(copy=copy, borrower=borrower)
    assert copy.status == Copy.Status.AVAILABLE
    assert loan.return_date is not None


@pytest.mark.django_db(transaction=True)
def test_student_can_find_book_manually_with_partial_text(page, live_server):
    book = Book.objects.create(title="Manual Search Book", authors="Specific Writer", isbn13="9780316381994")
    copy = Copy.objects.create(book=book, copy_number=1, shelf_location="Green-2")
    borrower = Borrower.objects.create(username="alex", first_name="Alex", last_name="Reader")

    page.goto(live_server.url)
    page.locator("select[name='borrower']").select_option(str(borrower.id))
    page.get_by_role("button", name="Continue").click()
    page.get_by_role("tab", name="Find manually").click()
    page.locator("#copy-filter").fill("Specific Writer")
    expect(page.locator("select[name='manual_copy'] option")).to_have_count(1)
    page.locator("select[name='manual_copy']").select_option(str(copy.id))
    page.get_by_role("button", name="Identify book").click()

    expect(page.get_by_text("Manual Search Book", exact=True)).to_be_visible()
    page.get_by_role("button", name="Confirm checkout").click()
    expect(page.get_by_text("Checked out Manual Search Book to Alex Reader.")).to_be_visible()
    assert Loan.objects.filter(copy=copy, borrower=borrower, return_date__isnull=True).exists()


@pytest.mark.django_db(transaction=True)
def test_admin_can_complete_school_setup_in_browser(page, live_server, django_user_model):
    from library.models import SchoolProfile

    django_user_model.objects.create_superuser(username="setup", password="secret", email="")
    page.goto(f"{live_server.url}/admin/login/?next=/dashboard/")
    page.locator("input[name='username']").fill("setup")
    page.locator("input[name='password']").fill("secret")
    page.locator("input[type='submit']").click()

    expect(page.get_by_text("Finish setting up Shelf-School")).to_be_visible()
    page.get_by_role("link", name="School settings").click()
    page.locator("input[name='school_name']").fill("Escola Montserrat")
    page.locator("input[name='short_name']").fill("Montserrat Library")
    page.locator("input[name='default_loan_days']").fill("21")
    page.get_by_role("button", name="Save school settings").click()

    expect(page.get_by_text("School settings saved.")).to_be_visible()
    expect(page.locator(".brand")).to_contain_text("Montserrat Library")
    profile = SchoolProfile.current()
    assert profile.setup_completed is True
    assert profile.default_loan_days == 21
