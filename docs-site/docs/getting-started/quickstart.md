# Quick Start

## Requirements

- Git.
- Python 3.10 or newer.
- A camera-equipped phone, tablet, or computer for photo workflows.
- Node.js 20 or newer only when building this documentation site.

## Install

Shelf-School is currently installed from its GitHub source code. It is **not yet
available as a `pip install shelf-school` package**. Using Git also makes future
updates possible with `git pull`.

:::caution macOS: check Git and Python first
Open **Terminal** and check Git:

```bash
git --version
```

On a fresh Mac, this command may open Apple's developer-tools installation
dialog. Complete that installation, then run `git --version` again.

Check the Python selected by the terminal **before creating `.venv`**:

```bash
python3 --version
```

Shelf-School requires Python 3.10 or newer. Some Macs still resolve `python3`
to Python 3.8. In that case, install an
[official macOS Python package](https://www.python.org/downloads/macos/). The
`universal2` installer supports both Intel and Apple silicon Macs. Then create
the environment with the installed versioned command; for example, the tested
Intel installation using Python 3.12.10 required:

```bash
python3.12 -m venv .venv
```

Once `.venv` is activated, the remaining `python` commands use that selected
interpreter. If `.venv` was already created with Python 3.8, move it aside and
create it again with the newer command.
:::

Clone Shelf-School and enter its directory:

```bash
git clone https://github.com/mrueda/shelf-school.git
cd shelf-school
```

Create the virtual environment and install the dependencies. Replace `python3`
with the verified versioned command, such as `python3.12`, when necessary:

```bash
python3 -m venv .venv
source .venv/bin/activate
python -m pip install --upgrade pip
python -m pip install -r requirements.txt
python -m playwright install chromium
```

Create the database and initial staff administrator:

```bash
python manage.py migrate
python manage.py createsuperuser
```

Start Shelf-School:

```bash
python manage.py runserver 127.0.0.1:8427
```

Open the public circulation kiosk:

```text
http://127.0.0.1:8427/
```

Open the staff sign-in directly, or select **Staff login** in the public
header:

```text
http://127.0.0.1:8427/staff/login/
```

The Django development server is suitable for local testing and a small pilot
on a trusted private school network. **Do not expose it directly to the public
internet.**

Shelf-School uses Django accounts internally, but staff accounts are managed in
Shelf-School. A system administrator can follow the clearly marked **Advanced
(Django Admin)** link in Settings for exceptional technical permission or
database maintenance.

For a dedicated Mac serving either its own browser or devices on trusted school
Wi-Fi, continue with [Mac Deployment](../operations/mac-mini-deployment.md) to
configure data transfer, private-LAN access, automatic startup, and backups
without Nginx or Caddy.

## Next steps

1. Sign in with the staff administrator account.
2. Open **Settings** and configure the school.
3. Add or import borrowers.
4. Catalog books and print copy QR labels.
5. Sign out and test the public kiosk.
