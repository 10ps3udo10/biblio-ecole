import pytest
from playwright.sync_api import expect

from library.models import SchoolClass, Book, Borrower, Copy, Loan


pytestmark = pytest.mark.playwright


@pytest.mark.django_db(transaction=True)
@pytest.mark.parametrize("width", [390, 1440])
def test_account_start_page_and_table_density(page, live_server, django_user_model, width):
    django_user_model.objects.create_user(username="preferences-reader", password="secret", is_staff=True)
    Book.objects.create(title="Personal preferences", authors="Library author")
    page.set_viewport_size({"width": width, "height": 1000})
    page.goto(f"{live_server.url}/staff/login/?next=/account/")
    page.locator("input[name=username]").fill("preferences-reader")
    page.locator("input[name=password]").fill("secret")
    page.get_by_role("button", name="Se connecter", exact=True).click()
    page.get_by_label("Page d'accueil après la connexion :", exact=True).select_option("book_list")
    page.get_by_text("Compact", exact=True).click()
    page.get_by_role("button", name="Enregistrer les préférences", exact=True).click()
    expect(page.get_by_label("Page d'accueil après la connexion :", exact=True)).to_have_value("book_list")
    expect(page.locator("input[value=compact]")).to_be_checked()
    assert page.evaluate("document.documentElement.scrollWidth <= innerWidth")
    page.screenshot(path=f"/tmp/shelf-school-account-preferences-{width}.png", full_page=True)
    page.goto(live_server.url + "/books/")
    cell = page.locator("tbody td").first
    assert cell.evaluate("el => getComputedStyle(el).paddingTop") == "6px"
    compact_height = page.locator("tbody tr").first.bounding_box()["height"]
    page.screenshot(path=f"/tmp/shelf-school-compact-table-{width}.png", full_page=True)
    page.emulate_media(media="print")
    assert cell.evaluate("el => getComputedStyle(el).paddingTop") == "12px"
    page.emulate_media(media="screen")
    page.get_by_label("Connecté : preferences-reader", exact=True).click()
    page.get_by_role("button", name="Se déconnecter", exact=True).click()
    expect(page.locator("html")).to_have_attribute("data-table-density", "comfortable")
    page.get_by_role("link", name="Connexion du personnel", exact=True).click()
    page.locator("input[name=username]").fill("preferences-reader")
    page.locator("input[name=password]").fill("secret")
    page.get_by_role("button", name="Se connecter", exact=True).click()
    expect(page).to_have_url(live_server.url + "/books/")
    expect(page.locator("html")).to_have_attribute("data-table-density", "compact")
    page.goto(live_server.url + "/account/")
    page.get_by_text("Confortable", exact=True).click()
    page.get_by_role("button", name="Enregistrer les préférences", exact=True).click()
    page.goto(live_server.url + "/books/")
    assert page.locator("tbody tr").first.bounding_box()["height"] > compact_height


@pytest.mark.django_db(transaction=True)
@pytest.mark.parametrize("width", [390, 1440])
def test_personal_theme_persistence_system_and_public_reset(page, live_server, django_user_model, width):
    from django.urls import reverse
    from library.models import UserPreference
    user = django_user_model.objects.create_user(username="theme-reader", password="secret", is_staff=True)
    book = Book.objects.create(title="Theme test book", authors="School writer", needs_information=True)
    copy = Copy.objects.create(book=book, copy_number=1)
    page.set_viewport_size({"width": width, "height": 1000})
    page.emulate_media(color_scheme="light")
    page.goto(f"{live_server.url}/staff/login/?next=/account/")
    page.locator("input[name=username]").fill(user.username)
    page.locator("input[name=password]").fill("secret")
    page.get_by_role("button", name="Se connecter", exact=True).click()
    expect(page.locator("html")).to_have_attribute("data-theme", "light")
    page.get_by_text("Sombre", exact=True).click()
    expect(page.locator("html")).to_have_attribute("data-theme", "dark")
    page.get_by_role("button", name="Enregistrer l'apparence", exact=True).click()
    assert UserPreference.objects.get(user=user).theme == "dark"
    page.reload()
    expect(page.locator("html")).to_have_attribute("data-theme", "dark")
    assert page.locator("body").evaluate("(el) => getComputedStyle(el).backgroundColor") == "rgb(41, 43, 46)"
    assert page.evaluate("document.documentElement.scrollWidth <= window.innerWidth")
    page.screenshot(path=f"/tmp/shelf-school-my-account-dark-{width}.png", full_page=True)
    for path, name in [("/books/", "catalog"), ("/settings/", "settings"), ("/dashboard/", "overview"), ("/", "circulation")]:
        page.goto(live_server.url + path)
        expect(page.locator("html")).to_have_attribute("data-theme", "dark")
        assert page.evaluate("document.documentElement.scrollWidth <= window.innerWidth")
        page.screenshot(path=f"/tmp/shelf-school-{name}-dark-{width}.png", full_page=True)
    page.goto(live_server.url + reverse("label", args=["copy", copy.pk]))
    assert page.locator(".label").evaluate("(el) => getComputedStyle(el).backgroundColor") == "rgb(255, 255, 255)"
    page.emulate_media(media="print")
    assert page.locator("body").evaluate("(el) => getComputedStyle(el).backgroundColor") == "rgb(255, 255, 255)"
    page.emulate_media(media="screen")
    page.goto(live_server.url + "/account/")
    page.get_by_text("Système", exact=True).click()
    page.get_by_role("button", name="Enregistrer l'apparence", exact=True).click()
    page.emulate_media(color_scheme="dark")
    expect(page.locator("html")).to_have_attribute("data-theme", "dark")
    page.emulate_media(color_scheme="light")
    expect(page.locator("html")).to_have_attribute("data-theme", "light")
    page.get_by_text("Clair", exact=True).click()
    page.get_by_role("button", name="Enregistrer l'apparence", exact=True).click()
    page.emulate_media(color_scheme="dark")
    expect(page.locator("html")).to_have_attribute("data-theme", "light")
    page.get_by_label("Connecté : theme-reader", exact=True).click()
    page.get_by_role("button", name="Se déconnecter", exact=True).click()
    expect(page.locator("html")).to_have_attribute("data-theme", "light")


