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

To preserve an existing Shelf-School library, follow the next section. It is
safe to do so even if the three commands above have already been run; there is
no need to reinstall Shelf-School or recreate the virtual environment.

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

The transferred `db.sqlite3` replaces the empty database created during setup.
If `createsuperuser` was already run on the Mac, that temporary account is
replaced too; the staff accounts from the transferred library become active.

### Quick transfer

Use this mode when both computers and the transfer drive or shared folder are
under your control:

1. Stop Shelf-School on both computers. For a manually started server, return
   to its terminal and press `Control-C`.
2. Copy `db.sqlite3` and the complete `media/` directory from the old computer.
3. Place them in `/Users/library/shelf-school` on the Mac, replacing the
   temporary versions there.
4. From that directory, run:

```bash
source .venv/bin/activate
python manage.py migrate
python manage.py check
```

That is a complete migration. There is no need to reinstall Shelf-School or
create another virtual environment.

### Recommended verified transfer

Use this mode for the school's final transfer or whenever the old computer
contains the only current copy of the library. It adds a database integrity
check, a single transfer archive, and a checksum that detects a damaged or
incomplete copy.

On the existing computer, stop Shelf-School. Then run from the repository root:

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

On the Mac, preserve the temporary database and media, verify and extract the
archive, and update the transferred database. Adjust the archive path as
needed:

```bash
cd /Users/library/shelf-school
backup="$HOME/shelf-school-empty-install-$(date +%Y%m%d-%H%M%S)"
mkdir -p "$backup"
if [ -f db.sqlite3 ]; then mv db.sqlite3 "$backup"/; fi
if [ -d media ]; then mv media "$backup"/; fi
shasum -a 256 ~/Downloads/shelf-school-data-YYYYMMDD.tar.gz
tar -xzf ~/Downloads/shelf-school-data-YYYYMMDD.tar.gz
source .venv/bin/activate
python manage.py migrate
python manage.py check
```

Compare the Mac checksum with the one recorded on the existing computer. Keep
the archive unchanged until the Mac has been tested. If restoration fails,
stop Shelf-School, move the restored `db.sqlite3` and `media/` aside, extract
the archive again, and repeat the migration and checks.

With either transfer mode, do not run `createsuperuser` again unless the
transferred library has no usable staff administrator: staff accounts and their
password hashes are already in the database. To reset an administrator
password, use:

```bash
python manage.py changepassword USERNAME
```

### Validate the transferred library

Run this command on both computers and confirm that the counts match:

```bash
python manage.py shell -c "from django.contrib.auth import get_user_model; from library.models import Book, Copy, Borrower, Loan; print({'books': Book.objects.count(), 'copies': Copy.objects.count(), 'borrowers': Borrower.objects.count(), 'loans': Loan.objects.count(), 'staff': get_user_model().objects.filter(is_staff=True).count()})"
```

Start the Mac copy and verify the school logo, several book covers, staff login,
one existing borrower, and one loan-history page. Complete a test checkout and
return before treating the Mac as the active installation.

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

Keep the result private. The next section stores it in a protected system
service file. Do not add that file to Git or publish the secret in an issue.

<details className="alert alert--info">
<summary><strong>Why does Shelf-School need this secret?</strong></summary>

`DJANGO_SECRET_KEY` is the installation's private cryptographic signing key. It
protects staff login sessions and signs short-lived circulation confirmations,
preventing checkout or return details from being altered in the browser. It is
not an administrator password, a paid API key, or a key for encrypting the
database, photos, or account passwords.

Generate it once and keep the same value across restarts and upgrades. Changing
it signs staff out and invalidates pending circulation confirmations, but does
not remove books, borrowers, loans, or passwords. If the database is moved to a
new Mac, using a new secret is acceptable; everyone will simply need to sign in
again. Keep a secure backup of the deployed value and never commit it to Git.

</details>

## Start automatically with launchd

Apple uses `launchd` to manage background processes. How Shelf-School is
started determines when it is available:

| Method | Starts | Stops |
| --- | --- | --- |
| Terminal command | When a person runs it | Terminal closes or that user logs out |
| LaunchAgent | When its macOS user logs in | That user logs out |
| **LaunchDaemon** | **When the Mac boots** | **Mac shuts down or the service is stopped** |

For a dedicated library Mac, use the **LaunchDaemon** below. It keeps
Shelf-School available over Wi-Fi while macOS users log in and out. Although
`root` installs and manages the service, Shelf-School itself runs as the
dedicated, non-administrator `library` user.

:::note When a LaunchAgent is enough
A LaunchAgent is simpler if the Mac automatically signs in to one dedicated
kiosk account and Shelf-School only needs to run during that login session. A
LaunchDaemon is the appropriate choice when the app must work before login and
survive user logout.
:::

Create `~/org.shelfschool.server.plist` with the following content. Replace
`PASTE_PRIVATE_SECRET_HERE`, `Library-Mac.local`, and `192.168.1.25`. Replace
`library` and `/Users/library` if the macOS account that owns the installation
has a different short name or home directory.

```xml
<?xml version="1.0" encoding="UTF-8"?>
<!DOCTYPE plist PUBLIC "-//Apple//DTD PLIST 1.0//EN" "http://www.apple.com/DTDs/PropertyList-1.0.dtd">
<plist version="1.0">
<dict>
  <key>Label</key>
  <string>org.shelfschool.server</string>
  <key>UserName</key>
  <string>library</string>
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

Install the file as a protected system service, validate it, and load it:

```bash
chmod 600 ~/org.shelfschool.server.plist
sudo cp ~/org.shelfschool.server.plist /Library/LaunchDaemons/
sudo chown root:wheel /Library/LaunchDaemons/org.shelfschool.server.plist
sudo chmod 600 /Library/LaunchDaemons/org.shelfschool.server.plist
sudo plutil -lint /Library/LaunchDaemons/org.shelfschool.server.plist
sudo launchctl bootstrap system /Library/LaunchDaemons/org.shelfschool.server.plist
sudo launchctl kickstart -k system/org.shelfschool.server
rm ~/org.shelfschool.server.plist
```

After loading it, verify the local and private-LAN URLs. Restart the Mac, but do
not log in immediately; confirm from another device that Shelf-School is
already available. Then log in and log out once and confirm that it remains
available.

:::warning Keep the Mac awake
`launchd` restarts Shelf-School if its process exits, but it cannot serve other
devices while the Mac is asleep. In **System Settings > Energy Saver**, enable
the option that prevents automatic sleeping while the display is off. The
display may still turn off normally.
:::

## Check status and logs

```bash
sudo launchctl print system/org.shelfschool.server
tail -f /Users/library/Library/Logs/shelf-school-error.log
```

To stop the service:

```bash
sudo launchctl bootout system /Library/LaunchDaemons/org.shelfschool.server.plist
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
sudo launchctl bootout system /Library/LaunchDaemons/org.shelfschool.server.plist
cd /Users/library/shelf-school
cp db.sqlite3 "db.sqlite3.backup-$(date +%Y%m%d)"
source .venv/bin/activate
git pull --ff-only
python -m pip install -r requirements.txt
python manage.py migrate
python manage.py check
sudo launchctl bootstrap system /Library/LaunchDaemons/org.shelfschool.server.plist
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
