from datetime import timedelta
import uuid

from django import forms
from django.contrib.auth import get_user_model
from django.contrib.auth.forms import AuthenticationForm, UserCreationForm
from django.core.exceptions import ValidationError
from django.db import models
from django.db.models import Q
from django.utils import timezone

from .models import Book, Borrower, Copy, SchoolProfile, EmployeePosition, SchoolClass, SchoolYear, UserPreference
from .photo_intake import clean_isbn, is_valid_isbn


class UserPreferenceForm(forms.ModelForm):
    class Meta:
        model = UserPreference
        fields = ["theme"]
        widgets = {"theme": forms.RadioSelect}


class UserWorkflowForm(forms.ModelForm):
    class Meta:
        model = UserPreference
        fields = ["start_page", "table_density"]
        labels = {"start_page": "Page d'accueil après la connexion", "table_density": "Espacement des tableaux"}
        widgets = {"table_density": forms.RadioSelect}


class StaffAuthenticationForm(AuthenticationForm):
    def confirm_login_allowed(self, user):
        super().confirm_login_allowed(user)
        if not user.is_staff:
            raise ValidationError("Ce compte n'a pas accès à Shelf-School.", code="not_staff")


class ExistingBorrowerChoiceField(forms.ModelChoiceField):
    def label_from_instance(self, borrower):
        school_id = f" · Identifiant école {borrower.school_id}" if borrower.school_id else ""
        return f"{borrower.full_name} · {borrower.borrower_id}{school_id}"


class StaffAccountCreationForm(UserCreationForm):
    first_name = forms.CharField(label="Prénom", max_length=150)
    last_name = forms.CharField(label="Nom", max_length=150)
    borrower = ExistingBorrowerChoiceField(
        label="Élève ou personnel existant",
        queryset=Borrower.objects.none(),
        required=False,
        empty_label="Créer une nouvelle fiche",
        help_text="Choisissez la personne si elle figure déjà dans la liste des élèves.",
    )

    class Meta(UserCreationForm.Meta):
        model = get_user_model()
        fields = ("username", "first_name", "last_name", "email")
        labels = {"username": "Identifiant de connexion"}

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self.fields["borrower"].queryset = Borrower.objects.filter(staff_account__isnull=True).order_by("last_name", "first_name")

    def save(self, commit=True):
        account = super().save(commit=False)
        account.is_staff = True
        if commit:
            account.save()
        return account


class StaffAccountEditForm(forms.ModelForm):
    first_name = forms.CharField(label="Prénom", max_length=150)
    last_name = forms.CharField(label="Nom", max_length=150)

    class Meta:
        model = get_user_model()
        fields = ("username", "first_name", "last_name", "email", "is_active")
        labels = {"username": "Identifiant de connexion"}

    def __init__(self, *args, operator=None, **kwargs):
        super().__init__(*args, **kwargs)
        self.operator = operator

    def clean_is_active(self):
        is_active = self.cleaned_data["is_active"]
        if not is_active and self.instance == self.operator:
            raise ValidationError("Vous ne pouvez pas désactiver votre propre compte.")
        if not is_active and self.instance.is_superuser:
            raise ValidationError("Les comptes administrateur système ne peuvent pas être désactivés ici.")
        return is_active

def default_form_due_date():
    try:
        days = SchoolProfile.current().default_loan_days
    except Exception:
        days = 14
    return timezone.localdate() + timedelta(days=days)


class BookValidationMixin:
    def clean(self):
        cleaned_data = super().clean()
        for field_name, length in (("isbn13", 13), ("isbn10", 10)):
            isbn = clean_isbn(cleaned_data.get(field_name))
            cleaned_data[field_name] = isbn
            if isbn and (len(isbn) != length or not is_valid_isbn(isbn)):
                self.add_error(field_name, f"Saisissez un ISBN-{length} valide.")

        isbn13 = cleaned_data.get("isbn13")
        isbn10 = cleaned_data.get("isbn10")
        isbn_query = Q()
        if isbn13:
            isbn_query |= Q(isbn13=isbn13)
        if isbn10:
            isbn_query |= Q(isbn10=isbn10)
        if isbn_query:
            matches = Book.objects.filter(isbn_query)
            if self.instance.pk:
                matches = matches.exclude(pk=self.instance.pk)
            if matches.exists():
                raise forms.ValidationError("Cet ISBN appartient à un autre livre du catalogue.")
        return cleaned_data


