import io
import json
import plistlib
import sqlite3
from types import SimpleNamespace

import pytest

from tools.library_backup import create_backup, restore_backup
from tools import macos_service


@pytest.fixture
def library_files(tmp_path):
    database = tmp_path / "db.sqlite3"
    connection = sqlite3.connect(database)
    connection.execute("CREATE TABLE books (title TEXT)")
    connection.execute("INSERT INTO books VALUES ('School book')")
    connection.commit()
    connection.close()
    media = tmp_path / "media"
    (media / "covers").mkdir(parents=True)
    (media / "covers/book.jpg").write_bytes(b"sample cover")
    destination = tmp_path / "backups"
    destination.mkdir()
    return database, media, destination


def test_complete_backup_restores_database_and_media(library_files, tmp_path):
    database, media, destination = library_files
    archive = create_backup(database, media, destination)
    restored = restore_backup(archive, tmp_path / "restored")
    connection = sqlite3.connect(restored / "db.sqlite3")
    try:
        assert connection.execute("SELECT title FROM books").fetchall() == [("School book",)]
    finally:
        connection.close()
    assert (restored / "media/covers/book.jpg").read_bytes() == b"sample cover"
    assert archive.stat().st_mode & 0o777 == 0o600
    assert list(destination.iterdir()) == [archive]


def test_restore_never_overwrites_existing_directory(library_files):
    database, media, destination = library_files
    archive = create_backup(database, media, destination)
    with pytest.raises(ValueError, match="new folder"):
        restore_backup(archive, media)
    assert (media / "covers/book.jpg").read_bytes() == b"sample cover"


def test_backup_rejects_missing_drive_and_recursive_destination(library_files, tmp_path):
    database, media, _ = library_files
    with pytest.raises(ValueError, match="mounted"):
        create_backup(database, media, tmp_path / "unmounted")
    with pytest.raises(ValueError, match="inside media"):
        create_backup(database, media, media)


def test_empty_library_without_media_restores(library_files, tmp_path):
    database, _, destination = library_files
    archive = create_backup(database, tmp_path / "no-media", destination)
    restored = restore_backup(archive, tmp_path / "restored")
    assert (restored / "media").is_dir()


def test_failed_backup_does_not_publish_archive(library_files, monkeypatch):
    from tools import library_backup
    database, media, destination = library_files

    def fail_verification(*args):
        raise ValueError("Verification failed")

    monkeypatch.setattr(library_backup, "restore_backup", fail_verification)
    with pytest.raises(ValueError, match="Verification failed"):
        create_backup(database, media, destination)
    assert not list(destination.iterdir())


@pytest.mark.parametrize("attack", ["../outside", "/outside", "media/link", "checksum"])
def test_restore_rejects_unsafe_or_corrupt_archive(tmp_path, attack):
    import tarfile
    archive = tmp_path / "bad.tar.gz"
    with tarfile.open(archive, "w:gz") as output:
        if attack == "checksum":
            entries = {"db.sqlite3": b"bad", "manifest.json": json.dumps({
                "format": 1, "sha256": {"db.sqlite3": "wrong"},
            }).encode()}
            for name, data in entries.items():
                member = tarfile.TarInfo(name)
                member.size = len(data)
                output.addfile(member, io.BytesIO(data))
        else:
            member = tarfile.TarInfo(attack)
            if attack == "media/link":
                member.type = tarfile.SYMTYPE
                member.linkname = "/outside"
            output.addfile(member)
    with pytest.raises(ValueError):
        restore_backup(archive, tmp_path / "restore")
    assert not (tmp_path / "restore").exists()
    assert not (tmp_path / "outside").exists()


def test_service_plist_runs_app_as_library(monkeypatch, tmp_path):
    monkeypatch.setattr(macos_service.pwd, "getpwnam", lambda user: SimpleNamespace(pw_dir=str(tmp_path)))
    server = macos_service.service_plist(tmp_path, "library", "localhost", 8427, "secret")
    assert plistlib.loads(plistlib.dumps(server)) == server
    assert server["UserName"] == "library"
    assert server["EnvironmentVariables"]["DJANGO_SECRET_KEY"] == "secret"
    assert "StartCalendarInterval" not in server


def test_installer_preserves_existing_secret(monkeypatch, tmp_path):
    project = tmp_path / "project"
    (project / ".venv/bin").mkdir(parents=True)
    (project / ".venv/bin/python").touch()
    (project / "db.sqlite3").touch()
    daemons = tmp_path / "daemons"
    daemons.mkdir()
    old = {"EnvironmentVariables": {"DJANGO_SECRET_KEY": "keep-this-secret"}}
    (daemons / f"{macos_service.SERVER}.plist").write_bytes(plistlib.dumps(old))
    monkeypatch.setattr(macos_service, "DAEMONS", daemons)
    monkeypatch.setattr(macos_service.pwd, "getpwnam", lambda user: SimpleNamespace(pw_dir=str(tmp_path), pw_uid=501))
    monkeypatch.setattr(macos_service, "run", lambda *args, **kwargs: None)
    monkeypatch.setattr(macos_service, "loaded", lambda label: False)
    monkeypatch.setattr(macos_service, "write_private", lambda path, data: path.write_bytes(data))
    macos_service.install(SimpleNamespace(
        project=project, user="library", hosts="localhost",
        port=8427, bind="127.0.0.1",
    ))
    installed = plistlib.loads((daemons / f"{macos_service.SERVER}.plist").read_bytes())
    assert installed["EnvironmentVariables"]["DJANGO_SECRET_KEY"] == "keep-this-secret"


@pytest.mark.parametrize("bind", ["127.0.0.1", "0.0.0.0"])
def test_service_binding_is_explicit(monkeypatch, tmp_path, bind):
    monkeypatch.setattr(macos_service.pwd, "getpwnam", lambda user: SimpleNamespace(pw_dir=str(tmp_path)))
    server = macos_service.service_plist(tmp_path, "library", "localhost", 8428, "secret", bind)
    assert f"{bind}:8428" in server["ProgramArguments"]
