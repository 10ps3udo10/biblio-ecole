# Mac Mini Kiosk Deployment

This guide is for a dedicated Mac where Shelf-School is opened **only in a
browser on that same computer**. It is a practical setup for a supervised
school library kiosk.

:::info No reverse proxy required
This single-computer setup binds Shelf-School to `127.0.0.1`. Other computers,
phones, and tablets cannot connect to it, so Nginx and Caddy are not required.
:::

:::warning Deployment boundary
This guide uses Django's lightweight server for a local-only kiosk. Django does
not classify that server as production-ready. **Do not change the address to
`0.0.0.0` or expose port 8001 to the school network.** Follow a future hardened
network deployment guide before allowing other devices to connect.
:::

## Prepare the Mac

Create a dedicated standard macOS user, such as `library`, and keep its password
available to the responsible staff member. Install Git and Python 3.10 or newer,
then place Shelf-School in a stable location that will not be renamed:

```text
/Users/library/shelf-school
```

From that directory, install and initialize the application:

```bash
python3 -m venv .venv
source .venv/bin/activate
python -m pip install --upgrade pip
python -m pip install -r requirements.txt
python manage.py migrate
python manage.py createsuperuser
python manage.py check
```

Test it before configuring automatic startup:

```bash
python manage.py runserver 127.0.0.1:8001 --noreload
```

Open `http://127.0.0.1:8001/`, complete one checkout and return, then stop the
server with `Control-C`.

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
content. Replace `PASTE_PRIVATE_SECRET_HERE` and adjust `/Users/library` if the
macOS account has a different home directory.

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
    <string>127.0.0.1:8001</string>
    <string>--noreload</string>
  </array>
  <key>WorkingDirectory</key>
  <string>/Users/library/shelf-school</string>
  <key>EnvironmentVariables</key>
  <dict>
    <key>DJANGO_SECRET_KEY</key>
    <string>PASTE_PRIVATE_SECRET_HERE</string>
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

Protect and validate the file, then load it:

```bash
chmod 600 ~/Library/LaunchAgents/org.shelfschool.kiosk.plist
plutil -lint ~/Library/LaunchAgents/org.shelfschool.kiosk.plist
launchctl bootstrap "gui/$(id -u)" ~/Library/LaunchAgents/org.shelfschool.kiosk.plist
launchctl kickstart -k "gui/$(id -u)/org.shelfschool.kiosk"
```

Recent macOS versions may ask the user to approve the background service. After
loading it, verify `http://127.0.0.1:8001/` and restart the Mac once to confirm
that Shelf-School returns after login.

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

- Students use tablets, phones, or another computer.
- Staff administer Shelf-School from another desk.
- The Mac is reachable from outside the school.
- The school requires centralized TLS certificates or device management.

At that point, use a production WSGI server, `DEBUG = False`, collected static
files, HTTPS, and a reverse proxy such as Caddy. Do not make the local kiosk
reachable merely by changing the bind address.

## References

- [Apple: Script management with launchd](https://support.apple.com/guide/terminal/script-management-with-launchd-apdc6c1077b-5d5d-4d35-9c19-60f2397b2369/mac)
- [Django deployment checklist](https://docs.djangoproject.com/en/dev/howto/deployment/checklist/)