class BookForm(BookValidationMixin, forms.ModelForm):
    isbn13 = forms.CharField(label="ISBN-13", max_length=20, required=False)
    isbn10 = forms.CharField(label="ISBN-10", max_length=20, required=False)
    bibliographic_source_url = forms.URLField(label="Adresse de la source bibliographique", required=False, assume_scheme="https")
    first_copy_shelf = forms.CharField(label="Emplacement", max_length=128, required=False)
    first_copy_condition = forms.ChoiceField(label="État", choices=Copy.Condition.choices, required=False)

    class Meta:
        model = Book
        fields = [
            "isbn13",
            "isbn10",
            "title",
            "subtitle",
            "authors",
            "publisher",
            "publication_year",
            "language",
            "page_count",
            "format",
            "category",
            "topics",
            "description",
            "montessori_levels",
            "suggested_age_range",
            "suggested_reading_level",
            "identification_confidence",
            "review_notes",
            "bibliographic_source_url",
            "needs_information",
            "cover_image",
        ]
        labels = {"authors": "Auteur(s)"}


class BookEditForm(BookValidationMixin, forms.ModelForm):
    isbn13 = forms.CharField(label="ISBN-13", max_length=20, required=False)
    isbn10 = forms.CharField(label="ISBN-10", max_length=20, required=False)
    bibliographic_source_url = forms.URLField(label="Adresse de la source bibliographique", required=False, assume_scheme="https")

    class Meta:
        model = Book
        fields = [
            "isbn13",
            "isbn10",
            "title",
            "subtitle",
            "authors",
            "publisher",
            "publication_year",
            "language",
            "page_count",
            "format",
            "category",
            "topics",
            "description",
            "montessori_levels",
            "suggested_age_range",
            "suggested_reading_level",
            "identification_confidence",
            "review_notes",
            "bibliographic_source_url",
            "needs_information",
            "cover_image",
        ]
        labels = {"authors": "Auteur(s)"}


class CopyForm(forms.ModelForm):
    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self.fields["status"].choices = [
            choice for choice in Copy.Status.choices if choice[0] != Copy.Status.CHECKED_OUT
        ]

    class Meta:
        model = Copy
        fields = ["shelf_location", "condition", "status"]


class CopyEditForm(CopyForm):
    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        if self.instance.pk and self.instance.active_loan:
            self.fields.pop("status")


class EmployeePositionForm(forms.ModelForm):
    class Meta:
        model = EmployeePosition
        fields = ["name", "active"]

    def clean_name(self):
        name = self.cleaned_data["name"].strip()
        if EmployeePosition.objects.filter(name__iexact=name).exclude(pk=self.instance.pk).exists():
            raise forms.ValidationError("Une fonction portant ce nom existe déjà.")
        return name


class SchoolClassForm(forms.ModelForm):
    class Meta:
        model = SchoolClass
        fields = ["name", "active"]

    def clean_name(self):
        name = self.cleaned_data["name"].strip()
        school_year = self.instance.school_year if self.instance.school_year_id else SchoolYear.current()
        if SchoolClass.objects.filter(school_year=school_year, name__iexact=name).exclude(pk=self.instance.pk).exists():
            raise forms.ValidationError("Une classe portant ce nom existe déjà.")
        return name


