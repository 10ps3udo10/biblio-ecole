# Mac Deployment

## Quick path

After Git, Make, and a compatible Python are installed, open Terminal as the
macOS user that will own the library:

```bash
git clone https://github.com/mrueda/shelf-school.git
cd shelf-school
make setup PYTHON=python3.12
make start
```

Open **http://localhost:8427/**. Keep Terminal open; press **Control-C** to stop.

**Moving an existing library?** Copy its `db.sqlite3` and `media/` into the
cloned folder **before** running `make setup`. Existing accounts and passwords
are preserved, so there is no need to create another administrator.

Setup creates or reuses `.venv`, installs dependencies, applies database
migrations, checks Django, and asks for the first system administrator only when
none is active. It creates a private signing key automatically. It does not
install a browser, start a service, download book covers, or schedule backups.

:::warning Deployment boundary
These commands use Django's lightweight server, not a production WSGI server.
They are intended for a supervised local pilot or trusted private school Wi-Fi.
Never expose port 8427 through the router or to the public internet. HTTP does
not encrypt passwords; use dedicated Shelf-School credentials.
Nginx and Caddy are not required for this setup.
:::

## Prepare the Mac

Use a dedicated standard macOS account, such as `library`, for the application
and its data. Keep a separate macOS administrator account for optional boot-time
service installation. Do not run `make setup` with `sudo`.

Keep the project on the Mac's local disk, outside iCloud Drive and other
synchronized folders. A stable location such as
`/Users/library/shelf-school` is suitable.

<details className="alert alert--info">
<summary><strong>Git, Make, or Python is missing or too old</strong></summary>

Check the installed commands:

```bash
git --version
make --version
python3.12 --version
```

