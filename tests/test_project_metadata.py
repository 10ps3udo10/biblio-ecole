import json
import re
from pathlib import Path

import library


ROOT = Path(__file__).resolve().parent.parent


def test_project_version_markers_are_consistent():
    version = (ROOT / "VERSION").read_text(encoding="ascii").strip()
    readme = (ROOT / "README.md").read_text(encoding="utf-8")
    docs_package = json.loads((ROOT / "docs-site" / "package.json").read_text(encoding="utf-8"))
    docs_lock = json.loads((ROOT / "docs-site" / "package-lock.json").read_text(encoding="utf-8"))

    assert re.fullmatch(r"\d+\.\d+\.\d+(?:-[0-9A-Za-z.-]+)?", version)
    assert library.__version__ == version
    assert docs_package["version"] == version
    assert docs_lock["version"] == version
    assert docs_lock["packages"][""]["version"] == version
    assert f"version-{version.replace('-', '--')}-" in readme
