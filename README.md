# ShelfSchool

Open-source library management for small schools.

ShelfSchool helps small school libraries catalog books, track physical copies, and handle circulation with QR/barcode photos. It is self-hosted, Django-based, and designed for simple day-to-day use by librarians, teachers, and school staff.

## Features

- Book catalog with title, author, ISBN, publisher, year, language, cover image, and description
- Physical copy tracking with one QR code per copy
- Borrower records with usernames, classes, email addresses, and borrower QR codes
- Circulation workflow for checking books out and checking them back in
- Photo-based circulation using copy QR labels, with ISBN barcode fallback when only one matching copy exists
- No-cost photo intake from ISBN barcode photos using local barcode decoding and Open Library metadata lookup
- Configurable school profile for school name, contact details, label footer, and default loan period
- Dashboard with book/copy/loan/overdue counts
- CSV import/export
- SQLite backup download
- Django admin for maintenance
- Pytest and Playwright test coverage

## How It Works

ShelfSchool separates titles from physical books:

- `Book` represents a title, such as *The Hobbit*.
- `Copy` represents one physical item on a shelf.
- `Loan` always references a `Copy`, not just a `Book`.

Each copy gets its own QR payload:

```text
COPY:<copy-uuid>
```

That copy QR code is the preferred identifier for circulation because ISBNs identify titles, not individual physical copies.

## No-Cost Photo Workflows

ShelfSchool does not require a paid AI API.

For book intake:

1. Take or upload a close-up photo of the ISBN barcode.
2. ShelfSchool decodes the barcode locally with open-source tooling.
3. The app looks up metadata through the free Open Library Books API.
4. A `Book` and first `Copy` are created.
5. A QR label can be printed for the physical copy.

For circulation:

1. Select the borrower.
2. Choose `Check out` or `Check in / return`.
3. Take or upload a photo of the copy QR label.
4. ShelfSchool updates the copy status and loan history.

An ISBN barcode can be used for circulation only when it resolves to exactly one matching copy.

## Technology Stack

- Python
- Django
- SQLite by default
- Django templates
- Local filesystem media storage
- `qrcode` for QR label generation
- `zxing-cpp` for local barcode/QR decoding
- Pytest
- Playwright

## Local Development

Create a virtual environment and install dependencies:

```bash
python3 -m venv .venv
source .venv/bin/activate
pip install -r requirements.txt
python -m playwright install chromium
```

Create the database and admin user:

```bash
python manage.py migrate
python manage.py createsuperuser
```

Run the development server:

```bash
python manage.py runserver 127.0.0.1:8001
```

Open:

```text
http://127.0.0.1:8001/
```

If port `8001` is already in use, choose another port.

## First Setup

After logging in as an admin:

1. Open the Django admin.
2. Edit `School profile` to set the school name, contact details, label footer, and default loan period.
3. Add borrowers with usernames.
4. Add books manually, by CSV import, or through photo intake.
5. Print copy QR labels and attach them to books.
6. Use `Circulation` for check out and check in.

## Useful URLs

```text
/                       Dashboard
/books/                 Book search and catalog
/books/photo-intake/    Add a book from a barcode photo
/borrowers/             Borrower list
/circulation/           Check out / check in workflow
/admin/                 Django admin
```

## Tests

Run the full test suite:

```bash
pytest
```

Run only the browser tests:

```bash
pytest tests/test_playwright.py
```

The Playwright tests use Django's live test server and exercise real rendered pages in Chromium.

## Data and Backups

By default, local data is stored in:

```text
db.sqlite3
media/
```

These files are ignored by git. Use the SQLite backup download in the app before moving, upgrading, or redeploying a live school installation.

## License

ShelfSchool is released under the MIT License. See `LICENSE`.
