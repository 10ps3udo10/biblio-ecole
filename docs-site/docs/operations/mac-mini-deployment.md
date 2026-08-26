# Mac Deployment

This guide is for a dedicated Mac running Shelf-School in either of these modes:

- **This Mac only:** the kiosk opens only in a browser on the library Mac.
- **Private school network:** computers, phones, and tablets on the trusted
  school Wi-Fi can open the circulation desk.

:::info No reverse proxy required
Neither mode requires Nginx or Caddy for a small, supervised school deployment.
Use `127.0.0.1` for this Mac only or `0.0.0.0` for the private school network.
:::

:::warning Deployment boundary
This pragmatic setup uses Django's lightweight server, which Django does not
classify as production-ready. LAN access is reasonable for a small pilot on a
trusted, private Wi-Fi, but **never expose port 8427 through the router or to the
public internet**. Use dedicated Shelf-School passwords because this HTTP setup
does not encrypt staff credentials with HTTPS.
:::

Shelf-School uses port `8427` in this guide to avoid common development-port
collisions. A less common port is convenient, but it is not a security control.

## Prepare the Mac

Create a dedicated standard macOS user, such as `library`, and keep its password
available to the responsible staff member. Install Git and Python 3.10 or newer.
Keep the application on the Mac's local disk, not in iCloud Drive or another
synchronized folder.

Clone Shelf-School into a stable location that will not be renamed:

```bash
cd /Users/library
git clone https://github.com/mrueda/shelf-school.git
cd shelf-school
```

Create a new macOS virtual environment and install the dependencies:

```bash
python3 -m venv .venv
source .venv/bin/activate
python -m pip install --upgrade pip
python -m pip install -r requirements.txt
```

:::warning Do not copy the old virtual environment
The `.venv` from Linux or another computer contains platform-specific binaries.
Always create a new `.venv` on the Mac. Only the database and `media/` directory
are transferred.
:::

For a new empty library, initialize Shelf-School now:

```bash
python manage.py migrate
python manage.py createsuperuser
python manage.py check
```

To preserve an existing Shelf-School library, follow the next section instead.

## Move an existing library to the Mac

The transfer preserves books, physical copies, borrowers, staff accounts and
passwords, settings, loans, and full loan history. Copy both of these items:

```text
db.sqlite3
media/
```

The database stores the records. `media/` stores downloaded or uploaded covers
and school branding. Circulation and ISBN-reading photos are not stored, so
there are no circulation-photo files to transfer.

### 1. Create the transfer archive

On the existing computer, stop Shelf-School before copying it. For a manually
started server, return to its terminal and press `Control-C`. Then run from the
repository root:

```bash
sqlite3 db.sqlite3 "PRAGMA integrity_check;"
archive="$HOME/shelf-school-data-$(date +%Y%m%d).tar.gz"
tar -czf "$archive" db.sqlite3 media
sha256sum "$archive"
```

The integrity command must print `ok`. Record the checksum, then move the
archive to the Mac with an external drive, a secure network copy, or a Parallels
shared folder. Do not start circulating books on the old computer after making
the final archive.

### 2. Restore it on the Mac

Restore the archive into the freshly cloned repository **before** running the
first migration. Adjust the archive path as needed:

```bash
cd /Users/library/shelf-school
shasum -a 256 ~/Downloads/shelf-school-data-YYYYMMDD.tar.gz
tar -xzf ~/Downloads/shelf-school-data-YYYYMMDD.tar.gz
source .venv/bin/activate
python manage.py migrate
python manage.py check
```

Compare the Mac checksum with the one recorded on the existing computer. Do not
run `createsuperuser`: staff accounts and their password hashes are already in
the transferred database. If an administrator password must be reset, use:

```bash
python manage.py changepassword USERNAME
```

### 3. Compare the records

Run this command on both computers and confirm that the counts match:

```bash
python manage.py shell -c "from django.contrib.auth import get_user_model; from library.models import Book, Copy, Borrower, Loan; print({'books': Book.objects.count(), 'copies': Copy.objects.count(), 'borrowers': Borrower.objects.count(), 'loans': Loan.objects.count(), 'staff': get_user_model().objects.filter(is_staff=True).count()})"
```

Start the Mac copy and verify the school logo, several book covers, staff login,
one existing borrower, and one loan-history page. Complete a test checkout and
return before treating the Mac as the active installation.

Keep the transfer archive unchanged until the Mac has been tested. If the
restore fails, stop Shelf-School, move the restored `db.sqlite3` and `media/`
aside, extract the archive again, and repeat the migration and checks.

## Test the installation

Test it on the Mac before configuring automatic startup:

```bash
python manage.py runserver 127.0.0.1:8427 --noreload
```

Open `http://127.0.0.1:8427/`, complete one checkout and return, then stop the
server with `Control-C`.

## Allow devices on the private Wi-Fi

For circulation from phones, tablets, and other computers, start Shelf-School
on every Mac network interface:

```bash
python manage.py runserver 0.0.0.0:8427 --noreload
```

`0.0.0.0` is a listening address, **not** the address entered in a browser.
Find the Mac's Bonjour name and active LAN address in macOS Terminal:

```bash
scutil --get LocalHostName
interface=$(route -n get default | awk '/interface:/{print $2}')
ipconfig getifaddr "$interface"
```

If the Bonjour name is `Library-Mac` and the address is `192.168.1.25`, test
these URLs from another device on the same Wi-Fi:

```text
http://Library-Mac.local:8427/
http://192.168.1.25:8427/
```

The `.local` name is easier to remember. If the school network does not carry
Bonjour traffic reliably, ask the network administrator to reserve the Mac's IP
address in DHCP and use that address.