@pytest.mark.django_db(transaction=True)
@pytest.mark.parametrize("kind", ["books", "borrowers"])
@pytest.mark.parametrize("width", [390, 1440])
def test_csv_import_reference_and_template_download(page, live_server, django_user_model, kind, width):
    import csv
    from pathlib import Path
    from library.csv_templates import csv_columns
    django_user_model.objects.create_user(username="import-admin", password="secret", is_staff=True)
    page.set_viewport_size({"width": width, "height": 1000})
    page.goto(f"{live_server.url}/staff/login/?next=/{kind}/import/")
    page.locator("input[name=username]").fill("import-admin")
    page.locator("input[name=password]").fill("secret")
    page.get_by_role("button", name="Se connecter", exact=True).click()
    expect(page.get_by_role("heading", name="Colonnes obligatoires")).to_be_visible()
    for group in page.locator(".csv-field-group").all():
        group.locator("summary").click()
        expect(group.locator("dl")).to_be_visible()
    with page.expect_download() as download_info:
        page.get_by_role("link", name="Télécharger le modèle CSV", exact=True).click()
    download = download_info.value
    assert download.suggested_filename == f"shelf-school-{kind}-template.csv"
    with Path(download.path()).open(encoding="utf-8-sig", newline="") as file:
        assert list(csv.reader(file)) == [csv_columns(kind)["headers"]]
    assert page.evaluate("document.documentElement.scrollWidth <= window.innerWidth")
    page.screenshot(path=f"/tmp/shelf-school-import-{kind}-{width}.png", full_page=True)
    if kind == "borrowers":
        SchoolClass.objects.get_or_create(name="Lower Elementary (6-9)")
        page.locator("input[type=file]").set_input_files({
            "name": "borrowers.csv", "mimeType": "text/csv",
            "buffer": b"First name,Last name,School ID,School role,Class\nAna,Garcia,S-1042,Student,Lower Elementary (6-9)\n",
        })
        page.get_by_role("button", name="Prévisualiser les emprunteurs", exact=True).click()
        expect(page.get_by_role("heading", name="Aperçu de l'import", exact=True)).to_be_visible()
        expect(page.get_by_role("button", name="Ajouter 1 emprunteur", exact=True)).to_be_visible()
        assert page.evaluate("document.documentElement.scrollWidth <= window.innerWidth")
        page.screenshot(path=f"/tmp/shelf-school-import-borrowers-preview-{width}.png", full_page=True)


@pytest.mark.django_db(transaction=True)
@pytest.mark.parametrize("width", [390, 1440])
def test_staff_catalog_pagination_and_page_selection(page, live_server, django_user_model, monkeypatch, width):
    django_user_model.objects.create_user(username="catalog-admin", password="secret", is_staff=True)
    Book.objects.bulk_create([Book(title=f"Scale {index:04}", authors="Library author", isbn13="9780306406157") for index in range(1000)])
    monkeypatch.setattr("library.views.download_cover_by_isbn", lambda isbn: None)
    page.set_viewport_size({"width": width, "height": 1000})
    page.goto(f"{live_server.url}/staff/login/?next=/books/?q=Scale%26sort=title%26direction=desc")
    page.locator("input[name=username]").fill("catalog-admin")
    page.locator("input[name=password]").fill("secret")
    page.get_by_role("button", name="Se connecter", exact=True).click()
    expect(page.get_by_text("1 à 50 sur 1000 livres", exact=True)).to_be_visible()
    expect(page.locator(".cover-book-select")).to_have_count(50)
    page.get_by_role("checkbox", name="Sélectionner les livres concernés sur cette page").check()
    expect(page.locator("#cover-selection-count")).to_have_text("50 sélectionné(s) sur cette page")
    pages = page.get_by_role("navigation", name="Pages du catalogue", exact=True)
    pages.get_by_role("link", name="Page suivante", exact=True).click()
    expect(page.get_by_text("51 à 100 sur 1000 livres", exact=True)).to_be_visible()
    expect(page.locator("#cover-selection-count")).to_have_text("0 sélectionné(s) sur cette page")
    expect(page.locator("#cover-fetch-form input[name=next]")).to_have_value("/books/?q=Scale&sort=title&direction=desc&page=2")
    assert page.evaluate("document.documentElement.scrollWidth <= window.innerWidth")
    page.screenshot(path=f"/tmp/shelf-school-staff-catalog-{width}.png", full_page=True)
    page.get_by_role("checkbox", name="Sélectionner les livres concernés sur cette page").check()
    page.locator("#fetch-covers").click()
    expect(page.get_by_text("51 à 100 sur 1000 livres", exact=True)).to_be_visible()
    expect(page.get_by_text("Recherche des couvertures terminée :", exact=False)).to_contain_text("50 introuvable(s)")
    pages.get_by_role("link", name="Dernière page", exact=True).click()
    expect(page.get_by_text("951 à 1000 sur 1000 livres", exact=True)).to_be_visible()
    page.locator(".search input[name=q]").fill("Scale 0001")
    page.locator(".search button").click()
    expect(page.get_by_text("1 à 1 sur 1 livres", exact=True)).to_be_visible()
    expect(page.locator(".cover-book-select")).to_have_count(1)


@pytest.mark.django_db(transaction=True)
@pytest.mark.parametrize("width", [390, 768, 1440])
def test_public_catalog_views_filters_and_pagination(page, live_server, width):
    for index in range(25):
        book = Book.objects.create(title=f"Browse book {index:02}", language="English", authors="School author")
        Copy.objects.create(book=book, copy_number=1, shelf_location="Green")
    unavailable = Book.objects.create(title="Unavailable book", language="Spanish")
    Copy.objects.create(book=unavailable, copy_number=1, shelf_location="Red", status="checked_out")
    page.set_viewport_size({"width": width, "height": 900})
    page.goto(f"{live_server.url}/catalog/")
    expect(page.get_by_role("button", name="Affichage en liste")).to_have_attribute("aria-pressed", "true")
    page.get_by_role("button", name="Affichage en grille").click()
    expect(page.locator(".public-catalog-results")).to_have_attribute("data-view", "grid")
    page.get_by_label("Disponibles uniquement").check()
    expect(page.get_by_text("25 livres", exact=True)).to_be_visible()
    expect(page.get_by_role("button", name="Affichage en grille")).to_have_attribute("aria-pressed", "true")
    page.get_by_label("Étagère", exact=True).select_option("Green")
    page.get_by_label("Langue", exact=True).select_option("English")
    page.get_by_role("link", name="Suivant", exact=True).click()
    expect(page.get_by_text("Page 2 sur 2")).to_be_visible()
    expect(page.get_by_label("Disponibles uniquement")).to_be_checked()
    expect(page.get_by_label("Étagère", exact=True)).to_have_value("Green")
    expect(page.get_by_label("Langue", exact=True)).to_have_value("English")
    expect(page.locator(".public-catalog-row")).to_have_count(1)
    page.get_by_role("link", name="Précédent", exact=True).click()
    assert page.evaluate("document.documentElement.scrollWidth <= window.innerWidth")
    page.screenshot(path=f"/tmp/shelf-school-catalog-grid-{width}.png", full_page=True)
    page.get_by_role("button", name="Affichage en liste").click()
    page.reload()
    expect(page.get_by_role("button", name="Affichage en liste")).to_have_attribute("aria-pressed", "true")
    assert page.evaluate("document.documentElement.scrollWidth <= window.innerWidth")
    page.screenshot(path=f"/tmp/shelf-school-catalog-list-{width}.png", full_page=True)


