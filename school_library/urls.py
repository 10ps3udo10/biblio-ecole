"""Project URL configuration."""
from django.conf import settings
from django.conf.urls.static import static
from django.contrib import admin
from django.contrib.auth import views as auth_views
from django.urls import include, path

from library.auth_views import StaffLoginView


admin.site.site_header = "Django Admin - Shelf-School"
admin.site.site_title = "Django Admin"
admin.site.index_title = "Technical administration"


urlpatterns = [
    path(
        "staff/login/",
        StaffLoginView.as_view(),
        name="staff_login",
    ),
    path("staff/logout/", auth_views.LogoutView.as_view(), name="staff_logout"),
    path("admin/", admin.site.urls),
    path("", include("library.urls")),
]

if settings.DEBUG:
    urlpatterns += static(settings.MEDIA_URL, document_root=settings.MEDIA_ROOT)
