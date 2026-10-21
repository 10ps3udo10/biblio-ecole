from django.contrib.auth.views import LoginView
from django.urls import reverse

from .forms import StaffAuthenticationForm
from .models import UserPreference


class StaffLoginView(LoginView):
    template_name = "registration/login.html"
    authentication_form = StaffAuthenticationForm

    def get_default_redirect_url(self):
        start_page = UserPreference.objects.filter(user=self.request.user).values_list("start_page", flat=True).first()
        if start_page not in UserPreference.StartPage.values:
            start_page = UserPreference.StartPage.DESK
        return reverse(start_page)