class BorrowerForm(forms.ModelForm):
    class Meta:
        model = Borrower
        fields = ["school_id", "first_name", "last_name", "school_role", "position", "school_class", "email", "active"]

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self.fields["position"].queryset = EmployeePosition.objects.filter(Q(active=True) | Q(pk=self.instance.position_id))
        self.fields["position"].empty_label = "Aucune fonction"
        self.fields["school_class"].queryset = SchoolClass.objects.filter(Q(active=True) | Q(pk=self.instance.school_class_id))
        self.fields["school_class"].empty_label = "Aucune classe"
        if self.instance.pk and self.instance.staff_account_id:
            for field_name in ("first_name", "last_name", "email"):
                self.fields[field_name].disabled = True
                self.fields[field_name].required = False
                self.fields[field_name].help_text = "Géré depuis le compte du personnel associé."

    def clean_school_id(self):
        school_id = self.cleaned_data.get("school_id") or None
        if school_id and Borrower.objects.filter(school_id__iexact=school_id).exclude(pk=self.instance.pk).exists():
            raise ValidationError("Cet identifiant école est déjà attribué à un autre emprunteur.")
        return school_id

    def clean(self):
        data = super().clean()
        if data.get("school_role") == Borrower.SchoolRole.STUDENT:
            if data.get("position"):
                self.add_error("position", "Une fonction ne peut être attribuée qu'au personnel.")
        elif data.get("school_role") == Borrower.SchoolRole.EMPLOYEE:
            data["school_class"] = None
        return data


class BorrowerChoiceField(forms.ModelChoiceField):
    def label_from_instance(self, borrower):
        identifier = borrower.borrower_id
        class_name = f" - {borrower.school_class}" if borrower.school_class else ""
        return f"{identifier} - {borrower.full_name}{class_name}"


class LoanBorrowerCorrectionForm(forms.Form):
    borrower = BorrowerChoiceField(label="Emprunteur corrigé", queryset=Borrower.objects.none())

    def __init__(self, *args, loan=None, **kwargs):
        super().__init__(*args, **kwargs)
        self.loan = loan
        self.fields["borrower"].queryset = Borrower.objects.filter(active=True).select_related("school_class").order_by("last_name", "first_name")

    def clean_borrower(self):
        borrower = self.cleaned_data["borrower"]
        if self.loan and borrower.pk == self.loan.borrower_id:
            raise forms.ValidationError("Choisissez un autre emprunteur.")
        return borrower


class SchoolProfileForm(forms.ModelForm):
    class Meta:
        model = SchoolProfile
        fields = [
            "school_name",
            "short_name",
            "logo",
            "address",
            "contact_email",
            "contact_phone",
            "default_loan_days",
            "label_footer",
        ]
        widgets = {"address": forms.Textarea(attrs={"rows": 3})}

    def clean_default_loan_days(self):
        days = self.cleaned_data["default_loan_days"]
        if days < 1 or days > 365:
            raise forms.ValidationError("Saisissez une durée de prêt comprise entre 1 et 365 jours.")
        return days


class CheckoutForm(forms.Form):
    borrower_code = forms.CharField(label="QR code ou identifiant de l'emprunteur")
    copy_code = forms.CharField(label="QR code ou identifiant de l'exemplaire")
    # Due date is computed from the school's loan period; never typed by hand.
    due_date = forms.DateField(required=False, widget=forms.HiddenInput)


class ReturnForm(forms.Form):
    copy_code = forms.CharField(label="QR code ou identifiant de l'exemplaire")


class PhotoIntakeForm(forms.Form):
    photos = forms.FileField(
        label="Photo du livre",
        widget=forms.ClearableFileInput(attrs={"accept": "image/*", "capture": "environment"}),
        help_text="Si possible, photographiez le code-barres ISBN de près. Une photo de la couverture seule ne peut pas être lue.",
    )
    isbn = forms.CharField(label="ISBN", max_length=20, required=False)
    title = forms.CharField(label="Titre", max_length=255, required=False)
    authors = forms.CharField(label="Author(s)", required=False, widget=forms.Textarea(attrs={"rows": 2}))
    shelf_location = forms.CharField(label="Emplacement", max_length=128, required=False)
    condition = forms.ChoiceField(label="État", choices=Copy.Condition.choices, initial=Copy.Condition.GOOD)

    def clean_isbn(self):
        isbn = clean_isbn(self.cleaned_data.get("isbn"))
        if isbn and not is_valid_isbn(isbn):
            raise forms.ValidationError("Saisissez un ISBN-10 ou ISBN-13 valide.")
        return isbn


