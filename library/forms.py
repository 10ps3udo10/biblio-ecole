from datetime import timedelta

from django import forms
from django.db import models
from django.utils import timezone

from .models import Book, Borrower, Copy, SchoolProfile


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
            "title",
            "subtitle",
            "authors",
            "isbn10",
            "isbn13",
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


class BorrowerChoiceField(forms.ModelChoiceField):
    def label_from_instance(self, borrower):
        username = borrower.username or "no username"
        return f"{username} - {borrower.full_name}"


class PhotoCirculationForm(forms.Form):
    class Action(models.TextChoices):
        CHECKOUT = "checkout", "Check out"
        CHECKIN = "checkin", "Check in / return"

    action = forms.ChoiceField(label="Action", choices=Action.choices, initial=Action.CHECKOUT)
    borrower = BorrowerChoiceField(label="Borrower", queryset=Borrower.objects.none())
    book_photo = forms.FileField(
        label="Book QR or ISBN barcode photo",
        widget=forms.ClearableFileInput(attrs={"accept": "image/*", "capture": "environment"}),
        help_text="Use the copy QR label when available. ISBN barcode works when there is only one matching copy.",
    )
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


class CsvImportForm(forms.Form):
    csv_file = forms.FileField(label="CSV file")
