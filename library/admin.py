from django.contrib import admin

from .models import Book, Borrower, Copy, Loan, SchoolProfile


class CopyInline(admin.TabularInline):
    model = Copy
    extra = 0
    fields = ("copy_number", "shelf_location", "condition", "status", "source_photo", "source_position", "qr_code")
    readonly_fields = ("qr_code",)


@admin.register(Book)
class BookAdmin(admin.ModelAdmin):
    list_display = ("title", "authors", "isbn13", "publisher", "needs_information", "available_copies", "total_copies")
    search_fields = ("title", "subtitle", "authors", "isbn10", "isbn13", "publisher", "category", "topics")
    list_filter = ("needs_information", "language", "category", "identification_confidence", "publication_year")
    inlines = [CopyInline]


@admin.register(Copy)
class CopyAdmin(admin.ModelAdmin):
    list_display = ("book", "copy_number", "shelf_location", "condition", "status")
    search_fields = ("id", "qr_code", "book__title", "book__authors", "shelf_location", "source_photo")
    list_filter = ("status", "condition")
    readonly_fields = ("qr_code",)


@admin.register(Borrower)
class BorrowerAdmin(admin.ModelAdmin):
    list_display = ("username", "full_name", "class_name", "email", "active")
    search_fields = ("username", "first_name", "last_name", "class_name", "email", "id", "qr_code")
    list_filter = ("active", "class_name")
    readonly_fields = ("qr_code",)


@admin.register(Loan)
class LoanAdmin(admin.ModelAdmin):
    list_display = ("copy", "borrower", "checkout_date", "due_date", "return_date")
    search_fields = ("copy__book__title", "borrower__first_name", "borrower__last_name")
    list_filter = ("checkout_date", "due_date", "return_date")


@admin.register(SchoolProfile)
class SchoolProfileAdmin(admin.ModelAdmin):
    list_display = ("school_name", "short_name", "default_loan_days", "contact_email", "setup_completed", "updated_at")

    def has_add_permission(self, request):
        return not SchoolProfile.objects.exists()

    def has_delete_permission(self, request, obj=None):
        return False