@pytest.mark.django_db(transaction=True)
@pytest.mark.parametrize("width", [390, 1440])
def test_public_catalog_is_read_only_and_responsive(page, live_server, width):
    book = Book.objects.create(title="The public library book", authors="School author")
    copy = Copy.objects.create(book=book, copy_number=1, status="checked_out", shelf_location="Green section")
    borrower = Borrower.objects.create(first_name="Private reader", last_name="Private surname")
    Loan.objects.create(copy=copy, borrower=borrower)
    page.set_viewport_size({"width": width, "height": 900})
    page.goto(live_server.url)
    page.get_by_role("link", name="Catalogue", exact=True).click()
    page.get_by_role("searchbox", name="Rechercher dans le catalogue").fill("public library")
    page.get_by_role("button", name="Rechercher", exact=True).click()
    expect(page.get_by_text("Indisponible", exact=True)).to_be_visible()
    page.get_by_role("link", name=book.title, exact=True).click()
    expect(page.get_by_role("heading", name=book.title)).to_be_visible()
    expect(page.get_by_text("Green section", exact=True)).to_be_visible()
    expect(page.get_by_text("Emprunté", exact=True)).to_be_visible()
    expect(page.get_by_text("Private reader", exact=False)).to_have_count(0)
    expect(page.get_by_role("link", name="Modifier l'exemplaire")).to_have_count(0)
    assert page.evaluate("document.documentElement.scrollWidth <= window.innerWidth")
    page.screenshot(path=f"/tmp/shelf-school-public-catalog-{width}.png", full_page=True)


@pytest.mark.django_db(transaction=True)
def test_admin_manages_classes_positions_and_imports_borrowers(page, live_server, django_user_model):
    from library.models import SchoolClass, EmployeePosition
    django_user_model.objects.create_user(username="position-admin", password="secret", is_staff=True)
    page.goto(f"{live_server.url}/staff/login/?next=/settings/")
    page.locator("input[name='username']").fill("position-admin")
    page.locator("input[name='password']").fill("secret")
    page.get_by_role("button", name="Se connecter", exact=True).click()
    page.get_by_role("link", name="Fonctions du personnel", exact=True).click()
    page.locator("#id_name").fill("Learning support")
    page.get_by_role("button", name="Enregistrer la fonction", exact=True).click()
    expect(page.get_by_role("cell", name="Learning support", exact=True)).to_be_visible()
    page.get_by_role("link", name="Paramètres", exact=True).click()
    page.get_by_role("link", name="Classes", exact=True).click()
    page.locator("#id_name").fill("3A")
    page.get_by_role("button", name="Enregistrer la classe", exact=True).click()
    expect(page.get_by_role("cell", name="3A", exact=True)).to_be_visible()
    for width in (1440, 390):
        page.set_viewport_size({"width": width, "height": 900})
        assert page.evaluate("document.documentElement.scrollWidth <= window.innerWidth")
        page.screenshot(path=f"/tmp/shelf-school-classes-{width}.png", full_page=True)
    page.goto(f"{live_server.url}/borrowers/import/")
    page.locator("input[type=file]").set_input_files({
        "name": "staff.csv", "mimeType": "text/csv",
        "buffer": b"First name,Last name,School role,Position,School ID\nSam,Reader,Employee,Learning support,support\n",
    })
    page.get_by_role("button", name="Prévisualiser les emprunteurs", exact=True).click()
    expect(page.get_by_role("heading", name="Aperçu de l'import", exact=True)).to_be_visible()
    page.get_by_role("button", name="Ajouter 1 emprunteur", exact=True).click()
    expect(page.get_by_role("heading", name="Élèves", exact=True)).to_be_visible()
    page.get_by_role("link", name="Sam Reader").click()
    expect(page.locator(".borrower-badges").get_by_text("Learning support", exact=True)).to_be_visible()
    expect(page.locator(".borrower-badges").get_by_text("Personnel", exact=True)).to_be_visible()
    page.get_by_role("link", name="Modifier l'élève", exact=True).click()
    expect(page.locator("#id_position")).to_be_visible()
    expect(page.locator("#id_school_class")).not_to_be_visible()
    page.locator("#id_school_role").select_option("student")
    expect(page.locator("#id_position")).not_to_be_visible()
    expect(page.locator("#id_school_class")).to_be_visible()
    page.locator("#id_school_class").select_option(label="3A")
    page.get_by_role("button", name="Enregistrer", exact=True).click()
    expect(page.locator(".borrower-badges .school-class")).to_have_text("3A")
    expect(page.locator(".borrower-badges .position")).to_have_count(0)
    page.screenshot(path="/tmp/shelf-school-student-class-badge.png", full_page=True)
    assert django_user_model.objects.count() == 1
    assert EmployeePosition.objects.filter(name="Learning support").exists()


@pytest.mark.django_db(transaction=True)
@pytest.mark.parametrize("width,height", [(1440, 1000), (768, 1024), (390, 844)])
def test_circulation_receipt_and_borrower_change_responsive(page, live_server, width, height):
    import io
    from PIL import Image
    from django.core.files.base import ContentFile

    book = Book.objects.create(title="A school library book with a long title for curious readers")
    cover = io.BytesIO()
    Image.new("RGB", (90, 120), "#588276").save(cover, format="PNG")
    book.cover_image.save("ui-review-cover.png", ContentFile(cover.getvalue()))
    page.route("**" + book.cover_image.url, lambda route: route.fulfill(body=cover.getvalue(), content_type="image/png"))
    copy = Copy.objects.create(book=book, copy_number=1)
    first = Borrower.objects.create(borrower_id="alex", first_name="Alex", last_name="Reader")
    second = Borrower.objects.create(borrower_id="maria", first_name="Maria", last_name="Fernandez")
    page.set_viewport_size({"width": width, "height": height})
    errors = []
    page.on("pageerror", lambda error: errors.append(str(error)))

    def snapshot(state):
        assert page.evaluate("document.documentElement.scrollWidth <= window.innerWidth")
        for image in page.locator(".desk-book-cover:is(img)").all():
            expect(image).to_be_visible()
            image.evaluate("(image) => image.decode()")
            assert image.evaluate("(image) => image.naturalWidth > 0")
        page.screenshot(path=f"/tmp/shelf-school-{width}-{state}.png", full_page=True)

    try:
        page.goto(live_server.url)
        snapshot("start")
        select_borrower(page, "alex", "alex - Alex Reader", first.id)
        page.get_by_role("button", name="Continuer").click()
        page.get_by_role("tab", name="Chercher à la main").click()
        page.locator("#id_manual_copy").select_option(str(copy.id))
        page.get_by_role("button", name="Vérifier le livre", exact=True).click()
        snapshot("confirm")
        page.get_by_role("button", name="Ajouter un autre livre").click()
        page.get_by_role("button", name="Changer", exact=True).click()
        select_borrower(page, "maria", "maria - Maria Fernandez", second.id)
        page.get_by_role("button", name="Continuer").click()
        expect(page.locator("#id_basket_token")).to_have_value("")
        page.get_by_role("tab", name="Chercher à la main").click()
        page.locator("#id_manual_copy").select_option(str(copy.id))
        page.get_by_role("button", name="Vérifier le livre", exact=True).click()
        page.get_by_role("button", name="Emprunter 1 livre", exact=True).click()
        expect(page.get_by_role("heading", name="C'est fait, Maria Fernandez.")).to_be_visible()
        snapshot("receipt")
        assert Loan.objects.get(copy=copy).borrower_id == second.id
        page.get_by_role("link", name="Même élève", exact=True).click()
        page.locator("input[name='action'][value='checkin']").check()
        select_borrower(page, "maria", "maria - Maria Fernandez", second.id)
        page.get_by_role("button", name="Continuer").click()
        expect(page.locator("input[name='return_copies']")).to_have_count(1)
        expect(page.get_by_role("button", name="Sélectionnez les livres à rendre")).to_be_disabled()
        page.locator("input[name='return_copies']").check()
        snapshot("return")
        page.get_by_role("button", name="Vérifier 1 livre", exact=True).click()
        page.get_by_role("button", name="Rendre 1 livre", exact=True).click()
        page.get_by_role("link", name="Élève suivant", exact=True).click()
        expect(page.locator("#id_borrower")).to_have_value("")
        assert Loan.objects.get(copy=copy).return_date is not None
        assert not errors
    finally:
        book.cover_image.delete(save=False)


