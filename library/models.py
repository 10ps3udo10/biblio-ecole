import uuid
from datetime import timedelta

from django.db import models
from django.db.models import Q
from django.urls import reverse
from django.utils import timezone


class SchoolProfile(models.Model):
    school_name = models.CharField(max_length=255, default="School Library")
    short_name = models.CharField(max_length=80, blank=True)
    address = models.TextField(blank=True)
    contact_email = models.EmailField(blank=True)
    contact_phone = models.CharField(max_length=40, blank=True)
    default_loan_days = models.PositiveIntegerField(default=14)
    label_footer = models.CharField(max_length=160, blank=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        verbose_name = "School profile"
        verbose_name_plural = "School profile"

    def __str__(self):
        return self.school_name

    def save(self, *args, **kwargs):
        self.pk = 1
        super().save(*args, **kwargs)

    @classmethod
    def current(cls):
        profile, _created = cls.objects.get_or_create(pk=1)
        return profile

    @property
    def display_name(self):
        return self.short_name or self.school_name


def default_due_date():
    try:
        days = SchoolProfile.current().default_loan_days
    except Exception:
        days = 14
    return timezone.localdate() + timedelta(days=days)


class Book(models.Model):
    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    title = models.CharField(max_length=255)
    subtitle = models.CharField(max_length=255, blank=True)
    authors = models.TextField(blank=True)
    isbn10 = models.CharField("ISBN-10", max_length=10, blank=True)
    isbn13 = models.CharField("ISBN-13", max_length=13, blank=True)
    publisher = models.CharField(max_length=255, blank=True)
    publication_year = models.PositiveIntegerField(null=True, blank=True)
    language = models.CharField(max_length=64, blank=True)
    description = models.TextField(blank=True)
    cover_image = models.FileField(upload_to="covers/", blank=True)
    ai_confidence = models.DecimalField(max_digits=5, decimal_places=2, null=True, blank=True)
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        ordering = ["title", "authors"]
        indexes = [
            models.Index(fields=["title"]),
            models.Index(fields=["isbn13"]),
            models.Index(fields=["isbn10"]),
        ]

    def __str__(self):
        return self.title

    def get_absolute_url(self):
        return reverse("book_detail", args=[self.pk])

    @property
    def total_copies(self):
        return self.copies.count()

    @property
    def available_copies(self):
        return self.copies.filter(status=Copy.Status.AVAILABLE).count()


class Copy(models.Model):
    class Status(models.TextChoices):
        AVAILABLE = "available", "Available"
        CHECKED_OUT = "checked_out", "Checked out"
        MISSING = "missing", "Missing"
        DAMAGED = "damaged", "Damaged"
        ARCHIVED = "archived", "Archived"

    class Condition(models.TextChoices):
        NEW = "new", "New"
        GOOD = "good", "Good"
        WORN = "worn", "Worn"
        DAMAGED = "damaged", "Damaged"

    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    book = models.ForeignKey(Book, related_name="copies", on_delete=models.CASCADE)
    copy_number = models.PositiveIntegerField()
    qr_code = models.CharField(max_length=128, blank=True)
    shelf_location = models.CharField(max_length=128, blank=True)
    condition = models.CharField(max_length=32, choices=Condition.choices, default=Condition.GOOD)
    status = models.CharField(max_length=32, choices=Status.choices, default=Status.AVAILABLE)

    class Meta:
        ordering = ["book__title", "copy_number"]
        constraints = [
            models.UniqueConstraint(fields=["book", "copy_number"], name="unique_copy_number_per_book"),
        ]

    def __str__(self):
        return f"{self.book.title} #{self.copy_number}"

    def save(self, *args, **kwargs):
        if not self.qr_code:
            self.qr_code = self.qr_payload
        super().save(*args, **kwargs)

    def get_absolute_url(self):
        return reverse("copy_detail", args=[self.pk])

    @property
    def qr_payload(self):
        return f"COPY:{self.id}"

    @property
    def active_loan(self):
        return self.loans.filter(return_date__isnull=True).select_related("borrower").first()


class Borrower(models.Model):
    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    username = models.CharField(max_length=80, unique=True, null=True, blank=True)
    first_name = models.CharField(max_length=120)
    last_name = models.CharField(max_length=120)
    class_name = models.CharField("Class", max_length=120, blank=True, db_column="class")
    email = models.EmailField(blank=True)
    qr_code = models.CharField(max_length=128, blank=True)
    active = models.BooleanField(default=True)

    class Meta:
        ordering = ["last_name", "first_name"]
        indexes = [
            models.Index(fields=["username"]),
            models.Index(fields=["last_name", "first_name"]),
            models.Index(fields=["class_name"]),
        ]

    def __str__(self):
        return self.full_name

    def save(self, *args, **kwargs):
        if not self.qr_code:
            self.qr_code = self.qr_payload
        super().save(*args, **kwargs)

    def get_absolute_url(self):
        return reverse("borrower_detail", args=[self.pk])

    @property
    def full_name(self):
        return f"{self.first_name} {self.last_name}".strip()

    @property
    def qr_payload(self):
        return f"BORROWER:{self.id}"


class Loan(models.Model):
    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    copy = models.ForeignKey(Copy, related_name="loans", on_delete=models.PROTECT)
    borrower = models.ForeignKey(Borrower, related_name="loans", on_delete=models.PROTECT)
    checkout_date = models.DateField(default=timezone.localdate)
    due_date = models.DateField(default=default_due_date)
    return_date = models.DateField(null=True, blank=True)

    class Meta:
        ordering = ["-checkout_date", "-due_date"]
        constraints = [
            models.UniqueConstraint(
                fields=["copy"],
                condition=Q(return_date__isnull=True),
                name="unique_active_loan_per_copy",
            ),
        ]

    def __str__(self):
        return f"{self.copy} to {self.borrower}"

    @property
    def is_active(self):
        return self.return_date is None

    @property
    def is_overdue(self):
        return self.return_date is None and self.due_date < timezone.localdate()
