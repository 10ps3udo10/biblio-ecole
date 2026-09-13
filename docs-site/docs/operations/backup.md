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
The download is a consistent SQLite snapshot, so circulation can continue while
it is created. Covers and branding must still be backed up separately.

## Complete backup

For a **complete recovery point**, preserve both the database and media:

1. Stop Shelf-School so the database is not changing.
2. Copy `db.sqlite3`.
3. Copy the complete `media/` directory.
4. Store both outside the application machine.

Test restoration on a separate installation before relying on a backup policy.
Shelf-School intentionally does not provide one-click web restoration because
replacing a live SQLite database is destructive and can corrupt active work.

## Verified full archives

**Backups are manual; nothing runs on a schedule.** Create an archive when
needed on Linux or macOS. **Stop Shelf-School first** so database
records and media remain consistent throughout the archive.

From the repository, using the account that owns the library:

```bash
.venv/bin/python tools/library_backup.py create --destination /path/to/backups
```

The destination folder must already exist. Each archive contains a SQLite
snapshot, every regular media file, and a checksum manifest. The command
checks database integrity and verifies the completed archive before publishing
its filename. It never includes your virtual environment or service secret.
Keep the secret separately in a secure location.

Archives have unique timestamped names and are readable only by their owner.
No automatic retention policy deletes older backups. Keep the destination
outside the repository, monitor its free space, and periodically copy a verified
archive to another device.

### Rehearse recovery

Extract into a **new folder**:

```bash
.venv/bin/python tools/library_backup.py restore /path/to/backups/shelf-school-TIMESTAMP-ID.tar.gz \
  --destination /path/to/recovery-check
```

The command verifies checksums and database integrity before creating the
destination. It rejects unsafe archive entries and never overwrites an existing
folder. This restore command accepts archives created by the helper; the simple
`tar` archives described below still use the manual extraction procedure.

The new folder contains `db.sqlite3`, `media/`, and `manifest.json`. To
complete a rehearsal, install a separate Shelf-School checkout, copy the restored
database and media into it, run migrations, and check books, covers, staff login,
and loans. Keep this test installation separate from the active library.

For actual recovery, stop the live service, preserve its
current database and media, replace them with the verified restored copies,
then run `python manage.py migrate` and `python manage.py check` as the library
account before starting the service again.

## Manual transfer archive

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