def select_borrower(page, query, option_name, borrower_id, keyboard=False):
    search = page.get_by_role("combobox", name="Choisissez votre nom")
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
    borrower = Borrower.objects.create(first_name="Mia", last_name="Lopez", school_class=SchoolClass.objects.get_or_create(name="3B")[0])

    page.goto(f"{live_server.url}/staff/login/?next=/dashboard/")
    page.locator("input[name='username']").fill("librarian")
    page.locator("input[name='password']").fill("secret")
    page.get_by_role("button", name="Se connecter").click()
    expect(page.get_by_role("heading", name="Vue d'ensemble")).to_be_visible()
    expect(page.get_by_label("Connecté : librarian")).to_be_visible()
    expect(page.get_by_role("img", name="Emprunts et retours des sept derniers jours")).to_be_visible()
    expect(page.get_by_role("heading", name="Disponibilité des exemplaires")).to_be_visible()
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
    page.get_by_text("Bibliothèque", exact=True).click()
    library_menu = page.locator("nav details").filter(has=page.locator("summary", has_text="Bibliothèque"))
    expect(library_menu.get_by_role("link")).to_have_text(["Vue d'ensemble", "Borne photo (élèves)", "Catalogue", "Élèves", "En retard", "Paramètres de l'école"])
    expect(library_menu.get_by_role("separator")).to_be_visible()
    expect(page.get_by_role("link", name="Catalogue", exact=True)).to_be_visible()
    expect(page.get_by_role("link", name="Élèves", exact=True)).to_be_visible()
    expect(page.get_by_role("link", name="En retard", exact=True)).to_be_visible()
    expect(page.get_by_role("navigation").get_by_role("link", name="Paramètres de l'école", exact=True)).to_be_visible()
    page.get_by_label("Connecté : librarian").click()
    expect(page.get_by_role("link", name="Mon compte", exact=True)).to_be_visible()
    expect(page.get_by_role("button", name="Se déconnecter", exact=True)).to_be_visible()

    page.goto(f"{live_server.url}/checkout/")
    page.locator("input[name='borrower_code']").fill(borrower.qr_code)
    page.locator("input[name='copy_code']").fill(copy.qr_code)
    page.get_by_role("button", name="Enregistrer l'emprunt").click()
    expect(page.get_by_text("The Wild Robot prêté à Mia Lopez.")).to_be_visible()

    copy.refresh_from_db()
    assert copy.status == Copy.Status.CHECKED_OUT
    assert Loan.objects.filter(copy=copy, borrower=borrower, return_date__isnull=True).exists()

    page.goto(f"{live_server.url}/return/")
    page.locator("input[name='copy_code']").fill(copy.qr_code)
    page.get_by_role("button", name="Rendre l'exemplaire").click()
    expect(page.get_by_text("The Wild Robot rendu.")).to_be_visible()

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

    page.goto(f"{live_server.url}/staff/login/?next=/books/photo-intake/")
    page.locator("input[name='username']").fill("photo")
    page.locator("input[name='password']").fill("secret")
    page.get_by_role("button", name="Se connecter").click()

    expect(page.get_by_role("heading", name="Ajout par photo")).to_be_visible()
    expect(page.locator(".photo-capture")).to_be_visible()
    expect(page.get_by_role("button", name="Ajouter ce livre")).to_be_visible()
    expect(page.locator("html")).to_have_attribute("data-photo-intake-ready", "true")
    expect(page.locator("#isbn-web-search")).to_be_hidden()
    page.locator("input[name='photos']").set_input_files(str(image_path))
    assert not page_errors, page_errors
    expect(page.locator("#photo-preview")).to_have_class("visible")
    expect(page.get_by_text("Un ISBN valide remplit automatiquement")).to_be_visible()
    page.locator("input[name='isbn']").fill("9780316381994")
    expect(page.locator("input[name='title']")).to_have_value("Classroom Photo Book")
    page.locator("input[name='shelf_location']").fill("New")
    page.get_by_role("button", name="Ajouter ce livre").click()

    expect(page.get_by_text("Un exemplaire a été créé à partir de la photo.")).to_be_visible()
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

    page.goto(f"{live_server.url}/staff/login/?next=/books/add/")
    page.locator("input[name='username']").fill("isbn")
    page.locator("input[name='password']").fill("secret")
    page.get_by_role("button", name="Se connecter").click()
    expect(page.locator("html")).to_have_attribute("data-book-entry-ready", "true")
    page.locator("input[name='isbn13']").fill("978-84-0805252-4")

    expect(page.locator("#isbn-entry-status")).to_have_text("Recherche des informations du livre...")
    expect(page.get_by_role("button", name="Recherche des informations du livre...")).to_be_disabled()
    page.wait_for_timeout(700)
    assert not page_errors, page_errors
    expect(page.locator("#isbn-entry-status")).not_to_be_empty()
    expect(page.locator("input[name='isbn13']")).to_have_value("9788408052524")
    expect(page.locator("input[name='title']")).to_have_value("La sombra del viento")
    expect(page.locator("textarea[name='authors']")).to_have_value("Carlos Ruiz Zafon")
    expect(page.locator("input[name='publisher']")).to_have_value("Planeta")
    expect(page.locator("input[name='publication_year']")).to_have_value("2005")
    expect(page.get_by_role("button", name="Enregistrer le livre")).to_be_enabled()
    page.get_by_role("button", name="Enregistrer le livre").click()

    expect(page.get_by_role("heading", name="La sombra del viento")).to_be_visible()
    assert Book.objects.filter(title="La sombra del viento", isbn13="9788408052524").exists()


