from datetime import timedelta

from django import forms
from django.db import models
from django.utils import timezone

from .models import Book, Borrower, Copy, SchoolProfile
from .photo_intake import clean_isbn, is_valid_isbn


def default_form_due_date():
    try:
        days = SchoolProfile.current().default_loan_days
    except Exception:
        days = 14
    return timezone.localdate() + timedelta(days=days)


class BookForm(forms.ModelForm):
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
            "description",
            "cover_image",
        ]


class CopyForm(forms.ModelForm):
    class Meta:
        model = Copy
        fields = ["shelf_location", "condition", "status"]


class BorrowerForm(forms.ModelForm):
    class Meta:
        model = Borrower
        fields = ["username", "first_name", "last_name", "class_name", "email", "active"]

    def clean_username(self):
        return self.cleaned_data.get("username") or None


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


class BorrowerChoiceField(forms.ModelChoiceField):
    def label_from_instance(self, borrower):
        username = borrower.username or "no username"
        return f"{username} - {borrower.full_name}"


class CopyChoiceField(forms.ModelChoiceField):
    def label_from_instance(self, copy):
        isbn = copy.book.isbn13 or copy.book.isbn10 or "no ISBN"
        authors = copy.book.authors or "author not recorded"
        shelf = copy.shelf_location or "no shelf"
        return f"{copy.book.title} - {authors} - copy #{copy.copy_number} - {isbn} - {shelf} - {copy.get_status_display()}"


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
    borrower = BorrowerChoiceField(label="Borrower", queryset=Borrower.objects.none())
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
        self.fields["borrower"].queryset = Borrower.objects.filter(active=True).order_by("username", "last_name", "first_name")
        self.fields["borrower"].empty_label = "Select borrower"
        self.fields["manual_copy"].queryset = Copy.objects.exclude(status=Copy.Status.ARCHIVED).select_related("book").order_by("book__title", "copy_number")
        self.fields["manual_copy"].empty_label = "Select an exact book copy"
        return_copies = Copy.objects.filter(status=Copy.Status.CHECKED_OUT, loans__return_date__isnull=True)
        borrower_id = self.data.get("borrower") if self.is_bound else self.initial.get("borrower")
        if borrower_id:
            return_copies = return_copies.filter(loans__borrower_id=borrower_id)
        else:
            return_copies = return_copies.none()
        self.fields["return_copies"].queryset = return_copies.select_related("book").distinct().order_by("book__title", "copy_number")

    def clean(self):
        cleaned_data = super().clean()
        if cleaned_data.get("action") == self.Action.CHECKIN and not cleaned_data.get("return_copies"):
            raise forms.ValidationError("Select at least one borrowed book to return.")
        if cleaned_data.get("action") == self.Action.CHECKOUT and not cleaned_data.get("book_photo") and not cleaned_data.get("manual_copy"):
            raise forms.ValidationError("Take a book photo or select the book manually.")
        return cleaned_data


class CsvImportForm(forms.Form):
    csv_file = forms.FileField(label="CSV file")


class BorrowerCsvImportForm(forms.Form):
    csv_file = forms.FileField(label="Borrower CSV file")
