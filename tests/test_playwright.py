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

    page.goto(f"{live_server.url}/admin/login/?next=/")
    page.locator("input[name='username']").fill("librarian")
    page.locator("input[name='password']").fill("secret")
    page.locator("input[type='submit']").click()
    expect(page.get_by_role("heading", name="Library dashboard")).to_be_visible()

    page.get_by_role("link", name="Checkout").click()
    page.locator("input[name='borrower_code']").fill(borrower.qr_code)
    page.locator("input[name='copy_code']").fill(copy.qr_code)
    page.get_by_role("button", name="Create loan").click()
    expect(page.get_by_text("Checked out The Wild Robot to Mia Lopez.")).to_be_visible()

    copy.refresh_from_db()
    assert copy.status == Copy.Status.CHECKED_OUT
    assert Loan.objects.filter(copy=copy, borrower=borrower, return_date__isnull=True).exists()

    page.get_by_role("link", name="Return").click()
    page.locator("input[name='copy_code']").fill(copy.qr_code)
    page.get_by_role("button", name="Return copy").click()
    expect(page.get_by_text("Returned The Wild Robot.")).to_be_visible()

    copy.refresh_from_db()
    loan = Loan.objects.get(copy=copy)
    assert copy.status == Copy.Status.AVAILABLE
    assert loan.return_date is not None


@pytest.mark.django_db(transaction=True)
def test_librarian_can_track_book_from_photo_in_browser(page, live_server, django_user_model, tmp_path, settings):
    settings.MEDIA_ROOT = tmp_path / "media"
    django_user_model.objects.create_superuser(username="photo", password="secret", email="")
    image_path = tmp_path / "cover.jpg"
    image_path.write_bytes(b"fake image bytes")

    page.goto(f"{live_server.url}/admin/login/?next=/books/photo-intake/")
    page.locator("input[name='username']").fill("photo")
    page.locator("input[name='password']").fill("secret")
    page.locator("input[type='submit']").click()

    expect(page.get_by_role("heading", name="Photo intake")).to_be_visible()
    page.locator("input[name='photos']").set_input_files(str(image_path))
    page.locator("input[name='title']").fill("Classroom Photo Book")
    page.locator("input[name='shelf_location']").fill("New")
    page.get_by_role("button", name="Track this book").click()

    expect(page.get_by_text("Photo intake created a tracked copy.")).to_be_visible()
    expect(page.get_by_role("heading", name="Classroom Photo Book #1")).to_be_visible()
    book = Book.objects.get(title="Classroom Photo Book")
    copy = book.copies.get()
    assert copy.qr_code == f"COPY:{copy.id}"
    assert copy.shelf_location == "New"


@pytest.mark.django_db(transaction=True)
def test_librarian_can_circulate_copy_from_photo_and_dropdowns(page, live_server, django_user_model, tmp_path):
    import qrcode

    django_user_model.objects.create_superuser(username="circ", password="secret", email="")
    book = Book.objects.create(title="Dropdown Circulation")
    copy = Copy.objects.create(book=book, copy_number=1)
    borrower = Borrower.objects.create(username="mia", first_name="Mia", last_name="Lopez")
    qr_path = tmp_path / "copy-qr.png"
    qrcode.make(copy.qr_code).save(qr_path)

    page.goto(f"{live_server.url}/admin/login/?next=/circulation/")
    page.locator("input[name='username']").fill("circ")
    page.locator("input[name='password']").fill("secret")
    page.locator("input[type='submit']").click()
    expect(page.get_by_role("heading", name="Circulation")).to_be_visible()

    page.locator("select[name='borrower']").select_option(str(borrower.id))
    page.locator("select[name='action']").select_option("checkout")
    page.locator("input[name='book_photo']").set_input_files(str(qr_path))
    page.get_by_role("button", name="Submit").click()
    expect(page.get_by_text("Checked out Dropdown Circulation to Mia Lopez.")).to_be_visible()

    copy.refresh_from_db()
    assert copy.status == Copy.Status.CHECKED_OUT

    page.goto(f"{live_server.url}/circulation/")
    page.locator("select[name='borrower']").select_option(str(borrower.id))
    page.locator("select[name='action']").select_option("checkin")
    page.locator("input[name='book_photo']").set_input_files(str(qr_path))
    page.get_by_role("button", name="Submit").click()
    expect(page.get_by_text("Checked in Dropdown Circulation from Mia Lopez.")).to_be_visible()

    copy.refresh_from_db()
    loan = Loan.objects.get(copy=copy, borrower=borrower)
    assert copy.status == Copy.Status.AVAILABLE
    assert loan.return_date is not None
