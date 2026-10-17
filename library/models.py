import uuid
from datetime import timedelta

from django.conf import settings
from django.db import models, transaction
from django.db.models import Q
from django.urls import reverse
from django.utils import timezone


class UserPreference(models.Model):
    class Theme(models.TextChoices):
        SYSTEM = "system", "System"
        LIGHT = "light", "Light"
        DARK = "dark", "Dark"

    class StartPage(models.TextChoices):
        OVERVIEW = "dashboard", "Overview"
        CIRCULATION = "photo_circulation", "Circulation"
        CATALOG = "book_list", "Catalog"

    class TableDensity(models.TextChoices):
        COMFORTABLE = "comfortable", "Comfortable"
        COMPACT = "compact", "Compact"

    user = models.OneToOneField(settings.AUTH_USER_MODEL, on_delete=models.CASCADE, related_name="library_preferences")
    theme = models.CharField(max_length=6, choices=Theme.choices, default=Theme.SYSTEM)
    start_page = models.CharField(max_length=20, choices=StartPage.choices, default=StartPage.OVERVIEW)
    table_density = models.CharField(max_length=12, choices=TableDensity.choices, default=TableDensity.COMFORTABLE)


class SchoolProfile(models.Model):
    school_name = models.CharField(max_length=255, default="School Library")
    short_name = models.CharField(max_length=80, blank=True)
    logo = models.ImageField(upload_to="branding/", blank=True)
    address = models.TextField(blank=True)
    contact_email = models.EmailField(blank=True)
    contact_phone = models.CharField(max_length=40, blank=True)
    default_loan_days = models.PositiveIntegerField(default=14)
    label_footer = models.CharField(max_length=160, blank=True)
    setup_completed = models.BooleanField(default=False)
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
    class IdentificationConfidence(models.TextChoices):
        HIGH = "high", "High"
        MEDIUM = "medium", "Medium"
        LOW = "low", "Low"

    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    title = models.CharField(max_length=255)
    subtitle = models.CharField(max_length=255, blank=True)
    authors = models.TextField(blank=True)
    isbn10 = models.CharField("ISBN-10", max_length=10, blank=True)
    isbn13 = models.CharField("ISBN-13", max_length=13, blank=True)
    publisher = models.CharField(max_length=255, blank=True)
    publication_year = models.PositiveIntegerField(null=True, blank=True)
    language = models.CharField(max_length=64, blank=True)
    page_count = models.PositiveIntegerField("Pages", null=True, blank=True)
    format = models.CharField(max_length=120, blank=True)
    category = models.CharField(max_length=160, blank=True)
    topics = models.TextField(blank=True)
    description = models.TextField(blank=True)
    montessori_levels = models.CharField("Suggested Montessori level", max_length=255, blank=True)
    suggested_age_range = models.CharField(max_length=40, blank=True)
    suggested_reading_level = models.CharField(max_length=160, blank=True)
    identification_confidence = models.CharField(
        max_length=16,
        choices=IdentificationConfidence.choices,
        blank=True,
    )
    review_notes = models.TextField(blank=True)
    bibliographic_source_url = models.URLField(blank=True)
    needs_information = models.BooleanField(default=False)
    cover_image = models.FileField(upload_to="covers/", blank=True)
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
    source_photo = models.CharField(max_length=255, blank=True)
    source_position = models.CharField(max_length=255, blank=True)

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


class EmployeePosition(models.Model):
    name = models.CharField(max_length=120, unique=True)
    active = models.BooleanField(default=True)

    class Meta:
        ordering = ["name"]

    def __str__(self):
        return self.name


class SchoolClass(models.Model):
    name = models.CharField(max_length=120, unique=True)
    active = models.BooleanField(default=True)

    class Meta:
        ordering = ["name"]
        verbose_name_plural = "school classes"

    def __str__(self):
        return self.name


class BorrowerIdSequence(models.Model):
    id = models.PositiveSmallIntegerField(primary_key=True, default=1, editable=False)
    current = models.PositiveBigIntegerField(default=0)

    @classmethod
    def next_id(cls):
        with transaction.atomic():
            sequence, _ = cls.objects.select_for_update().get_or_create(pk=1)
            sequence.current += 1
            sequence.save(update_fields=["current"])
            return f"B{sequence.current:06d}"


class Borrower(models.Model):
    class SchoolRole(models.TextChoices):
        STUDENT = "student", "Student"
        EMPLOYEE = "employee", "Employee"

    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    borrower_id = models.CharField("Borrower ID", max_length=80, unique=True, editable=False)
    school_id = models.CharField("School ID", max_length=80, unique=True, null=True, blank=True)
    first_name = models.CharField(max_length=120)
    last_name = models.CharField(max_length=120)
    school_class = models.ForeignKey(SchoolClass, verbose_name="Class", null=True, blank=True, on_delete=models.PROTECT, related_name="borrowers")
    school_role = models.CharField(max_length=16, choices=SchoolRole.choices, default=SchoolRole.STUDENT)
    position = models.ForeignKey(EmployeePosition, null=True, blank=True, on_delete=models.PROTECT, related_name="borrowers")
    email = models.EmailField(blank=True)
    qr_code = models.CharField(max_length=128, blank=True)
    active = models.BooleanField(default=True)
    staff_account = models.OneToOneField(
        settings.AUTH_USER_MODEL,
        null=True,
        blank=True,
        on_delete=models.SET_NULL,
        related_name="borrower_profile",
    )

    class Meta:
        ordering = ["last_name", "first_name"]
        indexes = [
            models.Index(fields=["borrower_id"]),
            models.Index(fields=["school_id"]),
            models.Index(fields=["last_name", "first_name"]),
        ]

    def __str__(self):
        return self.full_name

    def save(self, *args, **kwargs):
        if self.staff_account_id:
            self.first_name = self.staff_account.first_name
            self.last_name = self.staff_account.last_name
            self.email = self.staff_account.email
        if not self.qr_code:
            self.qr_code = self.qr_payload
        if not self.borrower_id:
            with transaction.atomic():
                self.borrower_id = BorrowerIdSequence.next_id()
                super().save(*args, **kwargs)
            return
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
    # Class of the borrower when the loan was made; kept even if the borrower changes class later.
    school_class = models.ForeignKey(
        SchoolClass,
        verbose_name="Class at checkout",
        related_name="loans",
        null=True,
        blank=True,
        on_delete=models.PROTECT,
    )
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

    def save(self, *args, **kwargs):
        if self._state.adding and self.school_class_id is None:
            self.school_class_id = self.borrower.school_class_id
        super().save(*args, **kwargs)

    @property
    def is_active(self):
        return self.return_date is None

    @property
    def is_overdue(self):
        return self.return_date is None and self.due_date < timezone.localdate()
