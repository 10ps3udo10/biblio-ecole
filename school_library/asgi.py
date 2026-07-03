"""ASGI config for the school library project."""
import os

from django.core.asgi import get_asgi_application


os.environ.setdefault("DJANGO_SETTINGS_MODULE", "school_library.settings")

application = get_asgi_application()
