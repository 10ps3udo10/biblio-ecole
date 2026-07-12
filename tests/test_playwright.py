import pytest
from playwright.sync_api import expect

from library.models import Book, Borrower, Copy, Loan


pytestmark = pytest.mark.playwright


def select_borrower(page, query, option_name, borrower_id, keyboard=False):
    search = page.get_by_role("combobox", name="Choose your name")
    search.fill(query)
    expect(page.get_by_role("option", name=option_name)).to_be_visible()
    if keyboard:
        search.press("ArrowDown")
        search.press("Enter")
    else:
        page.get_by_role("option", name=option_name).click()
    expect(page.locator("input[name='borrower']")).to_have_value(str(borrower_id))


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
    expect(page.get_by_role("heading", name="Overview")).to_be_visible()
    expect(page.get_by_label("Signed in as librarian")).to_be_visible()
    expect(page.get_by_role("img", name="Checkouts and returns during the last seven days")).to_be_visible()
    expect(page.get_by_role("heading", name="Copy availability")).to_be_visible()
    nav_items = page.locator("nav > a, nav > details > summary")
    assert nav_items.count() == 4
    for index in range(nav_items.count()):
        item = nav_items.nth(index)
        icon = item.locator("svg.lucide")
        item_box = item.bounding_box()
        assert item_box
        assert item_box["height"] == 36
        if icon.count():
            expect(icon).to_be_visible()
            icon_box = icon.bounding_box()
            assert icon_box
            assert abs((item_box["y"] + item_box["height"] / 2) - (icon_box["y"] + icon_box["height"] / 2)) < 1
    page.get_by_text("Library", exact=True).click()
    expect(page.get_by_role("link", name="Catalog", exact=True)).to_be_visible()
    expect(page.get_by_role("link", name="Borrowers", exact=True)).to_be_visible()
    expect(page.get_by_role("link", name="Overdue", exact=True)).to_be_visible()
    page.get_by_label("Signed in as librarian").click()
    expect(page.get_by_role("link", name="Settings", exact=True)).to_be_visible()
    expect(page.get_by_role("button", name="Sign out", exact=True)).to_be_visible()

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
def test_librarian_can_prefill_manual_book_from_isbn(page, live_server, django_user_model, monkeypatch):
    page_errors = []
    page.on("pageerror", lambda error: page_errors.append(str(error)))
    monkeypatch.setattr(
        "library.views.lookup_book_by_isbn",
        lambda isbn: {
            "title": "La sombra del viento",
            "authors": "Carlos Ruiz Zafon",
            "isbn13": isbn,
            "publisher": "Planeta",
            "publication_year": 2005,
        },
    )
    django_user_model.objects.create_superuser(username="isbn", password="secret", email="")

    page.goto(f"{live_server.url}/admin/login/?next=/books/add/")
    page.locator("input[name='username']").fill("isbn")
    page.locator("input[name='password']").fill("secret")
    page.locator("input[type='submit']").click()
    expect(page.locator("html")).to_have_attribute("data-book-entry-ready", "true")
    page.locator("input[name='isbn13']").fill("978-84-0805252-4")

    expect(page.locator("#isbn-entry-status")).to_have_text("Waiting for book details...")
    expect(page.get_by_role("button", name="Waiting for book details...")).to_be_disabled()
    page.wait_for_timeout(700)
    assert not page_errors, page_errors
    expect(page.locator("#isbn-entry-status")).not_to_be_empty()
    expect(page.locator("input[name='isbn13']")).to_have_value("9788408052524")
    expect(page.locator("input[name='title']")).to_have_value("La sombra del viento")
    expect(page.locator("textarea[name='authors']")).to_have_value("Carlos Ruiz Zafon")
    expect(page.locator("input[name='publisher']")).to_have_value("Planeta")
    expect(page.locator("input[name='publication_year']")).to_have_value("2005")
    expect(page.get_by_role("button", name="Save book")).to_be_enabled()
    page.get_by_role("button", name="Save book").click()

    expect(page.get_by_role("heading", name="La sombra del viento")).to_be_visible()
    assert Book.objects.filter(title="La sombra del viento", isbn13="9788408052524").exists()


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
    expect(page.get_by_role("navigation", name="Utility navigation")).to_be_visible()
    expect(page.get_by_role("link", name="Docs")).to_have_attribute("href", "https://mrueda.github.io/shelf-school/")
    expect(page.get_by_role("link", name="Admin login")).to_have_attribute("href", "/admin/login/?next=/dashboard/")

    select_borrower(page, "mia", "mia - Mia Lopez", borrower.id)
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
    expect(page.locator("input[name='borrower']")).to_have_value(str(borrower.id))

    copy.refresh_from_db()
    assert copy.status == Copy.Status.CHECKED_OUT

    page.locator("input[name='action'][value='checkin']").check()
    select_borrower(page, "mia", "mia - Mia Lopez", borrower.id, keyboard=True)
    page.get_by_role("button", name="Continue").click()
    expect(page.get_by_role("heading", name="Choose books to return")).to_be_visible()
    expect(page.get_by_text("Dropdown Circulation", exact=True)).to_be_visible()
    expect(page.locator("input[name='return_copies']")).to_have_count(1)
    page.locator("input[name='return_copies']").check()
    page.get_by_role("button", name="Review return").click()
    expect(page.get_by_text("Dropdown Circulation", exact=True)).to_be_visible()
    assert Loan.objects.get(copy=copy).return_date is None
    page.get_by_role("button", name="Confirm return").click()
    expect(page.get_by_text("Returned 1 book for Mia Lopez.")).to_be_visible()

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
    select_borrower(page, "alex", "alex - Alex Reader", borrower.id, keyboard=True)
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
def test_admin_borrower_view_highlights_current_and_overdue_loans(page, live_server, django_user_model):
    from datetime import timedelta
    from django.utils import timezone

    django_user_model.objects.create_superuser(username="borrowers", password="secret", email="")
    borrower = Borrower.objects.create(username="mia", first_name="Mia", last_name="Lopez", class_name="3B")
    copy = Copy.objects.create(book=Book.objects.create(title="Overdue classroom book"), copy_number=1, status=Copy.Status.CHECKED_OUT)
    Loan.objects.create(copy=copy, borrower=borrower, due_date=timezone.localdate() - timedelta(days=2))

    page.goto(f"{live_server.url}/admin/login/?next=/borrowers/")
    page.locator("input[name='username']").fill("borrowers")
    page.locator("input[name='password']").fill("secret")
    page.locator("input[type='submit']").click()

    expect(page.get_by_role("heading", name="Borrowers")).to_be_visible()
    expect(page.get_by_text("With books out")).to_be_visible()
    expect(page.get_by_text("1 overdue")).to_be_visible()
    page.get_by_role("link", name="ML Mia Lopez mia").click()
    expect(page.get_by_role("heading", name="Mia Lopez")).to_be_visible()
    expect(page.get_by_role("heading", name="Currently borrowed")).to_be_visible()
    expect(page.get_by_role("link", name="Overdue classroom book Copy #1")).to_be_visible()
    expect(page.get_by_text("1 overdue book needs attention.")).to_be_visible()


