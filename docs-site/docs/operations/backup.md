# Backup

The default installation stores school data in:

```text
db.sqlite3
media/
```

The SQLite database contains books, copies, borrowers, school settings, and
loan history. **The media directory contains uploaded covers and branding.**

## Download the database

Sign in with a staff administrator account, open **Settings**, and select **Download database
backup**. The backup endpoint is unavailable to signed-out kiosk users.

## Complete backup

For a **complete recovery point**, preserve both the database and media:

1. Stop Shelf-School so the database is not changing.
2. Copy `db.sqlite3`.
3. Copy the complete `media/` directory.
4. Store both outside the application machine.

Test restoration on a separate installation before relying on a backup policy.
Shelf-School intentionally does not provide one-click web restoration because
replacing a live SQLite database is destructive and can corrupt active work.

For a complete, portable archive on Linux, stop Shelf-School and run:

```bash
sqlite3 db.sqlite3 "PRAGMA integrity_check;"
archive="$HOME/shelf-school-data-$(date +%Y%m%d).tar.gz"
tar -czf "$archive" db.sqlite3 media
sha256sum "$archive"
```

The integrity check must print `ok`. Keep the checksum with the backup and
verify it after transferring the archive. Do not include `.venv`; dependencies
must be installed again on the destination operating system.

For the complete macOS transfer and verification procedure, see
[Mac Deployment](./mac-mini-deployment.md#move-an-existing-library-to-the-mac).

## Before upgrades

Create a backup before pulling code, installing dependencies, or applying new
migrations:

```bash
source .venv/bin/activate
python manage.py migrate
python manage.py check
```