@pytest.mark.django_db(transaction=True)
def test_student_can_self_circulate_copy_without_admin_login(page, live_server, tmp_path):
    import qrcode

    book = Book.objects.create(title="Dropdown Circulation")
    copy = Copy.objects.create(book=book, copy_number=1)
    second_book = Book.objects.create(title="Second Circulation Book")
    second_copy = Copy.objects.create(book=second_book, copy_number=1)
    borrower = Borrower.objects.create(borrower_id="mia", first_name="Mia", last_name="Lopez")
    qr_path = tmp_path / "copy-qr.png"
    second_qr_path = tmp_path / "second-copy-qr.png"
    qrcode.make(copy.qr_code).save(qr_path)
    qrcode.make(second_copy.qr_code).save(second_qr_path)

    page.goto(live_server.url)
    expect(page.get_by_role("heading", name="Emprunter ou rendre un livre")).to_be_visible()
    expect(page.get_by_role("navigation", name="Navigation utilitaire")).to_be_visible()
    expect(page.get_by_role("link", name="Documentation")).to_have_attribute("href", "https://mrueda.github.io/shelf-school/")
    expect(page.get_by_role("link", name="Connexion du personnel")).to_have_attribute("href", "/staff/login/")

    select_borrower(page, "mia", "mia - Mia Lopez", borrower.id)
    page.locator("input[name='action'][value='checkout']").check()
    page.get_by_role("button", name="Continuer").click()
    expect(page.get_by_role("tab", name="Chercher à la main")).to_have_attribute("aria-selected", "true")
    page.get_by_role("tab", name="Prendre une photo").click()
    expect(page.get_by_text("La photo est lue une seule fois et n'est jamais enregistrée.")).to_be_visible()
    page.locator("input[name='book_photo']").set_input_files(str(qr_path))
    page.get_by_role("button", name="Identifier le livre").click()
    expect(page.get_by_role("heading", name="Emprunter ou rendre un livre")).to_be_visible()
    expect(page.get_by_text("Dropdown Circulation", exact=True)).to_be_visible()
    assert Loan.objects.count() == 0
    page.get_by_role("button", name="Ajouter un autre livre").click()
    expect(page.get_by_role("heading", name="Ajouter un autre livre")).to_be_visible()
    expect(page.get_by_text("1 sélectionné(s)", exact=True)).to_be_visible()
    page.get_by_role("tab", name="Prendre une photo").click()
    page.locator("input[name='book_photo']").set_input_files(str(second_qr_path))
    page.get_by_role("button", name="Ajouter à l'emprunt").click()
    expect(page.get_by_text("Second Circulation Book", exact=True)).to_be_visible()
    expect(page.get_by_text("2 livres prêts à emprunter")).to_be_visible()
    page.get_by_role("button", name="Emprunter 2 livres", exact=True).click()
    expect(page.get_by_text("2 livres prêtés à Mia Lopez.")).to_be_visible()
    expect(page.get_by_role("heading", name="C'est fait, Mia Lopez.")).to_be_visible()
    page.get_by_role("link", name="Même élève").click()

    copy.refresh_from_db()
    second_copy.refresh_from_db()
    assert copy.status == Copy.Status.CHECKED_OUT
    assert second_copy.status == Copy.Status.CHECKED_OUT

    page.locator("input[name='action'][value='checkin']").check()
    select_borrower(page, "mia", "mia - Mia Lopez", borrower.id, keyboard=True)
    page.get_by_role("button", name="Continuer").click()
    expect(page.get_by_role("heading", name="Choisissez les livres à rendre")).to_be_visible()
    expect(page.get_by_text("Dropdown Circulation", exact=True)).to_be_visible()
    expect(page.locator("input[name='return_copies']")).to_have_count(2)
    page.locator("input[name='return_copies']").nth(0).check()
    page.locator("input[name='return_copies']").nth(1).check()
    page.get_by_role("button", name="Vérifier 2 livres").click()
    expect(page.get_by_text("Dropdown Circulation", exact=True)).to_be_visible()
    assert Loan.objects.get(copy=copy).return_date is None
    page.get_by_role("button", name="Rendre 2 livres", exact=True).click()
    expect(page.get_by_text("2 livres rendus par Mia Lopez.")).to_be_visible()

    copy.refresh_from_db()
    second_copy.refresh_from_db()
    loan = Loan.objects.get(copy=copy, borrower=borrower)
    assert copy.status == Copy.Status.AVAILABLE
    assert second_copy.status == Copy.Status.AVAILABLE
    assert loan.return_date is not None


@pytest.mark.django_db(transaction=True)
def test_student_can_find_book_manually_with_partial_text(page, live_server):
    book = Book.objects.create(title="Manual Search Book", authors="Specific Writer", isbn13="9780316381994")
    copy = Copy.objects.create(book=book, copy_number=1, shelf_location="Green-2")
    borrower = Borrower.objects.create(borrower_id="alex", first_name="Alex", last_name="Reader")

    page.goto(live_server.url)
    select_borrower(page, "alex", "alex - Alex Reader", borrower.id, keyboard=True)
    page.get_by_role("button", name="Continuer").click()
    page.get_by_role("tab", name="Chercher à la main").click()
    page.locator("#copy-filter").fill("Specific Writer")
    expect(page.locator("select[name='manual_copy'] option")).to_have_count(1)
    page.locator("select[name='manual_copy']").select_option(str(copy.id))
    page.get_by_role("button", name="Vérifier le livre").click()

    expect(page.get_by_text("Manual Search Book", exact=True)).to_be_visible()
    page.get_by_role("button", name="Emprunter 1 livre", exact=True).click()
    expect(page.get_by_text("Manual Search Book prêté à Alex Reader.")).to_be_visible()
    assert Loan.objects.filter(copy=copy, borrower=borrower, return_date__isnull=True).exists()


@pytest.mark.django_db(transaction=True)
def test_admin_borrower_view_highlights_current_and_overdue_loans(page, live_server, django_user_model):
    from datetime import timedelta
    from django.utils import timezone

    django_user_model.objects.create_superuser(username="borrowers", password="secret", email="")
    borrower = Borrower.objects.create(borrower_id="mia", first_name="Mia", last_name="Lopez", school_class=SchoolClass.objects.get_or_create(name="3B")[0])
    copy = Copy.objects.create(book=Book.objects.create(title="Overdue classroom book"), copy_number=1, status=Copy.Status.CHECKED_OUT)
    Loan.objects.create(copy=copy, borrower=borrower, due_date=timezone.localdate() - timedelta(days=2))

    page.goto(f"{live_server.url}/staff/login/?next=/borrowers/")
    page.locator("input[name='username']").fill("borrowers")
    page.locator("input[name='password']").fill("secret")
    page.get_by_role("button", name="Se connecter").click()

    expect(page.get_by_role("heading", name="Élèves")).to_be_visible()
    expect(page.get_by_text("Avec des livres empruntés")).to_be_visible()
    expect(page.get_by_text("1 en retard")).to_be_visible()
    page.get_by_role("link", name="ML Mia Lopez mia").click()
    expect(page.get_by_role("heading", name="Mia Lopez")).to_be_visible()
    expect(page.get_by_role("heading", name="Livres empruntés")).to_be_visible()
    expect(page.get_by_role("link", name="Overdue classroom book Exemplaire n°1")).to_be_visible()
    expect(page.get_by_text("1 livre en retard.")).to_be_visible()


