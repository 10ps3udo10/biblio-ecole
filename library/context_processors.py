from django.conf import settings

from .models import SchoolProfile


def school_profile(request):
    return {
        "school_profile": SchoolProfile.current(),
        "docs_url": settings.SHELF_SCHOOL_DOCS_URL,
    }
