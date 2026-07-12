import os

import pytest


os.environ.setdefault("DJANGO_ALLOW_ASYNC_UNSAFE", "true")


@pytest.fixture(autouse=True)
def disable_external_cover_download(monkeypatch):
    monkeypatch.setattr("library.views.download_cover_by_isbn", lambda isbn: None)