@pytest.mark.django_db(transaction=True)
def test_admin_can_delete_one_physical_copy_in_browser(page, live_server, django_user_model):
    django_user_model.objects.create_superuser(username="copies", password="secret", email="")
    book = Book.objects.create(title="Duplicate classroom title")
    first = Copy.objects.create(book=book, copy_number=1)
    second = Copy.objects.create(book=book, copy_number=2)

    page.goto(f"{live_server.url}/staff/login/?next={second.get_absolute_url()}")
    page.locator("input[name='username']").fill("copies")
    page.locator("input[name='password']").fill("secret")
    page.get_by_role("button", name="Se connecter").click()

    expect(page.get_by_role("heading", name="Duplicate classroom title #2")).to_be_visible()
    page.on("dialog", lambda dialog: dialog.accept())
    page.get_by_role("button", name="Retirer l'exemplaire").click()

    expect(page.get_by_text("L'exemplaire n°2 de « Duplicate classroom title » est retiré")).to_be_visible()
    expect(page.get_by_role("heading", name="Duplicate classroom title")).to_be_visible()
    assert Copy.objects.filter(pk=first.id).exists()
    second.refresh_from_db()
    assert second.archived_on is not None
    assert second.status == Copy.Status.ARCHIVED
    first.refresh_from_db()
    assert first.archived_on is None


@pytest.mark.django_db(transaction=True)
def test_admin_can_correct_book_copy_and_borrower_in_browser(page, live_server, django_user_model):
    django_user_model.objects.create_superuser(username="editor", password="secret", email="")
    book = Book.objects.create(title="Title with typo")
    copy = Copy.objects.create(book=book, copy_number=1, shelf_location="Wrong")
    borrower = Borrower.objects.create(borrower_id="student", first_name="Studnt", last_name="Name")

    page.goto(f"{live_server.url}/staff/login/?next={book.get_absolute_url()}")
    page.locator("input[name='username']").fill("editor")
    page.locator("input[name='password']").fill("secret")
    page.get_by_role("button", name="Se connecter").click()

    page.get_by_role("link", name="Modifier le livre").click()
    page.locator("input[name='title']").fill("Correct title")
    page.get_by_role("button", name="Enregistrer le livre").click()
    expect(page.get_by_text("Informations du livre mises à jour.")).to_be_visible()

    page.get_by_role("link", name="#1").click()
    page.get_by_role("link", name="Modifier l'exemplaire").click()
    page.locator("input[name='shelf_location']").fill("A2")
    page.get_by_role("button", name="Enregistrer").click()
    expect(page.get_by_text("Informations de l'exemplaire mises à jour.")).to_be_visible()

    page.goto(f"{live_server.url}{borrower.get_absolute_url()}")
    page.get_by_role("link", name="Modifier l'élève").click()
    page.locator("input[name='first_name']").fill("Student")
    page.locator("input[name='active']").check()
    page.get_by_role("button", name="Enregistrer").click()
    expect(page.get_by_text("Informations de l'emprunteur mises à jour.")).to_be_visible()

    book.refresh_from_db()
    copy.refresh_from_db()
    borrower.refresh_from_db()
    assert book.title == "Correct title"
    assert copy.shelf_location == "A2"
    assert borrower.first_name == "Student"


@pytest.mark.django_db(transaction=True)
def test_admin_can_move_active_loan_to_correct_borrower_in_browser(page, live_server, django_user_model):
    django_user_model.objects.create_superuser(username="loan-editor", password="secret", email="")
    wrong = Borrower.objects.create(borrower_id="wrong-child", first_name="Wrong", last_name="Child")
    correct = Borrower.objects.create(borrower_id="right-child", first_name="Right", last_name="Child", school_class=SchoolClass.objects.get_or_create(name="4A")[0])
    copy = Copy.objects.create(
        book=Book.objects.create(title="Borrowed under wrong name"),
        copy_number=1,
        status=Copy.Status.CHECKED_OUT,
    )
    loan = Loan.objects.create(copy=copy, borrower=wrong)

    page.goto(f"{live_server.url}/staff/login/?next={copy.get_absolute_url()}")
    page.locator("input[name='username']").fill("loan-editor")
    page.locator("input[name='password']").fill("secret")
    page.get_by_role("button", name="Se connecter").click()

    expect(page.get_by_text("Wrong Child", exact=True)).to_be_visible()
    page.get_by_role("link", name="Changer l'emprunteur").click()
    expect(page.get_by_role("heading", name="Changer l'emprunteur")).to_be_visible()
    page.locator("select[name='borrower']").select_option(str(correct.id))
    page.get_by_role("button", name="Changer l'emprunteur").click()

    expect(page.get_by_text("Emprunteur de « Borrowed under wrong name » modifié : Wrong Child remplacé par Right Child.")).to_be_visible()
    expect(page.get_by_text("Right Child", exact=True)).to_be_visible()
    loan.refresh_from_db()
    assert loan.borrower == correct


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
    alpha_borrower = Borrower.objects.create(borrower_id="alpha-user", first_name="Amy", last_name="Zulu", school_class=SchoolClass.objects.get_or_create(name="2B")[0])
    beta_borrower = Borrower.objects.create(borrower_id="beta-user", first_name="Ben", last_name="Alpha", school_class=SchoolClass.objects.get_or_create(name="1A")[0])
    Loan.objects.create(copy=alpha_copy, borrower=alpha_borrower, due_date=timezone.localdate() - timedelta(days=1))
    Loan.objects.create(copy=beta_copy, borrower=beta_borrower, due_date=timezone.localdate() - timedelta(days=2))

    page.goto(f"{live_server.url}/staff/login/?next=/books/")
    page.locator("input[name='username']").fill("sorter")
    page.locator("input[name='password']").fill("secret")
    page.get_by_role("button", name="Se connecter").click()

    page.get_by_role("columnheader", name="Auteur(s)").get_by_role("link").click()
    expect(page.locator("tbody tr").first).to_contain_text("Beta title")

    page.goto(f"{live_server.url}/borrowers/")
    page.get_by_role("columnheader", name="Classe").get_by_role("link").click()
    expect(page.locator("tbody tr").first).to_contain_text("Ben Alpha")

    page.goto(f"{live_server.url}/loans/overdue/")
    page.get_by_role("columnheader", name="Emprunteur", exact=True).get_by_role("link").click()
    expect(page.locator("tbody tr").first).to_contain_text("Ben Alpha")

    page.goto(f"{live_server.url}{alpha.get_absolute_url()}")
    page.get_by_role("columnheader", name="Étagère").get_by_role("link").click()
    expect(page.locator("tbody tr").first).to_contain_text("A1")