class CopyChoiceField(forms.ModelChoiceField):
    def label_from_instance(self, copy):
        details = [copy.book.title]
        if copy.book.authors:
            details.append(copy.book.authors)
        details.append(f"Exemplaire n°{copy.copy_number}")
        isbn = copy.book.isbn13 or copy.book.isbn10
        if isbn:
            details.append(f"ISBN {isbn}")
        if copy.shelf_location:
            details.append(f"Étagère {copy.shelf_location}")
        return " - ".join(details)


class CopyMultipleChoiceField(forms.ModelMultipleChoiceField):
    def label_from_instance(self, copy):
        return f"{copy.book.title} - exemplaire n°{copy.copy_number}"


class PhotoCirculationForm(forms.Form):
    class Action(models.TextChoices):
        CHECKOUT = "checkout", "Prêter"
        CHECKIN = "checkin", "Rendre"

    action = forms.ChoiceField(
        label="Action",
        choices=Action.choices,
        initial=Action.CHECKOUT,
        widget=forms.RadioSelect,
    )
    borrower = forms.UUIDField(label="Emprunteur", widget=forms.HiddenInput)
    basket_token = forms.CharField(required=False, widget=forms.HiddenInput)
    book_photo = forms.FileField(
        label="Photo du QR code ou du code-barres ISBN du livre",
        required=False,
        widget=forms.ClearableFileInput(attrs={"accept": "image/*", "capture": "environment"}),
        help_text="Utilisez de préférence le QR code de l'étiquette. Le code-barres ISBN ne fonctionne que s'il n'existe qu'un seul exemplaire.",
    )
    manual_copy = CopyChoiceField(label="Exemplaire", queryset=Copy.objects.none(), required=False)
    return_copies = CopyMultipleChoiceField(label="Livres à rendre", queryset=Copy.objects.none(), required=False)
    due_date = forms.DateField(
        label="Date de retour prévue",
        required=False,
        initial=default_form_due_date,
        widget=forms.DateInput(attrs={"type": "date"}),
    )

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self.fields["manual_copy"].queryset = Copy.objects.filter(status=Copy.Status.AVAILABLE).select_related("book").order_by("book__title", "copy_number")
        self.fields["manual_copy"].empty_label = "Choisissez un exemplaire précis"
        return_copies = Copy.objects.filter(status=Copy.Status.CHECKED_OUT, loans__return_date__isnull=True)
        borrower_id = self.data.get("borrower") if self.is_bound else self.initial.get("borrower")
        try:
            borrower_id = uuid.UUID(str(borrower_id)) if borrower_id else None
        except (TypeError, ValueError):
            borrower_id = None
        if borrower_id is not None:
            return_copies = return_copies.filter(loans__borrower_id=borrower_id)
        else:
            return_copies = return_copies.none()
        self.fields["return_copies"].queryset = return_copies.select_related("book").distinct().order_by("book__title", "copy_number")

    def clean(self):
        cleaned_data = super().clean()
        action = cleaned_data.get("action")
        borrower_id = cleaned_data.get("borrower")
        borrower = None
        if borrower_id:
            borrowers = Borrower.objects.all()
            if action == self.Action.CHECKOUT:
                borrowers = borrowers.filter(active=True)
            elif action == self.Action.CHECKIN:
                borrowers = borrowers.filter(loans__return_date__isnull=True).distinct()
            borrower = borrowers.filter(pk=borrower_id).first()
            if borrower is None:
                self.add_error("borrower", "Choisissez un élève dans les résultats de recherche.")
            else:
                cleaned_data["borrower"] = borrower
        if action == self.Action.CHECKIN and not cleaned_data.get("return_copies"):
            raise forms.ValidationError("Sélectionnez au moins un livre emprunté à rendre.")
        if action == self.Action.CHECKOUT and not cleaned_data.get("book_photo") and not cleaned_data.get("manual_copy"):
            raise forms.ValidationError("Prenez une photo du livre ou choisissez-le manuellement.")
        return cleaned_data


class CsvImportForm(forms.Form):
    csv_file = forms.FileField(label="Fichier CSV")


class FetchCoversForm(forms.Form):
    books = forms.ModelMultipleChoiceField(queryset=Book.objects.all())


class BorrowerCsvImportForm(forms.Form):
    csv_file = forms.FileField(label="Fichier CSV des élèves")