@pytest.mark.django_db(transaction=True)
def test_admin_can_delete_one_physical_copy_in_browser(page, live_server, django_user_model):
    django_user_model.objects.create_superuser(username="copies", password="secret", email="")
    book = Book.objects.create(title="Duplicate classroom title")
    first = Copy.objects.create(book=book, copy_number=1)
    second = Copy.objects.create(book=book, copy_number=2)

    page.goto(f"{live_server.url}/admin/login/?next={second.get_absolute_url()}")
    page.locator("input[name='username']").fill("copies")
    page.locator("input[name='password']").fill("secret")
    page.locator("input[type='submit']").click()

    expect(page.get_by_role("heading", name="Duplicate classroom title #2")).to_be_visible()
    page.on("dialog", lambda dialog: dialog.accept())
    page.get_by_role("button", name="Delete copy").click()

    expect(page.get_by_text("Deleted copy #2 of Duplicate classroom title")).to_be_visible()
    expect(page.get_by_role("heading", name="Duplicate classroom title")).to_be_visible()
    assert Copy.objects.filter(pk=first.id).exists()
    assert not Copy.objects.filter(pk=second.id).exists()


@pytest.mark.django_db(transaction=True)
def test_admin_can_correct_book_copy_and_borrower_in_browser(page, live_server, django_user_model):
    django_user_model.objects.create_superuser(username="editor", password="secret", email="")
    book = Book.objects.create(title="Title with typo")
    copy = Copy.objects.create(book=book, copy_number=1, shelf_location="Wrong")
    borrower = Borrower.objects.create(username="student", first_name="Studnt", last_name="Name")

    page.goto(f"{live_server.url}/admin/login/?next={book.get_absolute_url()}")
    page.locator("input[name='username']").fill("editor")
    page.locator("input[name='password']").fill("secret")
    page.locator("input[type='submit']").click()

    page.get_by_role("link", name="Edit book").click()
    page.locator("input[name='title']").fill("Correct title")
    page.get_by_role("button", name="Save book").click()
    expect(page.get_by_text("Book details updated.")).to_be_visible()

    page.get_by_role("link", name="#1").click()
    page.get_by_role("link", name="Edit copy").click()
    page.locator("input[name='shelf_location']").fill("A2")
    page.get_by_role("button", name="Save").click()
    expect(page.get_by_text("Copy details updated.")).to_be_visible()

    page.goto(f"{live_server.url}{borrower.get_absolute_url()}")
    page.get_by_role("link", name="Edit borrower").click()
    page.locator("input[name='first_name']").fill("Student")
    page.locator("input[name='active']").check()
    page.get_by_role("button", name="Save").click()
    expect(page.get_by_text("Borrower details updated.")).to_be_visible()

    book.refresh_from_db()
    copy.refresh_from_db()
    borrower.refresh_from_db()
    assert book.title == "Correct title"
    assert copy.shelf_location == "A2"
    assert borrower.first_name == "Student"


