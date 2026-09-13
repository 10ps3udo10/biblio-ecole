"""Install and control Shelf-School's macOS service."""
import argparse
import os
from pathlib import Path
import plistlib
import pwd
import secrets
import subprocess
import sys
import tempfile


SERVER = "org.shelfschool.server"
DAEMONS = Path("/Library/LaunchDaemons")


def run(*args, **kwargs):
    return subprocess.run([str(arg) for arg in args], check=True, **kwargs)


def service_plist(project, user, hosts, port, secret, bind="127.0.0.1"):
    python = project / ".venv/bin/python"
    logs = Path(pwd.getpwnam(user).pw_dir) / "Library/Logs"
    server = {
        "Label": SERVER, "UserName": user,
        "ProgramArguments": [str(python), str(project / "manage.py"), "runserver", f"{bind}:{port}", "--noreload"],
        "WorkingDirectory": str(project),
        "EnvironmentVariables": {"DJANGO_SECRET_KEY": secret, "DJANGO_ALLOWED_HOSTS": hosts, "PYTHONUNBUFFERED": "1"},
        "RunAtLoad": True, "KeepAlive": True,
        "StandardOutPath": str(logs / "shelf-school.log"),
        "StandardErrorPath": str(logs / "shelf-school-error.log"),
    }
    return server


def write_private(path, data):
    with tempfile.NamedTemporaryFile(dir=path.parent, delete=False) as stream:
        temporary = Path(stream.name)
        try:
            stream.write(data)
            stream.flush()
            os.fchmod(stream.fileno(), 0o600)
            os.fchown(stream.fileno(), 0, 0)
            temporary.replace(path)
        finally:
            temporary.unlink(missing_ok=True)


def loaded(label):
    return subprocess.run(
        ["/bin/launchctl", "print", f"system/{label}"],
        stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL,
    ).returncode == 0


def install(args):
    project = args.project.resolve()
    account = pwd.getpwnam(args.user)
    if account.pw_uid == 0:
        raise ValueError("Choose the dedicated library account, not root.")
    python = project / ".venv/bin/python"
    if not python.is_file() or not (project / "db.sqlite3").is_file():
        raise ValueError("Complete Quick Start or transfer the existing library first.")
    run("/usr/bin/sudo", "-u", args.user, python, "-c",
        "import sys; assert sys.version_info >= (3, 10), 'Python 3.10 or newer required'; import django, PIL, zxingcpp")
    for path in (project, project / "db.sqlite3", project / "media"):
        if path.exists():
            run("/usr/bin/sudo", "-u", args.user, "/bin/test", "-w", path)
    run("/usr/bin/sudo", "-u", args.user, python, project / "manage.py", "check")
    run("/usr/bin/sudo", "-u", args.user, python, project / "manage.py", "migrate", "--check")
    logs = Path(account.pw_dir) / "Library/Logs"
    run("/usr/bin/sudo", "-u", args.user, "/bin/mkdir", "-p", logs)
    secret = secrets.token_urlsafe(50)
    local_secret = project / ".shelf-school-secret"
    if local_secret.exists():
        secret = local_secret.read_text().strip()
        if not secret:
            raise ValueError("The installation secret is empty. Restore it before continuing.")
    server_path = DAEMONS / f"{SERVER}.plist"
    if server_path.exists():
        previous = plistlib.loads(server_path.read_bytes())
        existing = previous.get("EnvironmentVariables", {}).get("DJANGO_SECRET_KEY")
        if existing and existing not in {"change-me-before-deploying", "PASTE_PRIVATE_SECRET_HERE"}:
            secret = existing
    server = service_plist(project, args.user, args.hosts, args.port, secret, args.bind)
    if loaded(SERVER):
        run("/bin/launchctl", "bootout", "system", server_path)
    write_private(server_path, plistlib.dumps(server))
    run("/usr/bin/plutil", "-lint", server_path)
    run("/bin/launchctl", "bootstrap", "system", server_path)
    print(f"Installed. Open http://localhost:{args.port}/.")
    print("Run 'status' to inspect the service.")


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    commands = parser.add_subparsers(dest="command", required=True)
    setup = commands.add_parser("install")
    setup.add_argument("--project", type=Path, default=Path(__file__).resolve().parents[1])
    setup.add_argument("--user", required=True)
    setup.add_argument("--hosts", required=True, help="Comma-separated browser hostnames/IPs, including localhost.")
    setup.add_argument("--bind", choices=["127.0.0.1", "0.0.0.0"], default="127.0.0.1")
    setup.add_argument("--port", type=int, default=8427, choices=range(1024, 65536), metavar="PORT")
    for command in ("status", "stop", "start"):
        commands.add_parser(command)
    args = parser.parse_args()
    if sys.platform != "darwin" or os.geteuid() != 0:
        parser.exit(1, "Run on macOS from an administrator Terminal using sudo.\n")
    try:
        if args.command == "install":
            install(args)
        elif args.command == "status":
            run("/bin/launchctl", "print", f"system/{SERVER}")
        elif args.command == "stop":
            if loaded(SERVER):
                run("/bin/launchctl", "bootout", "system", DAEMONS / f"{SERVER}.plist")
        elif args.command == "start":
            if not loaded(SERVER):
                run("/bin/launchctl", "bootstrap", "system", DAEMONS / f"{SERVER}.plist")
    except (OSError, ValueError, KeyError, subprocess.CalledProcessError, plistlib.InvalidFileException) as exc:
        parser.exit(1, f"Service setup failed: {exc}\n")


if __name__ == "__main__":
    main()