@pytest.mark.django_db(transaction=True)
def test_admin_selects_books_and_fetches_missing_covers_in_browser(
    page, live_server, django_user_model, tmp_path, settings, monkeypatch
):
    settings.MEDIA_ROOT = tmp_path
    django_user_model.objects.create_superuser(username="covers", password="secret", email="")
    first = Book.objects.create(title="First missing cover", isbn13="9780316381994")
    second = Book.objects.create(title="Second missing cover", isbn13="9788408052524")
    Copy.objects.create(book=first, copy_number=1)
    Copy.objects.create(book=second, copy_number=1)
    monkeypatch.setattr("library.views.download_cover_by_isbn", lambda isbn: (f"cover:{isbn}".encode(), "jpg"))

    page.goto(f"{live_server.url}/staff/login/?next=/books/")
    page.locator("input[name='username']").fill("covers")
    page.locator("input[name='password']").fill("secret")
    page.get_by_role("button", name="Se connecter").click()

    fetch_button = page.get_by_role("button", name="Récupérer les couvertures manquantes")
    expect(fetch_button).to_be_disabled()
    page.get_by_role("checkbox", name="Sélectionner les livres concernés sur cette page").check()
    expect(page.get_by_text("2 sélectionné(s)")).to_be_visible()
    expect(fetch_button).to_be_enabled()
    fetch_button.click()

    expect(page.get_by_text("Recherche des couvertures terminée : 2 téléchargée(s)")).to_be_visible()
    expect(page.get_by_text("Disponible", exact=True)).to_have_count(2)
    first.refresh_from_db()
    second.refresh_from_db()
    assert first.cover_image
    assert second.cover_image


@pytest.mark.django_db(transaction=True)
def test_admin_imports_enriched_catalog_and_reviews_incomplete_book(
    page, live_server, django_user_model, tmp_path
):
    django_user_model.objects.create_superuser(username="importer", password="secret", email="")
    catalog = tmp_path / "catalog.csv"
    catalog.write_text(
        "Source photo,Photo position,Title,Subtitle,Contributors,ISBN,Publisher,Publication year,Language,"
        "Pages,Format,Category,Topics,Description,Suggested Montessori level,Suggested age range,"
        "Suggested reading level,Identification confidence,Review notes,Bibliographic source URL\n"
        "photo.jpg,left,The Classroom,,A. Teacher,,,2024,en,,Picture book,School and community,"
        "classroom; friendship,A classroom story,Children's House (3-6),4-7,Read-aloud,high,"
        "Confirm ISBN,\n",
        encoding="utf-8",
    )

    page.goto(f"{live_server.url}/staff/login/?next=/books/import/")
    page.locator("input[name='username']").fill("importer")
    page.locator("input[name='password']").fill("secret")
    page.get_by_role("button", name="Se connecter").click()
    page.locator("input[type='file']").set_input_files(catalog)
    page.get_by_role("button", name="Importer les livres").click()

    expect(page.get_by_text("Import du catalogue terminé : 1 livre physique")).to_be_visible()
    expect(page.get_by_text("Fiche à compléter", exact=True)).to_be_visible()
    page.get_by_role("link", name="The Classroom").click()
    expect(page.get_by_role("heading", name="Thèmes")).to_be_visible()
    expect(page.get_by_text("classroom; friendship")).to_be_visible()
    expect(page.get_by_text("Children's House (3-6)")).to_be_visible()


@pytest.mark.django_db(transaction=True)
def test_admin_can_complete_school_setup_in_browser(page, live_server, django_user_model):
    from library.models import SchoolClass, SchoolProfile

    django_user_model.objects.create_superuser(username="setup", password="secret", email="")
    page.goto(f"{live_server.url}/staff/login/?next=/dashboard/")
    page.locator("input[name='username']").fill("setup")
    page.locator("input[name='password']").fill("secret")
    page.get_by_role("button", name="Se connecter").click()

    expect(page.get_by_text("Terminez la configuration de Shelf-School")).to_be_visible()
    page.get_by_role("link", name="Paramètres de l'école").click()
    page.locator("input[name='school_name']").fill("Escola Montserrat")
    page.locator("input[name='short_name']").fill("Montserrat Library")
    page.locator("input[name='default_loan_days']").fill("21")
    page.get_by_role("button", name="Enregistrer les paramètres").click()

    expect(page.get_by_text("Paramètres de l'école enregistrés.")).to_be_visible()
    expect(page.locator(".brand")).to_contain_text("Montserrat Library")
    profile = SchoolProfile.current()
    assert profile.setup_completed is True
    assert profile.default_loan_days == 21
    for width in (1440, 768, 390):
        page.set_viewport_size({"width": width, "height": 1000})
        expect(page.get_by_role("link", name="Classes", exact=True)).to_be_visible()
        expect(page.get_by_role("link", name="Fonctions du personnel", exact=True)).to_be_visible()
        assert page.evaluate("document.documentElement.scrollWidth <= window.innerWidth")
        page.screenshot(path=f"/tmp/shelf-school-settings-{width}.png", full_page=True)
    page.locator("#id_school_name").fill("")
    page.locator("#school-settings-form").evaluate("(form) => form.noValidate = true")
    page.get_by_role("button", name="Enregistrer les paramètres").click()
    expect(page.get_by_text("Ce champ est obligatoire.", exact=True)).to_be_visible()


