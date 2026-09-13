"""Prepare and run a local Shelf-School installation without shell activation."""
import argparse
import os
from pathlib import Path
import secrets
import subprocess
import sys


PROJECT = Path(__file__).resolve().parents[1]
SECRET_FILE = ".shelf-school-secret"


def run(project, *args, **kwargs):
    return subprocess.run([str(arg) for arg in args], cwd=project, check=True, **kwargs)


def environment(project):
    path = project / SECRET_FILE
    if not path.exists():
        secret = os.environ.get("DJANGO_SECRET_KEY") or secrets.token_urlsafe(50)
        with open(path, "x", opener=lambda name, flags: os.open(name, flags, 0o600)) as stream:
            stream.write(secret + "\n")
    secret = path.read_text().strip()
    if not secret:
        raise ValueError("The installation secret is empty. Restore it before continuing.")
    path.chmod(0o600)
    env = os.environ.copy()
    env["DJANGO_SECRET_KEY"] = secret
    return env


def python_path(project):
    python = project / ".venv/bin/python"
    if not python.is_file():
        raise ValueError("Virtual environment missing. Run make setup PYTHON=python3.12 first.")
    return python


def setup(project):
    if sys.version_info < (3, 10):
        raise ValueError("Python 3.10 or newer is required. Install a compatible Python from python.org, then run make setup PYTHON=python3.12.")
    if hasattr(os, "geteuid") and os.geteuid() == 0:
        raise ValueError("Run setup as the library's macOS user, without sudo.")
    venv = project / ".venv"
    if not venv.exists():
        print("Creating .venv...", flush=True)
        run(project, sys.executable, "-m", "venv", venv)
    python = python_path(project)
    try:
        run(project, python, "-c", "import sys; sys.exit(0 if sys.version_info >= (3, 10) else 1)")
    except (OSError, subprocess.CalledProcessError) as exc:
        raise ValueError("The existing .venv is incompatible. Rename that folder and rerun setup. Keep db.sqlite3 and media/ unchanged.") from exc
    print("Installing dependencies...", flush=True)
    run(project, python, "-m", "pip", "install", "-r", project / "requirements.txt")
    env = environment(project)
    run(project, python, "manage.py", "migrate", "--noinput", env=env)
    run(project, python, "manage.py", "check", env=env)
    probe = subprocess.run(
        [str(python), "manage.py", "shell", "-c",
         "import sys; from django.contrib.auth import get_user_model; sys.exit(0 if get_user_model().objects.filter(is_active=True, is_superuser=True).exists() else 10)"],
        cwd=project, env=env,
    )
    if probe.returncode == 10:
        print("Create the first Shelf-School system administrator.", flush=True)
        if not sys.stdin.isatty():
            raise ValueError("Setup completed, but an administrator is missing. Run make admin in an interactive Terminal.")
        run(project, python, "manage.py", "createsuperuser", env=env)
    elif probe.returncode != 0:
        raise ValueError("Could not check administrator accounts; see the error above.")
    print("Ready. Run make start, then open http://localhost:8427/.")


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    commands = parser.add_subparsers(dest="command", required=True)
    commands.add_parser("setup")
    commands.add_parser("check")
    commands.add_parser("admin")
    start = commands.add_parser("start")
    start.add_argument("--bind", choices=["127.0.0.1", "0.0.0.0"], default="127.0.0.1")
    start.add_argument("--hosts", default="localhost,127.0.0.1")
    start.add_argument("--port", type=int, choices=range(1024, 65536), default=8427, metavar="PORT")
    backup = commands.add_parser("backup")
    backup.add_argument("--destination", type=Path, default=Path("backups"))
    args = parser.parse_args()
    try:
        if args.command == "setup":
            setup(PROJECT)
            return
        python = python_path(PROJECT)
        env = environment(PROJECT)
        if args.command == "check":
            run(PROJECT, python, "manage.py", "check", env=env)
            run(PROJECT, python, "manage.py", "migrate", "--check", env=env)
        elif args.command == "admin":
            run(PROJECT, python, "manage.py", "createsuperuser", env=env)
        elif args.command == "backup":
            if args.destination == Path("backups"):
                (PROJECT / "backups").mkdir(exist_ok=True)
            run(PROJECT, python, "tools/library_backup.py", "create", "--destination", args.destination, env=env)
        else:
            env["DJANGO_ALLOWED_HOSTS"] = args.hosts
            run(PROJECT, python, "manage.py", "migrate", "--check", env=env)
            print(f"Open http://localhost:{args.port}/. Press Control-C to stop.", flush=True)
            run(PROJECT, python, "manage.py", "runserver", f"{args.bind}:{args.port}", "--noreload", env=env)
    except (OSError, ValueError, subprocess.CalledProcessError) as exc:
        parser.exit(1, f"Setup error: {exc}\n")
    except KeyboardInterrupt:
        parser.exit(0, "\nStopped.\n")


if __name__ == "__main__":
    main()
