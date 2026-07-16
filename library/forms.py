from datetime import timedelta
import uuid

from django import forms
from django.contrib.auth import get_user_model
from django.contrib.auth.forms import AuthenticationForm, UserCreationForm
from django.core.exceptions import ValidationError
from django.db import models
from django.db.models import Q
from django.utils import timezone

from .models import Book, Borrower, Copy, SchoolProfile
from .photo_intake import clean_isbn, is_valid_isbn


class StaffAuthenticationForm(AuthenticationForm):
    def confirm_login_allowed(self, user):
        super().confirm_login_allowed(user)
        if not user.is_staff:
            raise ValidationError("This account does not have Shelf-School staff access.", code="not_staff")


class StaffAccountCreationForm(UserCreationForm):
    class Meta(UserCreationForm.Meta):
        model = get_user_model()
        fields = ("username", "first_name", "last_name", "email")

    def save(self, commit=True):
        account = super().save(commit=False)
        account.is_staff = True
        if commit:
            account.save()
        return account


class StaffAccountEditForm(forms.ModelForm):
    class Meta:
        model = get_user_model()
        fields = ("username", "first_name", "last_name", "email", "is_active")

    def __init__(self, *args, operator=None, **kwargs):
        super().__init__(*args, **kwargs)
        self.operator = operator

    def clean_is_active(self):
        is_active = self.cleaned_data["is_active"]
        if not is_active and self.instance == self.operator:
            raise ValidationError("You cannot deactivate your own account.")
        if not is_active and self.instance.is_superuser:
            raise ValidationError("System administrator accounts cannot be deactivated here.")
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
                self.add_error(field_name, f"Enter a valid ISBN-{length}.")

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
                raise forms.ValidationError("This ISBN belongs to another cataloged book.")
        return cleaned_data


class BookForm(BookValidationMixin, forms.ModelForm):
    isbn13 = forms.CharField(label="ISBN-13", max_length=20, required=False)
    isbn10 = forms.CharField(label="ISBN-10", max_length=20, required=False)
    bibliographic_source_url = forms.URLField(label="Bibliographic source URL", required=False, assume_scheme="https")
    first_copy_shelf = forms.CharField(label="Shelf location", max_length=128, required=False)
    first_copy_condition = forms.ChoiceField(label="Condition", choices=Copy.Condition.choices, required=False)

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
        labels = {"authors": "Contributors"}


class BookEditForm(BookValidationMixin, forms.ModelForm):
    isbn13 = forms.CharField(label="ISBN-13", max_length=20, required=False)
    isbn10 = forms.CharField(label="ISBN-10", max_length=20, required=False)
    bibliographic_source_url = forms.URLField(label="Bibliographic source URL", required=False, assume_scheme="https")

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
        labels = {"authors": "Contributors"}


class CopyForm(forms.ModelForm):
    class Meta:
        model = Copy
        fields = ["shelf_location", "condition", "status"]


class CopyEditForm(CopyForm):
    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        if self.instance.pk and self.instance.active_loan:
            self.fields.pop("status")


class BorrowerForm(forms.ModelForm):
    class Meta:
        model = Borrower
        fields = ["username", "first_name", "last_name", "class_name", "email", "active"]

    def clean_username(self):
        return self.cleaned_data.get("username") or None


class BorrowerChoiceField(forms.ModelChoiceField):
    def label_from_instance(self, borrower):
        identifier = borrower.username or "no username"
        class_name = f" - {borrower.class_name}" if borrower.class_name else ""
        return f"{identifier} - {borrower.full_name}{class_name}"


class LoanBorrowerCorrectionForm(forms.Form):
    borrower = BorrowerChoiceField(label="Correct borrower", queryset=Borrower.objects.none())

    def __init__(self, *args, loan=None, **kwargs):
        super().__init__(*args, **kwargs)
        self.loan = loan
        self.fields["borrower"].queryset = Borrower.objects.filter(active=True).order_by("last_name", "first_name")

    def clean_borrower(self):
        borrower = self.cleaned_data["borrower"]
        if self.loan and borrower.pk == self.loan.borrower_id:
            raise forms.ValidationError("Choose a different borrower.")
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

    def clean_default_loan_days(self):
        days = self.cleaned_data["default_loan_days"]
        if days < 1 or days > 365:
            raise forms.ValidationError("Enter a loan period between 1 and 365 days.")
        return days


