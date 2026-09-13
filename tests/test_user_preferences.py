import pytest
from django.urls import reverse

from library.models import UserPreference

pytestmark = pytest.mark.django_db


def test_account_requires_staff_access(client, django_user_model):
    url = reverse("my_account")
    assert client.get(url).status_code == 302
    client.force_login(django_user_model.objects.create_user(username="reader"))
    assert client.get(url).status_code == 302


def test_theme_is_personal_and_public_kiosk_stays_light(client, django_user_model):
    first = django_user_model.objects.create_user(username="first", is_staff=True)
    second = django_user_model.objects.create_user(username="second", is_staff=True)
    client.force_login(first)
    response = client.get(reverse("my_account"))
    assert response.context["user_theme"] == "system"
    assert "autofocus" not in response.context["password_form"].fields["old_password"].widget.attrs
    assert not UserPreference.objects.exists()
    response = client.post(reverse("my_account"), {"action": "appearance", "theme": "dark", "user": second.pk})
    assert response.status_code == 302
    assert UserPreference.objects.get(user=first).theme == "dark"
    assert not UserPreference.objects.filter(user=second).exists()
    assert b'data-theme="dark"' in client.get(reverse("book_list")).content
    client.force_login(second)
    assert client.get(reverse("my_account")).context["user_theme"] == "system"
    client.logout()
    assert client.get(reverse("photo_circulation")).context["user_theme"] == "light"


def test_invalid_theme_cannot_replace_saved_preference(client, django_user_model):
    user = django_user_model.objects.create_user(username="operator", is_staff=True)
    UserPreference.objects.create(user=user, theme="dark")
    client.force_login(user)
    response = client.post(reverse("my_account"), {"action": "appearance", "theme": "unknown", "is_superuser": True})
    assert response.status_code == 200
    assert response.context["appearance_form"].errors
    assert UserPreference.objects.get(user=user).theme == "dark"
    user.refresh_from_db()
    assert not user.is_superuser


def test_password_change_requires_current_password_and_preserves_session(client, django_user_model):
    user = django_user_model.objects.create_user(username="operator", is_staff=True, password="current-password")
    client.force_login(user)
    data = {"action": "password", "old_password": "wrong", "new_password1": "new-library-secret-938", "new_password2": "new-library-secret-938"}
    response = client.post(reverse("my_account"), data)
    assert response.context["password_form"].errors
    data["old_password"] = "current-password"
    assert client.post(reverse("my_account"), data).status_code == 302
    user.refresh_from_db()
    assert user.check_password(data["new_password1"])
    assert client.get(reverse("my_account")).status_code == 200


def test_account_nav_separates_school_from_personal_settings(client, django_user_model):
    client.force_login(django_user_model.objects.create_user(username="operator", is_staff=True))
    content = client.get(reverse("my_account")).content.decode()
    account_menu = content.split('class="nav-menu account-menu')[1].split("</details>")[0]
    assert "My account" in account_menu
    assert "School settings" not in account_menu
    assert "School settings" in content


@pytest.mark.parametrize("start_page", UserPreference.StartPage.values)
def test_login_uses_personal_start_page_but_respects_safe_next(client, django_user_model, start_page):
    user = django_user_model.objects.create_user(username="operator", password="secret", is_staff=True)
    UserPreference.objects.create(user=user, start_page=start_page)
    for next_url, destination in [("", reverse(start_page)), ("/borrowers/", "/borrowers/"), ("https://example.org/", reverse(start_page))]:
        client.logout()
        response = client.post(reverse("staff_login"), {"username": "operator", "password": "secret", "next": next_url})
        assert response.url == destination


def test_login_defaults_to_overview_and_public_link_does_not_override_it(client, django_user_model):
    content = client.get(reverse("photo_circulation")).content.decode()
    assert f'href="{reverse("staff_login")}"' in content
    user = django_user_model.objects.create_user(username="operator", password="secret", is_staff=True)
    response = client.post(reverse("staff_login"), {"username": "operator", "password": "secret"})
    assert response.url == reverse("dashboard")
    assert not UserPreference.objects.filter(user=user).exists()


def test_workflow_preferences_are_validated_and_personal(client, django_user_model):
    user = django_user_model.objects.create_user(username="operator", is_staff=True)
    other = django_user_model.objects.create_user(username="other", is_staff=True)
    UserPreference.objects.create(user=user, theme="dark")
    client.force_login(user)
    url = reverse("my_account")
    response = client.post(url, {"action": "workflow", "start_page": "book_list", "table_density": "compact", "user": other.pk})
    assert response.status_code == 302
    pref = UserPreference.objects.get(user=user)
    assert (pref.start_page, pref.table_density, pref.theme) == ("book_list", "compact", "dark")
    assert not UserPreference.objects.filter(user=other).exists()
    for data in [{"start_page": "https://example.org/", "table_density": "compact"}, {"start_page": "dashboard", "table_density": "invalid"}]:
        assert client.post(url, {"action": "workflow", **data}).context["workflow_form"].errors
        pref.refresh_from_db()
        assert (pref.start_page, pref.table_density) == ("book_list", "compact")
    client.post(url, {"action": "appearance", "theme": "light"})
    pref.refresh_from_db()
    assert (pref.start_page, pref.table_density) == ("book_list", "compact")
    assert client.get(reverse("book_list")).context["user_table_density"] == "compact"
    client.force_login(other)
    assert client.get(reverse("book_list")).context["user_table_density"] == "comfortable"
    client.logout()
    assert client.get(reverse("public_catalog")).context["user_table_density"] == "comfortable"
