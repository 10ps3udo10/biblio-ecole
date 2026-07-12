<div align="center">
  <a href="https://github.com/mrueda/shelf-school">
    <img src="docs-site/static/img/shelf-school-logo.svg" width="180" alt="Shelf-School logo">
  </a>
  <p><em>Open-source circulation for small school libraries</em></p>
</div>

# Shelf-School

**A small, self-hosted library system centered on the moment a student borrows
or returns a physical book.**

[![Build](https://github.com/mrueda/shelf-school/actions/workflows/build-and-test.yml/badge.svg)](https://github.com/mrueda/shelf-school/actions/workflows/build-and-test.yml)
[![Documentation Status](https://github.com/mrueda/shelf-school/actions/workflows/documentation.yml/badge.svg)](https://github.com/mrueda/shelf-school/actions/workflows/documentation.yml)
[![Documentation](https://img.shields.io/badge/docs-online-0b5cad)](https://mrueda.github.io/shelf-school/)
[![Version](https://img.shields.io/badge/version-0.1.0--dev-d68b00)](VERSION)
[![Python](https://img.shields.io/badge/python-%3E%3D3.10-blue)](requirements.txt)
[![Django](https://img.shields.io/badge/django-5.x-0c4b33)](https://www.djangoproject.com/)
[![License](https://img.shields.io/badge/license-MIT-blue.svg)](LICENSE)

Shelf-School provides a public self-service kiosk where students choose their
name and select checkout or return. Checkout books are
normally identified from a photograph of a Shelf-School QR label or ISBN. If a
photo cannot be read, partial title, author, ISBN, shelf, and copy-number search
provides a manual fallback. For returns, Shelf-School shows only the selected
borrower's current loans and allows one or several books to be returned together.

Students need no accounts or library cards. Staff sign in separately for
cataloging, borrowers, reports, school settings, and backups.

**Project status:** `0.1.0-dev`. Shelf-School is under active development and
has not reached its first stable release.

**Documentation:** <https://mrueda.github.io/shelf-school/>

**Quick Start:** <https://mrueda.github.io/shelf-school/docs/getting-started/quickstart>

**Self-Service:** <https://mrueda.github.io/shelf-school/docs/usage/self-service>

## Highlights

- Public checkout and return with a short, child-facing workflow.
- Local QR and ISBN decoding with `zxing-cpp`.
- Free Open Library metadata lookup and exact-ISBN web-search fallback.
- One QR label and loan history per physical copy.
- Photo intake, borrower CSV import, overdue reports, and SQLite backup.
- No paid AI service or student authentication required.
- Pytest and Playwright browser coverage.

ISBN-intake and circulation photos are decoded for one request and never
stored. Available catalog covers are downloaded from Open Library; intentional
no-ISBN cover photos are stored in `media/covers/` and can be removed later.

## Quick Start

```bash
python3 -m venv .venv
source .venv/bin/activate
python -m pip install -r requirements.txt
python -m playwright install chromium
python manage.py migrate
python manage.py createsuperuser
python manage.py runserver 127.0.0.1:8001
```

Open the public kiosk at <http://127.0.0.1:8001/> and staff login at
<http://127.0.0.1:8001/admin/login/>.

## Development

Run application checks:

```bash
python manage.py check
python manage.py makemigrations --check --dry-run
python -m pytest -q
```

Build the documentation:

```bash
cd docs-site
npm ci
npm run typecheck
npm run build
```

The **Build and test** and **Documentation** GitHub Actions workflows are
manual-only and must be started from the repository Actions tab.

## Author

Written by Manuel Rueda.

Repository: <https://github.com/mrueda/shelf-school>

## Copyright and License

Copyright (C) 2026 Manuel Rueda.

Shelf-School is distributed under the MIT License. See [LICENSE](LICENSE).
