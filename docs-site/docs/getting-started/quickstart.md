# Quick Start

## Requirements

- Python 3.10 or newer.
- A camera-equipped phone, tablet, or computer for photo workflows.
- Node.js 20 or newer only when building this documentation site.

## Install

From the repository root:

```bash
python3 -m venv .venv
source .venv/bin/activate
python -m pip install --upgrade pip
python -m pip install -r requirements.txt
python -m playwright install chromium
```

Create the database and administrator:

```bash
python manage.py migrate
python manage.py createsuperuser
```

Start Shelf-School:

```bash
python manage.py runserver 127.0.0.1:8001
```

Open the public circulation kiosk:

```text
http://127.0.0.1:8001/
```

Open staff administration:

```text
http://127.0.0.1:8001/admin/login/
```

The Django development server is suitable for local testing. **Do not expose it
directly to the public internet.**

## Next steps

1. Sign in as the administrator.
2. Open **Settings** and configure the school.
3. Add or import borrowers.
4. Catalog books and print copy QR labels.
5. Sign out and test the public kiosk.
