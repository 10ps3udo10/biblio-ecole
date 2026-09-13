from django.conf import settings

from .models import SchoolProfile, UserPreference


def school_profile(request):
    theme = "light"
    density = "comfortable"
    if request.user.is_authenticated:
        preference = UserPreference.objects.filter(user=request.user).values("theme", "table_density").first() or {}
        theme = preference.get("theme", "system")
        density = preference.get("table_density", "comfortable")
        if theme not in UserPreference.Theme.values:
            theme = "system"
        if density not in UserPreference.TableDensity.values:
            density = "comfortable"
    return {
        "school_profile": SchoolProfile.current(),
        "docs_url": settings.SHELF_SCHOOL_DOCS_URL,
        "user_theme": theme,
        "user_table_density": density,
    }
