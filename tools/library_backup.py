"""Portable database-and-media archives; no Django installation is required."""
import argparse
from contextlib import closing
from datetime import datetime, timezone
import hashlib
import json
from pathlib import Path
import shutil
import sqlite3
import tarfile
import tempfile
import uuid


def digest(path):
    with path.open("rb") as stream:
        result = hashlib.sha256()
        for chunk in iter(lambda: stream.read(1024 * 1024), b""):
            result.update(chunk)
        return result.hexdigest()


def check_database(path):
    with closing(sqlite3.connect(path.as_uri() + "?mode=ro", uri=True)) as database:
        if database.execute("PRAGMA integrity_check").fetchall() != [("ok",)]:
            raise ValueError("Database integrity check failed.")


def create_backup(database, media, destination):
    database, media, destination = (Path(p).resolve() for p in (database, media, destination))
    if not database.is_file():
        raise ValueError("Database does not exist.")
    if not destination.is_dir():
        raise ValueError("Backup destination must already exist and be mounted.")
    if destination == media or media in destination.parents:
        raise ValueError("Backup destination cannot be inside media.")
    name = "shelf-school-" + datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%SZ")
    archive = destination / f"{name}-{uuid.uuid4().hex[:8]}.tar.gz"
    with tempfile.TemporaryDirectory(dir=destination, prefix=".shelf-school-") as temporary:
        root = Path(temporary)
        snapshot = root / "db.sqlite3"
        with closing(sqlite3.connect(database.as_uri() + "?mode=ro", uri=True)) as source:
            with closing(sqlite3.connect(snapshot)) as target:
                source.backup(target)
        check_database(snapshot)
        files = {"db.sqlite3": snapshot}
        if media.exists():
            for path in sorted(media.rglob("*")):
                if path.is_symlink():
                    raise ValueError("Media contains a symbolic link; use regular files for backups.")
                if path.is_file():
                    files["media/" + path.relative_to(media).as_posix()] = path
        manifest = root / "manifest.json"
        manifest.write_text(json.dumps({
            "format": 1,
            "created_at": datetime.now(timezone.utc).isoformat(),
            "sha256": {name: digest(path) for name, path in files.items()},
        }, indent=2), encoding="utf-8")
        partial = root / "archive.tar.gz"
        with tarfile.open(partial, "w:gz") as output:
            output.add(manifest, arcname="manifest.json")
            for name, path in files.items():
                output.add(path, arcname=name)
        # Validate the actual archive before publishing it as a completed backup.
        restore_backup(partial, root / "verification")
        partial.chmod(0o600)
        partial.rename(archive)
    return archive


def restore_backup(archive, destination):
    destination = Path(destination).resolve()
    if destination.exists():
        raise ValueError("Restore destination must be a new folder; existing data is never overwritten.")
    if not destination.parent.is_dir():
        raise ValueError("Restore parent directory does not exist.")
    with tempfile.TemporaryDirectory(dir=destination.parent, prefix=".shelf-school-restore-") as temporary:
        root = Path(temporary) / "data"
        root.mkdir(mode=0o700)
        with tarfile.open(archive, "r:gz") as source:
            seen = set()
            for member in source:
                path = Path(member.name)
                if (not member.isfile() or path.is_absolute() or ".." in path.parts
                        or member.name in seen or path.as_posix() != member.name
                        or not (member.name in {"db.sqlite3", "manifest.json"}
                                or member.name.startswith("media/"))):
                    raise ValueError("Archive contains an unsupported or unsafe entry.")
                seen.add(member.name)
                target = root / path
                target.parent.mkdir(parents=True, exist_ok=True)
                with source.extractfile(member) as incoming, target.open("xb") as output:
                    shutil.copyfileobj(incoming, output)
                target.chmod(0o600)
        manifest = json.loads((root / "manifest.json").read_text(encoding="utf-8"))
        if not isinstance(manifest, dict) or not isinstance(manifest.get("sha256"), dict):
            raise ValueError("Archive manifest is invalid.")
        hashes = manifest.get("sha256", {})
        if manifest.get("format") != 1 or set(hashes) != seen - {"manifest.json"} or "db.sqlite3" not in hashes:
            raise ValueError("Archive manifest is invalid.")
        for name, expected in hashes.items():
            if digest(root / name) != expected:
                raise ValueError(f"Archive checksum failed: {name}")
        check_database(root / "db.sqlite3")
        (root / "media").mkdir(exist_ok=True)
        root.rename(destination)
    return destination


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    commands = parser.add_subparsers(dest="command", required=True)
    backup = commands.add_parser("create", help="Stop Shelf-School before creating a complete archive.")
    backup.add_argument("--database", type=Path, default=Path("db.sqlite3"))
    backup.add_argument("--media", type=Path, default=Path("media"))
    backup.add_argument("--destination", type=Path, required=True)
    restore = commands.add_parser("restore", help="Verify and extract into a new folder.")
    restore.add_argument("archive", type=Path)
    restore.add_argument("--destination", type=Path, required=True)
    args = parser.parse_args()
    try:
        if args.command == "create":
            result = create_backup(args.database, args.media, args.destination)
        else:
            result = restore_backup(args.archive, args.destination)
    except (OSError, ValueError, sqlite3.Error, tarfile.TarError) as exc:
        parser.exit(1, f"Backup error: {exc}\n")
    print(result)


if __name__ == "__main__":
    main()
