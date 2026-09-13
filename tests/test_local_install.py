import os
from pathlib import Path
import shutil
import sqlite3
import subprocess
import sys
import sysconfig
from types import SimpleNamespace

import pytest

from tools import local_install


def test_secret_is_private_and_stable(tmp_path, monkeypatch):
    monkeypatch.delenv("DJANGO_SECRET_KEY", raising=False)
    first = local_install.environment(tmp_path)
    second = local_install.environment(tmp_path)
    secret = tmp_path / local_install.SECRET_FILE
    assert first["DJANGO_SECRET_KEY"] == second["DJANGO_SECRET_KEY"]
    assert len(first["DJANGO_SECRET_KEY"]) >= 50
    assert secret.stat().st_mode & 0o777 == 0o600
    assert "DJANGO_SECRET_KEY" not in os.environ


def test_existing_secret_is_never_replaced_by_environment(tmp_path, monkeypatch):
    (tmp_path / local_install.SECRET_FILE).write_text("existing-secret")
    monkeypatch.setenv("DJANGO_SECRET_KEY", "different")
    assert local_install.environment(tmp_path)["DJANGO_SECRET_KEY"] == "existing-secret"


def test_empty_secret_is_rejected(tmp_path):
    (tmp_path / local_install.SECRET_FILE).touch()
    with pytest.raises(ValueError, match="secret is empty"):
        local_install.environment(tmp_path)


def test_old_python_fails_before_creating_any_files(tmp_path, monkeypatch):
    monkeypatch.setattr(sys, "version_info", (3, 8, 0))
    with pytest.raises(ValueError, match="PYTHON=python3.12"):
        local_install.setup(tmp_path)
    assert list(tmp_path.iterdir()) == []


def test_root_setup_is_rejected(tmp_path, monkeypatch):
    monkeypatch.setattr(os, "geteuid", lambda: 0)
    with pytest.raises(ValueError, match="without sudo"):
        local_install.setup(tmp_path)


def test_invalid_existing_venv_is_not_deleted(tmp_path, monkeypatch):
    monkeypatch.setattr(os, "geteuid", lambda: 501)
    python = tmp_path / ".venv/bin/python"
    python.parent.mkdir(parents=True)
    python.write_text("not a usable interpreter")
    monkeypatch.setattr(local_install, "run", lambda *a, **k: (_ for _ in ()).throw(OSError("not executable")))
    with pytest.raises(ValueError, match="existing .venv is incompatible"):
        local_install.setup(tmp_path)
    assert python.read_text() == "not a usable interpreter"


def test_setup_preserves_existing_library_and_does_not_recreate_admin(tmp_path, monkeypatch):
    project = tmp_path / "school library"
    project.mkdir()
    root = Path(__file__).resolve().parents[1]
    for directory in ("school_library", "library"):
        shutil.copytree(root / directory, project / directory, ignore=shutil.ignore_patterns("__pycache__"))
    shutil.copyfile(root / "manage.py", project / "manage.py")
    shutil.copyfile(root / "VERSION", project / "VERSION")
    (project / ".venv/bin").mkdir(parents=True)
    (project / ".venv/bin/python").symlink_to(sys.executable)
    monkeypatch.setenv("PYTHONPATH", sysconfig.get_path("purelib"))
    monkeypatch.setattr(os, "geteuid", lambda: 501)
    monkeypatch.setattr(sys, "stdin", SimpleNamespace(isatty=lambda: False))
    actual_run = local_install.run
    calls = []

    def run_without_install(project, *args, **kwargs):
        calls.append(tuple(str(arg) for arg in args))
        if "pip" not in args:
            return actual_run(project, *args, **kwargs)

    monkeypatch.setattr(local_install, "run", run_without_install)
    with pytest.raises(ValueError, match="make admin"):
        local_install.setup(project)
    python = project / ".venv/bin/python"
    actual_run(project, python, "manage.py", "shell", "-c",
        "from django.contrib.auth import get_user_model; from library.models import Book; get_user_model().objects.create_superuser(username='owner', password='private', email=''); Book.objects.create(title='Preserve me')")
    before = (project / local_install.SECRET_FILE).read_text()
    local_install.setup(project)
    assert (project / local_install.SECRET_FILE).read_text() == before
    with sqlite3.connect(project / "db.sqlite3") as connection:
        assert connection.execute("SELECT title FROM library_book").fetchall() == [("Preserve me",)]
        assert connection.execute("SELECT username FROM auth_user").fetchall() == [("owner",)]
    assert not any("createsuperuser" in call for call in calls)
    assert not any("playwright" in call for call in calls)


def test_start_uses_requested_network_and_checks_migrations(tmp_path, monkeypatch):
    python = tmp_path / ".venv/bin/python"
    python.parent.mkdir(parents=True)
    python.touch()
    monkeypatch.setattr(local_install, "PROJECT", tmp_path)
    monkeypatch.setattr(sys, "argv", ["local_install.py", "start", "--bind", "0.0.0.0", "--hosts", "localhost,Library-Mac.local", "--port", "8428"])
    calls = []
    monkeypatch.setattr(local_install, "run", lambda *args, **kwargs: calls.append((args, kwargs)))
    local_install.main()
    assert calls[0][0][-2:] == ("migrate", "--check")
    assert calls[1][0][-3:] == ("runserver", "0.0.0.0:8428", "--noreload")
    assert calls[1][1]["env"]["DJANGO_ALLOWED_HOSTS"] == "localhost,Library-Mac.local"


def test_make_targets_do_not_activate_a_shell_or_install_browsers():
    root = Path(__file__).resolve().parents[1]
    commands = subprocess.run(["make", "-n", "setup", "PYTHON=python3.12"], cwd=root, check=True, capture_output=True, text=True).stdout
    assert '"python3.12" tools/local_install.py setup' in commands
    assert "activate" not in commands and "playwright" not in commands