class CheckoutForm(forms.Form):
    borrower_code = forms.CharField(label="Borrower QR or UUID")
    copy_code = forms.CharField(label="Copy QR or UUID")
    due_date = forms.DateField(
        initial=default_form_due_date,
        widget=forms.DateInput(attrs={"type": "date"}),
    )


class ReturnForm(forms.Form):
    copy_code = forms.CharField(label="Copy QR or UUID")


class PhotoIntakeForm(forms.Form):
    photos = forms.FileField(
        label="Book photo",
        widget=forms.ClearableFileInput(attrs={"accept": "image/*", "capture": "environment"}),
        help_text="Use a close-up of the ISBN barcode when possible. Cover-only photos cannot be read without OCR or AI.",
    )
    isbn = forms.CharField(label="ISBN", max_length=20, required=False)
    title = forms.CharField(label="Title", max_length=255, required=False)
    authors = forms.CharField(label="Author(s)", required=False, widget=forms.Textarea(attrs={"rows": 2}))
    shelf_location = forms.CharField(label="Shelf location", max_length=128, required=False)
    condition = forms.ChoiceField(label="Condition", choices=Copy.Condition.choices, initial=Copy.Condition.GOOD)

    def clean_isbn(self):
        isbn = clean_isbn(self.cleaned_data.get("isbn"))
        if isbn and not is_valid_isbn(isbn):
            raise forms.ValidationError("Enter a valid ISBN-10 or ISBN-13.")
        return isbn


class CopyChoiceField(forms.ModelChoiceField):
    def label_from_instance(self, copy):
        details = [copy.book.title]
        if copy.book.authors:
            details.append(copy.book.authors)
        details.append(f"Copy #{copy.copy_number}")
        isbn = copy.book.isbn13 or copy.book.isbn10
        if isbn:
            details.append(f"ISBN {isbn}")
        if copy.shelf_location:
            details.append(f"Shelf {copy.shelf_location}")
        return " - ".join(details)


class CopyMultipleChoiceField(forms.ModelMultipleChoiceField):
    def label_from_instance(self, copy):
        return f"{copy.book.title} - copy #{copy.copy_number}"


class PhotoCirculationForm(forms.Form):
    class Action(models.TextChoices):
        CHECKOUT = "checkout", "Check out"
        CHECKIN = "checkin", "Check in / return"

    action = forms.ChoiceField(
        label="Action",
        choices=Action.choices,
        initial=Action.CHECKOUT,
        widget=forms.RadioSelect,
    )
    borrower = forms.UUIDField(label="Borrower", widget=forms.HiddenInput)
    basket_token = forms.CharField(required=False, widget=forms.HiddenInput)
    book_photo = forms.FileField(
        label="Book QR or ISBN barcode photo",
        required=False,
        widget=forms.ClearableFileInput(attrs={"accept": "image/*", "capture": "environment"}),
        help_text="Use the copy QR label when available. ISBN barcode works when there is only one matching copy.",
    )
    manual_copy = CopyChoiceField(label="Book copy", queryset=Copy.objects.none(), required=False)
    return_copies = CopyMultipleChoiceField(label="Books to return", queryset=Copy.objects.none(), required=False)
    due_date = forms.DateField(
        label="Due date",
        required=False,
        initial=default_form_due_date,
        widget=forms.DateInput(attrs={"type": "date"}),
    )

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self.fields["manual_copy"].queryset = Copy.objects.filter(status=Copy.Status.AVAILABLE).select_related("book").order_by("book__title", "copy_number")
        self.fields["manual_copy"].empty_label = "Select an exact book copy"
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
                self.add_error("borrower", "Choose a borrower from the search results.")
            else:
                cleaned_data["borrower"] = borrower
        if action == self.Action.CHECKIN and not cleaned_data.get("return_copies"):
            raise forms.ValidationError("Select at least one borrowed book to return.")
        if action == self.Action.CHECKOUT and not cleaned_data.get("book_photo") and not cleaned_data.get("manual_copy"):
            raise forms.ValidationError("Take a book photo or select the book manually.")
        return cleaned_data


class CsvImportForm(forms.Form):
    csv_file = forms.FileField(label="CSV file")


class FetchCoversForm(forms.Form):
    books = forms.ModelMultipleChoiceField(queryset=Book.objects.all())


class BorrowerCsvImportForm(forms.Form):
    csv_file = forms.FileField(label="Borrower CSV file")