@pytest.mark.django_db(transaction=True)
def test_system_admin_links_and_synchronizes_matching_borrower_in_browser(
    page, live_server, django_user_model
):
    django_user_model.objects.create_superuser(username="owner", password="secret", email="")
    borrower = Borrower.objects.create(school_id="school-lrueda", first_name="Leo", last_name="Rueda")
    borrower_id = borrower.borrower_id

    page.goto(f"{live_server.url}/staff/login/?next=/settings/")
    page.locator("input[name='username']").fill("owner")
    page.locator("input[name='password']").fill("secret")
    page.get_by_role("button", name="Se connecter").click()

    expect(page.get_by_role("link", name="Ouvrir l'administration avancée (Django)")).to_be_visible()
    page.get_by_role("link", name="Gérer les comptes du personnel").click()
    expect(page.get_by_role("heading", name="Comptes du personnel")).to_be_visible()
    page.get_by_role("link", name="Ajouter un compte du personnel").click()
    page.locator("input[name='username']").fill("lrueda")
    page.locator("input[name='first_name']").fill("Luis")
    page.locator("input[name='last_name']").fill("Rueda")
    page.locator("input[name='email']").fill("lrueda@example.org")
    page.get_by_label("Élève ou personnel existant :", exact=True).select_option(str(borrower.pk))
    page.locator("input[name='password1']").fill("library-test-password-42")
    page.locator("input[name='password2']").fill("library-test-password-42")
    page.get_by_role("button", name="Enregistrer le compte du personnel").click()

    expect(page.get_by_text("Compte du personnel lrueda créé et associé à la fiche existante.")).to_be_visible()
    staff_row = page.get_by_role("row").filter(has_text="lrueda@example.org")
    expect(staff_row).to_contain_text("Luis Rueda")
    expect(staff_row.get_by_role("link", name="Luis Rueda")).to_be_visible()
    account = django_user_model.objects.get(username="lrueda")
    borrower.refresh_from_db()
    assert account.is_staff is True
    assert account.is_superuser is False
    assert borrower.staff_account == account
    assert borrower.borrower_id == borrower_id
    assert borrower.school_id == "school-lrueda"
    assert account.username == "lrueda"
    assert borrower.full_name == account.get_full_name() == "Luis Rueda"
    assert borrower.email == account.email == "lrueda@example.org"
    for width in (1440, 390):
        page.set_viewport_size({"width": width, "height": 900})
        edit = staff_row.get_by_role("link", name="Modifier lrueda", exact=True)
        reset = staff_row.get_by_role("link", name="Réinitialiser le mot de passe de lrueda", exact=True)
        expect(edit.locator("svg")).to_be_visible()
        expect(reset.locator("svg")).to_be_visible()
        for control in (edit, reset):
            box = control.bounding_box()
            assert box["width"] == 44 and box["height"] == 44
        page.screenshot(path=f"/tmp/shelf-school-staff-actions-{width}.png", full_page=True)
    edit.click()
    expect(page.get_by_role("heading", name="Modifier le compte du personnel")).to_be_visible()
    page.get_by_role("link", name="Annuler", exact=True).click()
    staff_row.get_by_role("link", name="Réinitialiser le mot de passe de lrueda", exact=True).click()
    expect(page.get_by_role("heading", name="Réinitialiser le mot de passe")).to_be_visible()


@pytest.mark.django_db(transaction=True)
@pytest.mark.parametrize("width", [390, 1440])
def test_desk_scanner_checkout_and_return_in_browser(page, live_server, django_user_model, width):
    django_user_model.objects.create_user(username="desk", password="secret", is_staff=True)
    borrower = Borrower.objects.create(borrower_id="mia", first_name="Mia", last_name="Lopez", school_class=SchoolClass.objects.get_or_create(name="3B")[0])
    book = Book.objects.create(title="Scanner book")
    copy = Copy.objects.create(book=book, copy_number=1)
    other = Copy.objects.create(book=book, copy_number=2)
    page.set_viewport_size({"width": width, "height": 900})
    page.goto(f"{live_server.url}/staff/login/?next=/pret/")
    page.locator("input[name=username]").fill("desk")
    page.locator("input[name=password]").fill("secret")
    page.get_by_role("button", name="Se connecter", exact=True).click()
    scan = page.locator("#desk-code")
    expect(scan).to_be_focused()
    page.evaluate("window.__marker = 1")

    def scan_code(code):
        page.keyboard.type(code, delay=5)
        page.keyboard.press("Enter")

    def assert_ready():
        expect(scan).to_be_focused()
        expect(scan).to_have_value("")
        assert page.evaluate("window.__marker") == 1
        assert page.evaluate("document.documentElement.scrollWidth <= innerWidth")

    scan_code(borrower.qr_code)
    expect(page.locator(".desk-outcome")).to_contain_text("scannez le livre")
    assert_ready()
    scan_code(copy.qr_code)
    expect(page.locator(".desk-outcome.success")).to_contain_text("Prêt enregistré")
    assert_ready()
    assert Loan.objects.filter(copy=copy, borrower=borrower, return_date__isnull=True).count() == 1
    page.screenshot(path=f"/tmp/biblio-desk-{width}.png", full_page=True)

    # Same copy right away: ignored as a duplicate scan (30 s window), loan stays open.
    scan_code(copy.qr_code)
    expect(page.locator(".desk-outcome.info")).to_contain_text("déjà enregistré")
    assert_ready()
    assert Loan.objects.get(copy=copy).return_date is None

    # Another loan moves the duplicate guard away, then scanning the first copy returns it.
    scan_code(borrower.qr_code)
    expect(page.locator(".desk-outcome")).to_contain_text("scannez le livre")
    scan_code(other.qr_code)
    expect(page.locator(".desk-outcome.success")).to_contain_text("Prêt enregistré")
    assert_ready()
    scan_code(copy.qr_code)
    expect(page.locator(".desk-outcome.success")).to_contain_text("Retour enregistré")
    assert_ready()
    assert Loan.objects.get(copy=copy).return_date is not None
    assert Loan.objects.get(copy=other).return_date is None

    scan_code("COPY:00000000-0000-0000-0000-000000000000")
    expect(page.locator(".desk-outcome.error")).to_contain_text("Étiquette inconnue")
    assert_ready()
    page.screenshot(path=f"/tmp/biblio-desk-{width}-error.png", full_page=True)


@pytest.mark.django_db(transaction=True)
def test_label_sheet_layout_in_browser(page, live_server, django_user_model):
    django_user_model.objects.create_user(username="labels", password="secret", is_staff=True)
    school_class = SchoolClass.objects.get_or_create(name="CE2")[0]
    for number in range(25):
        Borrower.objects.create(borrower_id=f"kid{number}", first_name=f"Élève{number}", last_name=f"Nom{number}", school_class=school_class)
    page.set_viewport_size({"width": 1200, "height": 900})
    page.goto(f"{live_server.url}/staff/login/?next=/labels/class/{school_class.pk}/")
    page.locator("input[name=username]").fill("labels")
    page.locator("input[name=password]").fill("secret")
    page.get_by_role("button", name="Se connecter", exact=True).click()
    page.emulate_media(media="print")
    sheets = page.locator(".sheet")
    expect(sheets).to_have_count(2)
    assert [sheets.nth(i).locator(".label:has(svg)").count() for i in range(2)] == [24, 1]
    mm = 96 / 25.4
    for index, expected in enumerate([24, 1]):
        labels = sheets.nth(index).locator(".label")
        assert labels.count() == expected
        for i in range(expected):
            box = labels.nth(i).bounding_box()
            assert abs(box["width"] - 70 * mm) <= 1 and abs(box["height"] - 37 * mm) <= 1, (index, i, box)
    page.pdf(path="/tmp/biblio-planche.pdf", format="A4", print_background=True)
    page.screenshot(path="/tmp/biblio-planche.png", full_page=True)