@pytest.mark.django_db(transaction=True)
def test_admin_can_sort_every_data_table_in_browser(page, live_server, django_user_model):
    from datetime import timedelta
    from django.utils import timezone

    django_user_model.objects.create_superuser(username="sorter", password="secret", email="")
    alpha = Book.objects.create(title="Alpha title", authors="Zulu Author")
    beta = Book.objects.create(title="Beta title", authors="Alpha Author")
    alpha_copy = Copy.objects.create(book=alpha, copy_number=1, shelf_location="Z9", status=Copy.Status.CHECKED_OUT)
    Copy.objects.create(book=alpha, copy_number=2, shelf_location="A1")
    beta_copy = Copy.objects.create(book=beta, copy_number=1, shelf_location="B1", status=Copy.Status.CHECKED_OUT)
    alpha_borrower = Borrower.objects.create(username="alpha-user", first_name="Amy", last_name="Zulu", class_name="2B")
    beta_borrower = Borrower.objects.create(username="beta-user", first_name="Ben", last_name="Alpha", class_name="1A")
    Loan.objects.create(copy=alpha_copy, borrower=alpha_borrower, due_date=timezone.localdate() - timedelta(days=1))
    Loan.objects.create(copy=beta_copy, borrower=beta_borrower, due_date=timezone.localdate() - timedelta(days=2))

    page.goto(f"{live_server.url}/admin/login/?next=/books/")
    page.locator("input[name='username']").fill("sorter")
    page.locator("input[name='password']").fill("secret")
    page.locator("input[type='submit']").click()

    page.get_by_role("columnheader", name="Author").get_by_role("link").click()
    expect(page.locator("tbody tr").first).to_contain_text("Beta title")

    page.goto(f"{live_server.url}/borrowers/")
    page.get_by_role("columnheader", name="Class").get_by_role("link").click()
    expect(page.locator("tbody tr").first).to_contain_text("Ben Alpha")

    page.goto(f"{live_server.url}/loans/overdue/")
    page.get_by_role("columnheader", name="Borrower").get_by_role("link").click()
    expect(page.locator("tbody tr").first).to_contain_text("Ben Alpha")

    page.goto(f"{live_server.url}{alpha.get_absolute_url()}")
    page.get_by_role("columnheader", name="Shelf").get_by_role("link").click()
    expect(page.locator("tbody tr").first).to_contain_text("A1")


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
