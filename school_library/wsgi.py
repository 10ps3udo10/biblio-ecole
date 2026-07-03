"""WSGI config for the school library project."""
import os

from django.core.wsgi import get_wsgi_application


os.environ.setdefault("DJANGO_SETTINGS_MODULE", "school_library.settings")

application = get_wsgi_application()