On the first connection, macOS may ask whether Python can accept incoming
connections. Allow it. If another device still cannot connect, confirm that:

- It is using the same private Wi-Fi, not a guest network.
- Wireless client isolation or AP isolation is disabled for that network.
- The macOS firewall allows incoming connections for Python.
- No router port forwarding exposes port `8427` to the internet.

The public circulation desk is intentionally available to everyone on that
network. Staff pages still require a staff account. Camera capture uses the
device's image picker; if browser-side barcode detection is unavailable, the
uploaded image is decoded on the Mac and is not retained.

## Create a private secret

Generate a secret once:

```bash
python -c "import secrets; print(secrets.token_urlsafe(50))"
```

Keep the result private. The next section stores it in a user-owned service
file. Do not add that file to Git or publish the secret in an issue.

## Start automatically with launchd

Apple uses `launchd` to manage background processes. A LaunchAgent starts after
the dedicated kiosk user logs in and restarts Shelf-School if it exits.

Create `~/Library/LaunchAgents/org.shelfschool.kiosk.plist` with the following
content. Replace `PASTE_PRIVATE_SECRET_HERE`, `Library-Mac.local`, and
`192.168.1.25`; adjust `/Users/library` if the macOS account has a different
home directory.

```xml
<?xml version="1.0" encoding="UTF-8"?>
<!DOCTYPE plist PUBLIC "-//Apple//DTD PLIST 1.0//EN" "http://www.apple.com/DTDs/PropertyList-1.0.dtd">
<plist version="1.0">
<dict>
  <key>Label</key>
  <string>org.shelfschool.kiosk</string>
  <key>ProgramArguments</key>
  <array>
    <string>/Users/library/shelf-school/.venv/bin/python</string>
    <string>/Users/library/shelf-school/manage.py</string>
    <string>runserver</string>
    <string>0.0.0.0:8427</string>
    <string>--noreload</string>
  </array>
  <key>WorkingDirectory</key>
  <string>/Users/library/shelf-school</string>
  <key>EnvironmentVariables</key>
  <dict>
    <key>DJANGO_SECRET_KEY</key>
    <string>PASTE_PRIVATE_SECRET_HERE</string>
    <key>DJANGO_ALLOWED_HOSTS</key>
    <string>localhost,127.0.0.1,Library-Mac.local,192.168.1.25</string>
    <key>PYTHONUNBUFFERED</key>
    <string>1</string>
  </dict>
  <key>RunAtLoad</key>
  <true/>
  <key>KeepAlive</key>
  <true/>
  <key>StandardOutPath</key>
  <string>/Users/library/Library/Logs/shelf-school.log</string>
  <key>StandardErrorPath</key>
  <string>/Users/library/Library/Logs/shelf-school-error.log</string>
</dict>
</plist>
```

This configuration enables private-LAN access. For a Mac-only kiosk, use
`127.0.0.1:8427` in `ProgramArguments` and
`localhost,127.0.0.1` in `DJANGO_ALLOWED_HOSTS` instead.

Protect and validate the file, then load it:

```bash
chmod 600 ~/Library/LaunchAgents/org.shelfschool.kiosk.plist
plutil -lint ~/Library/LaunchAgents/org.shelfschool.kiosk.plist
launchctl bootstrap "gui/$(id -u)" ~/Library/LaunchAgents/org.shelfschool.kiosk.plist
launchctl kickstart -k "gui/$(id -u)/org.shelfschool.kiosk"
```

Recent macOS versions may ask the user to approve the background service. After
loading it, verify the local and private-LAN URLs, then restart the Mac once to
confirm that Shelf-School returns after login.

## Check status and logs

```bash
launchctl print "gui/$(id -u)/org.shelfschool.kiosk"
tail -f ~/Library/Logs/shelf-school-error.log
```

To stop the service:

```bash
launchctl bootout "gui/$(id -u)" ~/Library/LaunchAgents/org.shelfschool.kiosk.plist
```

Load it again with the `bootstrap` command above.

## Back up the library

The database and uploaded images are both required for a complete recovery:

```text
/Users/library/shelf-school/db.sqlite3
/Users/library/shelf-school/media/
```

Stop the service before taking a filesystem copy. Store backups on a different
device and test restoration periodically. See [Backup](./backup.md) for the
complete policy.

## Upgrade Shelf-School

Choose a time when nobody is circulating books:

```bash
launchctl bootout "gui/$(id -u)" ~/Library/LaunchAgents/org.shelfschool.kiosk.plist
cd /Users/library/shelf-school
cp db.sqlite3 "db.sqlite3.backup-$(date +%Y%m%d)"
source .venv/bin/activate
git pull --ff-only
python -m pip install -r requirements.txt
python manage.py migrate
python manage.py check
launchctl bootstrap "gui/$(id -u)" ~/Library/LaunchAgents/org.shelfschool.kiosk.plist
```

Open the kiosk and perform a test checkout after every upgrade.

## When the requirements change

This setup is no longer appropriate when:

- The Mac is reachable from outside the trusted school network.
- Guest or otherwise untrusted devices share the same network segment.
- Staff need encrypted remote login or the school requires HTTPS.
- Usage grows beyond a small number of concurrent circulation devices.
- The school requires centralized TLS certificates or device management.

At that point, use a production WSGI server, `DEBUG = False`, collected static
files, HTTPS, and a reverse proxy such as Caddy.

## References

- [Apple: Script management with launchd](https://support.apple.com/guide/terminal/script-management-with-launchd-apdc6c1077b-5d5d-4d35-9c19-60f2397b2369/mac)
- [Django deployment checklist](https://docs.djangoproject.com/en/dev/howto/deployment/checklist/)