A fresh Mac may offer to install Apple's developer tools when you type `git`.
Complete that dialog. If Git or Make is still missing, install the
[Apple command-line tools](https://developer.apple.com/documentation/xcode/installing-the-command-line-tools/):

```bash
xcode-select --install
```

Shelf-School requires **Python 3.10 or newer**. Some older Macs still resolve
`python3` to Python 3.8. Install a compatible package from
[Python's macOS downloads](https://www.python.org/downloads/macos/), then specify
the versioned command in setup.

The Intel Catalina machine tested for this project used
[Python 3.12.10](https://www.python.org/downloads/release/python-31210/) and
`make setup PYTHON=python3.12`. That is a tested older-machine example, not a
claim that 3.12.10 is the latest security release.

An incompatible existing `.venv` is never deleted automatically. Rename that
folder and rerun setup with the correct Python. Keep `db.sqlite3` and `media/`
unchanged. Never copy a Linux virtual environment to the Mac.

</details>

## Move an existing library to the Mac

Transfer **both** `db.sqlite3` and the complete `media/` folder. They contain
books, physical copies, borrowers, staff accounts and password hashes, settings,
loans, covers, and school branding. Circulation and ISBN-reading photos are not
stored.

### Quick transfer

1. Stop Shelf-School on both computers.
2. Copy `db.sqlite3` and `media/` from the old computer into the cloned project
   on the Mac.
3. If a temporary library already exists on the Mac, move its database and
   media folder aside first. Do not merge two libraries.
4. As the macOS `library` user, run:

```bash
cd /Users/library/shelf-school
make setup PYTHON=python3.12
make start
```

It is fine if you already ran migrations or created an administrator on the
Mac. The transferred database replaces that temporary library, including its
accounts. Keep the old computer unchanged until the Mac has been tested.

### Recommended verified transfer

For the school's final transfer, use a verified database-and-media archive.

On the old computer, stop the app and run:

```bash
make backup
```

Move the archive printed by that command to the Mac. From the cloned project
on the Mac, restore it into a **new folder**, adjusting the archive path:

```bash
python3.12 tools/library_backup.py restore ~/Downloads/shelf-school-ARCHIVE.tar.gz --destination ../restored-library
```

The tool checks file hashes and database integrity. Copy `db.sqlite3` and
`media/` from `restored-library` into the project, moving any temporary versions
aside first. Then run `make setup PYTHON=python3.12` and `make start`.
Keep the archive unchanged until the Mac has been tested.

### Validate the transferred library

Check several books, their covers, an existing borrower, and loan history.
Sign in with a transferred Staff account, then complete a test checkout and
return. Do not continue circulating books on the old computer after the final
transfer.

To reset a transferred administrator's password:

```bash
.venv/bin/python manage.py changepassword USERNAME
```

## Allow devices on the private Wi-Fi

`make start` defaults to **this Mac only**. To allow trusted LAN devices, stop
the running app and restart it with an explicit listening address and allowed
browser hostnames. Substitute the actual Mac name and LAN address:

```bash
make start BIND=0.0.0.0 HOSTS=localhost,127.0.0.1,Library-Mac.local,192.168.1.25
```

Open `http://Library-Mac.local:8427/` or `http://192.168.1.25:8427/` from another
device. **Do not enter 0.0.0.0 in the browser**; it is the listening address.

Find the Mac's name and active network address:

```bash
scutil --get LocalHostName
interface=$(route -n get default | awk '/interface:/{print $2}')
ipconfig getifaddr "$interface"
```

Allow Python's incoming connections if macOS asks. Devices must share the
private network, not an isolated guest Wi-Fi. If the IP address changes, update
`HOSTS`; a DHCP reservation can keep the address stable.

Use `PORT=8428` to choose a different port. A less common port is convenient,
not a security control. Camera permissions vary by browser over plain HTTP;
manual search and image uploads remain available.

## Start automatically with launchd

Manual `make start` runs in a user's Terminal session. For a dedicated Mac that
must remain available across login/logout, install the **LaunchDaemon** once.

First stop the manually running app. Then open Terminal in the **macOS
administrator account**, enter the project folder, and run:

```bash
cd /Users/library/shelf-school
make service-install SERVICE_USER=library
```

The command asks for the macOS administrator's password through `sudo`.
Shelf-School itself runs as the non-root `library` account. No plist editing is
needed. The helper verifies dependencies, write access, and pending migrations.

For private-Wi-Fi access, install with the same explicit network settings:

```bash
make service-install SERVICE_USER=library BIND=0.0.0.0 HOSTS=localhost,127.0.0.1,Library-Mac.local,192.168.1.25
```

Service settings are saved, so they need not be repeated when starting it.
To change them, rerun `service-install` with the desired settings.
If an older LaunchAgent is running, unload it from its owner's session first;
only one server should use the port.

### Everyday service commands

From the project folder in the macOS administrator's Terminal:

| Command | Effect |
| --- | --- |
| `make service-status` | Show launchd's service status |
| `make service-stop` | Stop the background app |
| `make service-start` | Start it again with its saved settings |

Do not run `make start` while the service is already running.

:::warning Sleep and FileVault
A service cannot serve other devices while the Mac is asleep. Configure the Mac
to stay awake during library hours; the display can still turn off.
FileVault may require unlocking the disk after a cold boot before services can
start. Test an actual restart and logout on the school's Mac.
:::

The service logs are in the library user's `~/Library/Logs/` folder:

```bash
sudo tail -f /Users/library/Library/Logs/shelf-school-error.log
```

<details className="alert alert--info">
<summary><strong>Where is the private secret, and why is it needed?</strong></summary>

Make commands store the installation's signing key in `.shelf-school-secret`
with owner-only permissions. Git ignores the file. It is not a login password
or a paid API key, and it does not encrypt the database or photos.

The key signs login sessions and circulation confirmations. Keep it unchanged
across restarts and upgrades. The service installer reuses it for a new service;
an already installed service retains its existing key in its protected plist.

The database-and-media archive does not include this key. Store it separately
if you need to preserve sessions. A new key on a new Mac is acceptable; users
will need to sign in again.

</details>

## Back up the library

Backups are **manual only**. Stop the app or service, then run as `library`:

```bash
make backup
```

The command prints the verified archive path under `backups/`. For an external
drive, use an existing destination directory:

```bash
make backup DEST=/Volumes/LibraryBackup
```

No backup schedule is installed. Keep a copy off the Mac and test restoration.
See [Backup and recovery](./backup.md) for details.

## Upgrade Shelf-School

Choose a time when nobody is circulating books.

1. As the macOS administrator, run `make service-stop`, or use Control-C for a
   manually started server.
2. As `library`, from the project folder:

```bash
make backup
git pull --ff-only
make setup PYTHON=python3.12
```

3. As the macOS administrator, run `make service-start`. For a manually run
   installation, use `make start` instead.
4. Verify the kiosk and a test checkout.

Setup preserves existing records and administrator credentials; it does not
replace the database or create duplicate accounts. It does not pull Git changes
or create backups on its own.

## Troubleshooting

- **Port already in use:** stop the other Shelf-School process or use
  `make start PORT=8428`.
- **Invalid HTTP_HOST:** add the actual browser hostname or IP to `HOSTS`.
  Reinstall the service with the updated settings if using launchd.
- **No administrator and no interactive Terminal:** setup leaves the prepared
  library intact. Run `make admin` in Terminal.
- **Pending migrations:** stop the app and run `make setup PYTHON=python3.12`.
- **Need to inspect the installation:** run `make check`.
- **Need the command list:** run `make help`.

If the Mac becomes internet-facing, shares an untrusted network, or requires
encrypted remote access, use a production WSGI server, HTTPS, and a reverse
proxy such as Caddy. See the
[Django deployment checklist](https://docs.djangoproject.com/en/5.2/howto/deployment/checklist/).
