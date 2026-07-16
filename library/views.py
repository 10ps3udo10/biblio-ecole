import csv
import logging
import uuid
from datetime import timedelta
from io import StringIO, TextIOWrapper
from urllib.parse import quote_plus

from django.conf import settings
from django.contrib import messages
from django.contrib.admin.views.decorators import staff_member_required
from django.contrib.auth.decorators import login_required
from django.core import signing
from django.core.files.base import ContentFile
from django.db import transaction
from django.db.models import Count, Max, Q
from django.http import FileResponse, Http404, HttpResponse, JsonResponse
from django.shortcuts import get_object_or_404, redirect, render
from django.urls import reverse
from django.utils import timezone
from django.utils.http import url_has_allowed_host_and_scheme
from django.utils.safestring import mark_safe
from django.views.decorators.http import require_GET, require_POST

from .forms import (
    BookForm,
    BookEditForm,
    BorrowerCsvImportForm,
    BorrowerForm,
    CheckoutForm,
    CopyForm,
    CopyEditForm,
    CsvImportForm,
    FetchCoversForm,
    LoanBorrowerCorrectionForm,
    PhotoCirculationForm,
    PhotoIntakeForm,
    ReturnForm,
    SchoolProfileForm,
    default_form_due_date,
)
from .catalog_import import import_catalog_rows
from .models import Book, Borrower, Copy, Loan, SchoolProfile
from .photo_intake import MetadataLookupError, clean_isbn, decode_barcodes_from_image, decode_isbn_from_image, download_cover_by_isbn, is_valid_isbn, lookup_book_by_isbn
from .qr import svg_qr


CIRCULATION_SALT = "shelf-school-circulation"
MAX_CHECKOUT_BOOKS = 20
logger = logging.getLogger(__name__)


def _uuid_from_code(value, prefix):
    value = value.strip()
    if ":" in value:
        found_prefix, value = value.split(":", 1)
        if found_prefix.upper() != prefix:
            raise ValueError(f"Expected {prefix} code")
    return uuid.UUID(value.strip())


def _next_copy_number(book):
    highest = book.copies.aggregate(max_copy=Max("copy_number"))["max_copy"] or 0
    return highest + 1


def _attach_intake_cover(book, isbn, uploaded_photo):
    if isbn:
        downloaded = download_cover_by_isbn(isbn)
        if downloaded:
            content, extension = downloaded
            book.cover_image.save(f"{isbn}.{extension}", ContentFile(content), save=False)
    else:
        book.cover_image = uploaded_photo


def _copy_from_photo(uploaded_file, action):
    codes = decode_barcodes_from_image(uploaded_file)
    for code in codes:
        value = (code or "").strip()
        if value.upper().startswith("COPY:"):
            try:
                return Copy.objects.select_related("book").get(pk=_uuid_from_code(value, "COPY"))
            except (ValueError, Copy.DoesNotExist):
                continue

    isbn = ""
    for code in codes:
        candidate = clean_isbn(code)
        if candidate.startswith(("978", "979")) and len(candidate) == 13:
            isbn = candidate
            break
    if not isbn:
        raise ValueError("No copy QR or ISBN barcode was detected in the photo.")

    books = Book.objects.filter(Q(isbn13=isbn) | Q(isbn10=isbn)).distinct()
    if not books.exists():
        raise ValueError(f"No cataloged book has ISBN {isbn}.")
    copies = Copy.objects.select_related("book").filter(book__in=books)
    if action == PhotoCirculationForm.Action.CHECKOUT:
        copies = copies.filter(status=Copy.Status.AVAILABLE)
    else:
        copies = copies.filter(status=Copy.Status.CHECKED_OUT, loans__return_date__isnull=True).distinct()
    count = copies.count()
    if count == 1:
        return copies.get()
    if count == 0:
        raise ValueError(f"No matching copy is available for ISBN {isbn}.")
    raise ValueError(f"ISBN {isbn} matches multiple copies. Use the copy QR label for circulation.")


def _perform_circulation(copy, borrower, action, due_date=None):
    if action == PhotoCirculationForm.Action.CHECKOUT:
        if copy.status != Copy.Status.AVAILABLE or copy.loans.filter(return_date__isnull=True).exists():
            raise ValueError("This copy is no longer available for check out.")
        Loan.objects.create(copy=copy, borrower=borrower, due_date=due_date or default_form_due_date())
        copy.status = Copy.Status.CHECKED_OUT
        copy.save(update_fields=["status"])
        return f"Checked out {copy.book.title} to {borrower.full_name}."

    loan = copy.loans.filter(return_date__isnull=True).select_related("borrower").first()
    if loan is None:
        raise ValueError("This copy no longer has an active loan to check in.")
    if loan.borrower_id != borrower.id:
        raise ValueError("This copy is checked out to a different borrower.")
    loan.return_date = timezone.localdate()
    loan.save(update_fields=["return_date"])
    copy.status = Copy.Status.AVAILABLE
    copy.save(update_fields=["status"])
    return f"Checked in {copy.book.title} from {borrower.full_name}."


def _circulation_payload(token):
    payload = signing.loads(token, salt=CIRCULATION_SALT, max_age=600)
    action = payload.get("action")
    copy_ids = payload.get("copy_ids")
    if action not in PhotoCirculationForm.Action.values:
        raise ValueError("That circulation confirmation is invalid.")
    if not isinstance(copy_ids, list) or not copy_ids or len(copy_ids) > MAX_CHECKOUT_BOOKS:
        raise ValueError("That circulation confirmation is invalid.")
    if len(copy_ids) != len(set(copy_ids)):
        raise ValueError("The same book appears more than once.")
    return payload


def _ordered_copies(copy_ids, *, lock=False):
    copies = Copy.objects.select_related("book")
    if lock:
        copies = copies.select_for_update()
    by_id = {str(copy.id): copy for copy in copies.filter(pk__in=copy_ids)}
    if len(by_id) != len(copy_ids):
        raise ValueError("One of the selected books no longer exists.")
    return [by_id[copy_id] for copy_id in copy_ids]


def _checkout_confirmation(request, form, payload):
    borrower = Borrower.objects.get(pk=payload["borrower_id"])
    copies = _ordered_copies(payload["copy_ids"])
    token = signing.dumps(payload, salt=CIRCULATION_SALT)
    return render(
        request,
        "library/photo_circulation.html",
        _circulation_context(
            form,
            confirmation=True,
            confirmation_token=token,
            copies=copies,
            borrower=borrower,
            action=PhotoCirculationForm.Action.CHECKOUT,
            due_date=payload["due_date"],
        ),
    )


def _checkout_scan(request, form, payload):
    copies = _ordered_copies(payload["copy_ids"])
    token = signing.dumps(payload, salt=CIRCULATION_SALT)
    if not form.is_bound:
        form.initial["basket_token"] = token
    return render(
        request,
        "library/photo_circulation.html",
        _circulation_context(
            form,
            resume_checkout=True,
            basket_token=token,
            basket_copies=copies,
            basket_count=len(copies),
        ),
    )


def _circulation_context(form, **extra):
    borrower_id = form.data.get("borrower") if form.is_bound else form.initial.get("borrower")
    try:
        borrower_id = uuid.UUID(str(borrower_id)) if borrower_id else None
    except (TypeError, ValueError):
        borrower_id = None
    selected_borrower = Borrower.objects.filter(pk=borrower_id).first() if borrower_id else None
    context = {
        "form": form,
        "has_borrowers": Borrower.objects.filter(Q(active=True) | Q(loans__return_date__isnull=True)).exists(),
        "selected_borrower": selected_borrower,
    }
    context.update(extra)
    return context


@login_required
def dashboard(request):
    active_loans = Loan.objects.filter(return_date__isnull=True)
    total_copies = Copy.objects.count()
    available_copies = Copy.objects.filter(status=Copy.Status.AVAILABLE).count()
    unavailable_copies = Copy.objects.filter(status__in=[Copy.Status.DAMAGED, Copy.Status.ARCHIVED]).count()
    today = timezone.localdate()
    circulation_days = []
    for days_ago in range(6, -1, -1):
        day = today - timedelta(days=days_ago)
        circulation_days.append(
            {
                "date": day,
                "checkouts": Loan.objects.filter(checkout_date=day).count(),
                "returns": Loan.objects.filter(return_date=day).count(),
            }
        )
    max_daily_activity = max(
        [item["checkouts"] for item in circulation_days] + [item["returns"] for item in circulation_days] + [1]
    )
    context = {
        "total_books": Book.objects.count(),
        "total_copies": total_copies,
        "available_copies": available_copies,
        "unavailable_copies": unavailable_copies,
        "available_percent": round((available_copies / total_copies) * 100) if total_copies else 0,
        "borrowed_percent": round((active_loans.count() / total_copies) * 100) if total_copies else 0,
        "unavailable_percent": round((unavailable_copies / total_copies) * 100) if total_copies else 0,
        "borrowed_books": active_loans.count(),
        "overdue_books": active_loans.filter(due_date__lt=timezone.localdate()).count(),
        "circulation_days": circulation_days,
        "max_daily_activity": max_daily_activity,
        "recent_books": Book.objects.order_by("-created_at")[:6],
        "recent_loans": Loan.objects.select_related("copy__book", "borrower").order_by("-checkout_date")[:8],
        "setup_needed": not SchoolProfile.current().setup_completed,
    }
    return render(request, "library/dashboard.html", context)


@login_required
def book_list(request):
    query = request.GET.get("q", "").strip()
    sort = request.GET.get("sort", "title")
    direction = request.GET.get("direction", "asc")
    sort_fields = {
        "title": ("title",),
        "author": ("authors",),
        "isbn": ("isbn13", "isbn10"),
        "availability": ("available_count",),
        "copies": ("copy_count",),
        "cover": ("cover_image",),
        "catalog_status": ("needs_information",),
    }
    if sort not in sort_fields:
        sort = "title"
    if direction not in {"asc", "desc"}:
        direction = "asc"
    books = Book.objects.annotate(
        copy_count=Count("copies"),
        available_count=Count("copies", filter=Q(copies__status=Copy.Status.AVAILABLE)),
    )
    if query:
        books = books.filter(
            Q(title__icontains=query)
            | Q(subtitle__icontains=query)
            | Q(authors__icontains=query)
            | Q(isbn10__icontains=query)
            | Q(isbn13__icontains=query)
            | Q(publisher__icontains=query)
            | Q(category__icontains=query)
            | Q(topics__icontains=query)
            | Q(montessori_levels__icontains=query)
            | Q(suggested_age_range__icontains=query)
            | Q(suggested_reading_level__icontains=query)
            | Q(copies__shelf_location__icontains=query)
            | Q(copies__status__icontains=query)
        ).distinct()
    prefix = "-" if direction == "desc" else ""
    order_by = [f"{prefix}{field}" for field in sort_fields[sort]]
    if sort != "title":
        order_by.append("title")
    books = list(books.order_by(*order_by))
    for book in books:
        book.cover_fetch_eligible = not book.cover_image and is_valid_isbn(book.isbn13 or book.isbn10)
    sort_headers = [
        {
            "key": key,
            "label": label,
            "active": sort == key,
            "direction": direction if sort == key else "",
            "next_direction": "desc" if sort == key and direction == "asc" else "asc",
        }
        for key, label in (
            ("title", "Title"),
            ("author", "Contributors"),
            ("isbn", "ISBN"),
            ("availability", "Availability"),
            ("copies", "Copies"),
            ("cover", "Cover"),
            ("catalog_status", "Catalog status"),
        )
    ]
    return render(
        request,
        "library/book_list.html",
        {"books": books, "query": query, "sort": sort, "direction": direction, "sort_headers": sort_headers},
    )


@login_required
@require_POST
def fetch_book_covers(request):
    form = FetchCoversForm(request.POST)
    next_url = request.POST.get("next", "")
    redirect_to = next_url if url_has_allowed_host_and_scheme(
        next_url,
        allowed_hosts={request.get_host()},
        require_https=request.is_secure(),
    ) else reverse("book_list")
    if not form.is_valid():
        messages.error(request, "Select at least one book with a missing cover.")
        return redirect(redirect_to)

    counts = {"downloaded": 0, "unavailable": 0, "without_isbn": 0, "existing": 0, "failed": 0}
    for book in form.cleaned_data["books"].order_by("title"):
        if book.cover_image:
            counts["existing"] += 1
            continue
        isbn = book.isbn13 or book.isbn10
        if not is_valid_isbn(isbn):
            counts["without_isbn"] += 1
            continue
        try:
            downloaded = download_cover_by_isbn(isbn)
            if not downloaded:
                counts["unavailable"] += 1
                continue
            content, extension = downloaded
            book.cover_image.save(f"{clean_isbn(isbn)}.{extension}", ContentFile(content), save=False)
            book.save(update_fields=["cover_image", "updated_at"])
            counts["downloaded"] += 1
        except Exception:
            logger.exception("Could not fetch a cover for book %s", book.pk)
            counts["failed"] += 1

    summary = [
        f'{counts["downloaded"]} downloaded',
        f'{counts["unavailable"]} unavailable',
        f'{counts["without_isbn"]} without a valid ISBN',
        f'{counts["existing"]} already present',
    ]
    if counts["failed"]:
        summary.append(f'{counts["failed"]} failed')
    messages.success(request, f'Cover fetch complete: {", ".join(summary)}.')
    return redirect(redirect_to)


@login_required
def book_detail(request, pk):
    book = get_object_or_404(Book, pk=pk)
    copy_sort = request.GET.get("sort", "copy")
    copy_direction = request.GET.get("direction", "asc")
    copy_sort_fields = {
        "copy": ("copy_number",),
        "status": ("status",),
        "shelf": ("shelf_location",),
        "condition": ("condition",),
    }
    if copy_sort not in copy_sort_fields:
        copy_sort = "copy"
    if copy_direction not in {"asc", "desc"}:
        copy_direction = "asc"
    loans = Loan.objects.filter(copy__book=book).select_related("copy", "borrower")[:20]
    prefix = "-" if copy_direction == "desc" else ""
    copy_order = [f"{prefix}{field}" for field in copy_sort_fields[copy_sort]]
    if copy_sort != "copy":
        copy_order.append("copy_number")
    copies = list(book.copies.order_by(*copy_order))
    active_copy_ids = set(Loan.objects.filter(copy__book=book, return_date__isnull=True).values_list("copy_id", flat=True))
    for copy in copies:
        copy.has_active_loan = copy.id in active_copy_ids
    return render(
        request,
        "library/book_detail.html",
        {
            "book": book,
            "copies": copies,
            "loans": loans,
            "has_active_loans": bool(active_copy_ids),
            "has_multiple_copies": len(copies) > 1,
            "sort_headers": [
                {
                    "key": key,
                    "label": label,
                    "active": copy_sort == key,
                    "direction": copy_direction if copy_sort == key else "",
                    "next_direction": "desc" if copy_sort == key and copy_direction == "asc" else "asc",
                }
                for key, label in (("copy", "Copy"), ("status", "Status"), ("shelf", "Shelf"), ("condition", "Condition"))
            ],
        },
    )


@login_required
@require_POST
def delete_book(request, pk):
    book = get_object_or_404(Book, pk=pk)
    loans = Loan.objects.filter(copy__book=book)
    if loans.filter(return_date__isnull=True).exists():
        messages.error(request, "This book cannot be deleted while a copy is checked out.")
        return redirect(book)
    title = book.title
    loans.delete()
    book.delete()
    messages.success(request, f"Deleted {title}, its copies, and its loan history.")
    return redirect("book_list")


@login_required
@require_POST
def delete_book_photo(request, pk):
    book = get_object_or_404(Book, pk=pk)
    if book.cover_image:
        book.cover_image.delete(save=False)
        book.cover_image = ""
        book.save(update_fields=["cover_image", "updated_at"])
        messages.success(request, "Stored book photo deleted.")
    return redirect(book)


@login_required
@require_GET
def isbn_metadata(request):
    isbn = clean_isbn(request.GET.get("isbn"))
    if not is_valid_isbn(isbn):
        return JsonResponse({"error": "This is not a valid ISBN-10 or ISBN-13."}, status=400)

    existing = Book.objects.filter(Q(isbn13=isbn) | Q(isbn10=isbn)).first()
    if existing:
        return JsonResponse(
            {
                "source": "catalog",
                "title": existing.title,
                "authors": existing.authors,
                "message": "This ISBN is already cataloged. Tracking it will add another physical copy.",
            }
        )

    try:
        metadata = lookup_book_by_isbn(isbn)
    except MetadataLookupError:
        return JsonResponse({"error": "Free ISBN metadata is temporarily unavailable."}, status=503)
    if not metadata:
        return JsonResponse(
            {
                "source": "none",
                "title": "",
                "authors": "",
                "message": "This ISBN is valid, but no free catalog metadata was found. It will be saved; enter the title and author manually.",
                "search_url": f"https://www.google.com/search?q={quote_plus(chr(34) + isbn + chr(34) + ' book')}",
            }
        )
    return JsonResponse(
        {
            "source": "open_library",
            "title": metadata.get("title", ""),
            "subtitle": metadata.get("subtitle", ""),
            "authors": metadata.get("authors", ""),
            "publisher": metadata.get("publisher", ""),
            "publication_year": metadata.get("publication_year"),
            "language": metadata.get("language", ""),
            "description": metadata.get("description", ""),
            "cover_url": metadata.get("cover_url", ""),
            "message": "Book details filled from the free Open Library catalog.",
        }
    )


@login_required
def book_create(request):
    if request.method == "POST":
        form = BookForm(request.POST, request.FILES)
        if form.is_valid():
            book = form.save(commit=False)
            isbn = book.isbn13 or book.isbn10
            book.needs_information = book.needs_information or not (isbn and book.authors and book.language)
            if not book.cover_image:
                _attach_intake_cover(book, isbn, None)
            book.save()
            Copy.objects.create(
                book=book,
                copy_number=1,
                shelf_location=form.cleaned_data.get("first_copy_shelf", ""),
                condition=form.cleaned_data.get("first_copy_condition") or Copy.Condition.GOOD,
            )
            messages.success(request, "Book and first copy added.")
            return redirect(book)
    else:
        form = BookForm(initial={"first_copy_condition": Copy.Condition.GOOD})
    return render(request, "library/book_form.html", {"form": form, "title": "Add book", "is_edit": False})


@login_required
def book_edit(request, pk):
    book = get_object_or_404(Book, pk=pk)
    if request.method == "POST":
        form = BookEditForm(request.POST, request.FILES, instance=book)
        if form.is_valid():
            book = form.save()
            messages.success(request, "Book details updated.")
            return redirect(book)
    else:
        form = BookEditForm(instance=book)
    return render(request, "library/book_form.html", {"form": form, "title": "Edit book", "is_edit": True})


@login_required
def photo_intake(request):
    if request.method == "POST":
        form = PhotoIntakeForm(request.POST, request.FILES)
        if form.is_valid():
            photo = form.cleaned_data["photos"]
            isbn = clean_isbn(form.cleaned_data.get("isbn")) or decode_isbn_from_image(photo)
            existing_book = None
            if isbn:
                existing_book = Book.objects.filter(Q(isbn13=isbn) | Q(isbn10=isbn)).first()

            if existing_book is not None:
                if not existing_book.cover_image:
                    _attach_intake_cover(existing_book, isbn, photo)
                    existing_book.save(update_fields=["cover_image", "updated_at"])
                copy = Copy.objects.create(
                    book=existing_book,
                    copy_number=_next_copy_number(existing_book),
                    shelf_location=form.cleaned_data.get("shelf_location", ""),
                    condition=form.cleaned_data.get("condition") or Copy.Condition.GOOD,
                )
                messages.success(request, f"Added copy #{copy.copy_number} to the existing title. Print its QR label before shelving.")
                return redirect(copy)

            metadata = {}
            if isbn:
                try:
                    metadata = lookup_book_by_isbn(isbn)
                except MetadataLookupError:
                    messages.warning(request, "The book was tracked, but free ISBN metadata lookup was unavailable.")

            if not isbn and not form.cleaned_data.get("title"):
                form.add_error(None, "No ISBN barcode was detected. Enter the ISBN or title, or retake a close-up photo of the ISBN barcode.")
                return render(request, "library/photo_intake.html", {"form": form})

            title = form.cleaned_data.get("title") or metadata.get("title") or f"ISBN {isbn}"
            authors = form.cleaned_data.get("authors") or metadata.get("authors", "")
            book = Book(
                title=title,
                subtitle=metadata.get("subtitle", ""),
                authors=authors,
                isbn10=metadata.get("isbn10") or (isbn if len(isbn) == 10 else ""),
                isbn13=metadata.get("isbn13") or (isbn if len(isbn) == 13 else ""),
                publisher=metadata.get("publisher", ""),
                publication_year=metadata.get("publication_year"),
                language=metadata.get("language", ""),
                description=metadata.get("description", ""),
                needs_information=not (isbn and authors and metadata.get("language")),
            )
            _attach_intake_cover(book, isbn, photo)
            book.save()
            copy = Copy.objects.create(
                book=book,
                copy_number=1,
                shelf_location=form.cleaned_data.get("shelf_location", ""),
                condition=form.cleaned_data.get("condition") or Copy.Condition.GOOD,
            )
            messages.success(request, "Photo intake created a tracked copy. Print its QR label before shelving.")
            return redirect(copy)
    else:
        form = PhotoIntakeForm()
    return render(request, "library/photo_intake.html", {"form": form})


@login_required
def add_copy(request, book_pk):
    book = get_object_or_404(Book, pk=book_pk)
    if request.method == "POST":
        form = CopyForm(request.POST)
        if form.is_valid():
            copy = form.save(commit=False)
            copy.book = book
            copy.copy_number = _next_copy_number(book)
            copy.save()
            messages.success(request, "Copy added.")
            return redirect(copy)
    else:
        form = CopyForm(initial={"condition": Copy.Condition.GOOD, "status": Copy.Status.AVAILABLE})
    return render(request, "library/copy_form.html", {"form": form, "book": book})


@login_required
def copy_edit(request, pk):
    copy = get_object_or_404(Copy.objects.select_related("book"), pk=pk)
    if request.method == "POST":
        form = CopyEditForm(request.POST, instance=copy)
        if form.is_valid():
            copy = form.save()
            messages.success(request, "Copy details updated.")
            return redirect(copy)
    else:
        form = CopyEditForm(instance=copy)
    return render(request, "library/copy_form.html", {"form": form, "book": copy.book, "copy": copy, "is_edit": True})


@login_required
def copy_detail(request, pk):
    copy = get_object_or_404(Copy.objects.select_related("book"), pk=pk)
    loans = copy.loans.select_related("borrower").all()[:20]
    active_loan = copy.active_loan
    return render(
        request,
        "library/copy_detail.html",
        {
            "copy": copy,
            "loans": loans,
            "active_loan": active_loan,
            "has_multiple_copies": copy.book.copies.count() > 1,
        },
    )


@staff_member_required
def correct_loan_borrower(request, pk):
    loan = get_object_or_404(
        Loan.objects.select_related("copy__book", "borrower"),
        pk=pk,
        return_date__isnull=True,
    )
    if request.method == "POST":
        form = LoanBorrowerCorrectionForm(request.POST, loan=loan)
        if form.is_valid():
            with transaction.atomic():
                locked_loan = get_object_or_404(
                    Loan.objects.select_for_update().select_related("copy__book", "borrower"),
                    pk=loan.pk,
                    return_date__isnull=True,
                )
                new_borrower = form.cleaned_data["borrower"]
                if locked_loan.borrower_id == new_borrower.id:
                    form.add_error("borrower", "Choose a different borrower.")
                else:
                    previous_name = locked_loan.borrower.full_name
                    locked_loan.borrower = new_borrower
                    locked_loan.save(update_fields=["borrower"])
                    messages.success(
                        request,
                        f"Changed the borrower for {locked_loan.copy.book.title} from {previous_name} to {new_borrower.full_name}.",
                    )
                    return redirect(locked_loan.copy)
    else:
        form = LoanBorrowerCorrectionForm(loan=loan)
    return render(request, "library/loan_borrower_form.html", {"form": form, "loan": loan})


@login_required
@require_POST
def delete_copy(request, pk):
    with transaction.atomic():
        copy = get_object_or_404(Copy.objects.select_for_update().select_related("book"), pk=pk)
        book = Book.objects.select_for_update().get(pk=copy.book_id)
        if copy.loans.filter(return_date__isnull=True).exists():
            messages.error(request, "This copy cannot be deleted while it is checked out.")
            return redirect(copy)
        if Copy.objects.filter(book=book).count() <= 1:
            messages.error(request, "The last copy cannot be deleted separately. Delete the book instead.")
            return redirect(copy)
        copy_number = copy.copy_number
        copy.loans.all().delete()
        copy.delete()
    messages.success(request, f"Deleted copy #{copy_number} of {book.title} and its loan history.")
    return redirect(book)


@login_required
def borrower_list(request):
    query = request.GET.get("q", "").strip()
    sort = request.GET.get("sort", "borrower")
    direction = request.GET.get("direction", "asc")
    sort_fields = {
        "borrower": ("last_name", "first_name"),
        "class": ("class_name",),
        "loans": ("active_loan_count",),
        "status": ("active",),
    }
    if sort not in sort_fields:
        sort = "borrower"
    if direction not in {"asc", "desc"}:
        direction = "asc"
    borrowers = Borrower.objects.annotate(
        active_loan_count=Count("loans", filter=Q(loans__return_date__isnull=True)),
        overdue_loan_count=Count(
            "loans",
            filter=Q(loans__return_date__isnull=True, loans__due_date__lt=timezone.localdate()),
        ),
    )
    if query:
        borrowers = borrowers.filter(
            Q(username__icontains=query)
            | Q(first_name__icontains=query)
            | Q(last_name__icontains=query)
            | Q(class_name__icontains=query)
            | Q(email__icontains=query)
        )
    prefix = "-" if direction == "desc" else ""
    order_by = [f"{prefix}{field}" for field in sort_fields[sort]]
    if sort != "borrower":
        order_by.extend(["last_name", "first_name"])
    borrowers = borrowers.order_by(*order_by)
    sort_headers = [
        {
            "key": key,
            "label": label,
            "active": sort == key,
            "direction": direction if sort == key else "",
            "next_direction": "desc" if sort == key and direction == "asc" else "asc",
        }
        for key, label in (
            ("borrower", "Borrower"),
            ("class", "Class"),
            ("loans", "Current loans"),
            ("status", "Status"),
        )
    ]
    return render(
        request,
        "library/borrower_list.html",
        {
            "borrowers": borrowers,
            "query": query,
            "sort": sort,
            "direction": direction,
            "sort_headers": sort_headers,
            "total_borrowers": Borrower.objects.count(),
            "active_borrowers": Borrower.objects.filter(active=True).count(),
            "borrowers_with_loans": Borrower.objects.filter(loans__return_date__isnull=True).distinct().count(),
        },
    )


@login_required
def borrower_detail(request, pk):
    borrower = get_object_or_404(Borrower, pk=pk)
    active_loans = borrower.loans.filter(return_date__isnull=True).select_related("copy__book")
    loan_history = borrower.loans.select_related("copy__book")[:30]
    return render(
        request,
        "library/borrower_detail.html",
        {
            "borrower": borrower,
            "active_loans": active_loans,
            "loan_history": loan_history,
            "active_loan_count": active_loans.count(),
            "overdue_loan_count": active_loans.filter(due_date__lt=timezone.localdate()).count(),
        },
    )


@login_required
def borrower_create(request):
    if request.method == "POST":
        form = BorrowerForm(request.POST)
        if form.is_valid():
            borrower = form.save()
            messages.success(request, "Borrower added.")
            return redirect(borrower)
    else:
        form = BorrowerForm(initial={"active": True})
    return render(request, "library/borrower_form.html", {"form": form, "title": "Add borrower"})


@login_required
def borrower_edit(request, pk):
    borrower = get_object_or_404(Borrower, pk=pk)
    if request.method == "POST":
        form = BorrowerForm(request.POST, instance=borrower)
        if form.is_valid():
            borrower = form.save()
            messages.success(request, "Borrower details updated.")
            return redirect(borrower)
    else:
        form = BorrowerForm(instance=borrower)
    return render(request, "library/borrower_form.html", {"form": form, "title": "Edit borrower"})


@require_GET
def circulation_borrower_search(request):
    query = request.GET.get("q", "").strip()
    action = request.GET.get("action", PhotoCirculationForm.Action.CHECKOUT)
    if len(query) < 2 or action not in PhotoCirculationForm.Action.values:
        return JsonResponse({"results": []})

    borrowers = Borrower.objects.all()
    if action == PhotoCirculationForm.Action.CHECKOUT:
        borrowers = borrowers.filter(active=True)
    else:
        borrowers = borrowers.filter(loans__return_date__isnull=True)
    borrowers = (
        borrowers.filter(
            Q(username__icontains=query)
            | Q(first_name__icontains=query)
            | Q(last_name__icontains=query)
        )
        .distinct()
        .order_by("last_name", "first_name")[:8]
    )
    return JsonResponse(
        {
            "results": [
                {
                    "id": str(borrower.id),
                    "name": borrower.full_name,
                    "username": borrower.username or "",
                    "class_name": borrower.class_name,
                }
                for borrower in borrowers
            ]
        }
    )


@require_GET
def circulation_borrower_loans(request, pk):
    loans = Loan.objects.filter(
        borrower_id=pk,
        return_date__isnull=True,
    ).select_related("copy__book").order_by("copy__book__title", "copy__copy_number")
    return JsonResponse(
        {
            "loans": [
                {
                    "copy_id": str(loan.copy_id),
                    "title": loan.copy.book.title,
                    "copy_number": loan.copy.copy_number,
                    "due_date": loan.due_date.isoformat(),
                    "overdue": loan.is_overdue,
                }
                for loan in loans
            ]
        }
    )


def photo_circulation(request):
    if request.method == "POST":
        confirmation_token = request.POST.get("confirmation_token")
        intent = request.POST.get("intent", "confirm")
        if confirmation_token and intent == "add_another":
            try:
                payload = _circulation_payload(confirmation_token)
                if payload["action"] != PhotoCirculationForm.Action.CHECKOUT:
                    raise ValueError("Only checkout supports adding another book.")
                borrower = Borrower.objects.get(pk=payload["borrower_id"], active=True)
                if len(payload["copy_ids"]) >= MAX_CHECKOUT_BOOKS:
                    raise ValueError(f"A checkout can contain at most {MAX_CHECKOUT_BOOKS} books.")
                form = PhotoCirculationForm(
                    initial={
                        "action": payload["action"],
                        "borrower": borrower.id,
                        "due_date": payload["due_date"],
                    }
                )
                return _checkout_scan(request, form, payload)
            except signing.BadSignature:
                messages.error(request, "That checkout basket expired. Start the checkout again.")
            except (Borrower.DoesNotExist, KeyError, ValueError) as exc:
                messages.error(request, str(exc) or "That checkout basket is no longer valid.")
            return redirect("photo_circulation")

        remove_copy_id = request.POST.get("remove_copy_id")
        if confirmation_token and remove_copy_id:
            try:
                payload = _circulation_payload(confirmation_token)
                if payload["action"] != PhotoCirculationForm.Action.CHECKOUT:
                    raise ValueError("Books can only be removed from a checkout basket.")
                borrower = Borrower.objects.get(pk=payload["borrower_id"], active=True)
                if remove_copy_id not in payload["copy_ids"]:
                    raise ValueError("That book is not in this checkout basket.")
                payload["copy_ids"] = [copy_id for copy_id in payload["copy_ids"] if copy_id != remove_copy_id]
                if not payload["copy_ids"]:
                    messages.info(request, "The checkout basket is empty.")
                    next_url = reverse("photo_circulation")
                    return redirect(f"{next_url}?borrower={borrower.id}&action={payload['action']}")
                form = PhotoCirculationForm(
                    initial={
                        "action": payload["action"],
                        "borrower": borrower.id,
                        "due_date": payload["due_date"],
                    }
                )
                return _checkout_confirmation(request, form, payload)
            except signing.BadSignature:
                messages.error(request, "That checkout basket expired. Start the checkout again.")
            except (Borrower.DoesNotExist, KeyError, ValueError) as exc:
                messages.error(request, str(exc) or "That checkout basket is no longer valid.")
            return redirect("photo_circulation")

        if confirmation_token:
            try:
                payload = _circulation_payload(confirmation_token)
                action = payload["action"]
                borrower = Borrower.objects.get(pk=payload["borrower_id"])
                if action == PhotoCirculationForm.Action.CHECKOUT and not borrower.active:
                    raise ValueError("This borrower is no longer active.")
                due_date = payload.get("due_date") or None
                with transaction.atomic():
                    copies = _ordered_copies(payload["copy_ids"], lock=True)
                    for selected_copy in copies:
                        _perform_circulation(selected_copy, borrower, action, due_date)
                    if action == PhotoCirculationForm.Action.CHECKOUT:
                        if len(copies) == 1:
                            success_message = f"Checked out {copies[0].book.title} to {borrower.full_name}."
                        else:
                            success_message = f"Checked out {len(copies)} books to {borrower.full_name}."
                    else:
                        success_message = f"Returned {len(copies)} book{'s' if len(copies) != 1 else ''} for {borrower.full_name}."
            except signing.BadSignature:
                messages.error(request, "That circulation confirmation expired. Please scan the book again.")
                return redirect("photo_circulation")
            except (Borrower.DoesNotExist, Copy.DoesNotExist, KeyError, ValueError) as exc:
                messages.error(request, str(exc) or "The circulation record changed. Please scan the book again.")
                return redirect("photo_circulation")
            messages.success(request, success_message)
            next_url = reverse("photo_circulation")
            return redirect(f"{next_url}?borrower={borrower.id}&action={action}")

        form = PhotoCirculationForm(request.POST, request.FILES)
        if form.is_valid():
            action = form.cleaned_data["action"]
            borrower = form.cleaned_data["borrower"]
            return_copies = list(form.cleaned_data.get("return_copies") or [])
            if action == PhotoCirculationForm.Action.CHECKIN and return_copies:
                for selected_copy in return_copies:
                    loan = selected_copy.active_loan
                    if loan is None or loan.borrower_id != borrower.id:
                        form.add_error("return_copies", "One of these books is not checked out to the selected borrower.")
                        return render(request, "library/photo_circulation.html", _circulation_context(form))
                token = signing.dumps(
                    {
                        "copy_ids": [str(selected_copy.id) for selected_copy in return_copies],
                        "borrower_id": str(borrower.id),
                        "action": action,
                        "due_date": "",
                    },
                    salt=CIRCULATION_SALT,
                )
                return render(
                    request,
                    "library/photo_circulation.html",
                    _circulation_context(
                        form,
                        confirmation=True,
                        confirmation_token=token,
                        copies=return_copies,
                        borrower=borrower,
                        action=action,
                    ),
                )
            basket_payload = None
            basket_token = form.cleaned_data.get("basket_token")
            if action == PhotoCirculationForm.Action.CHECKOUT and basket_token:
                try:
                    basket_payload = _circulation_payload(basket_token)
                    if basket_payload["action"] != action or basket_payload["borrower_id"] != str(borrower.id):
                        raise ValueError("The checkout basket belongs to a different transaction.")
                    if len(basket_payload["copy_ids"]) >= MAX_CHECKOUT_BOOKS:
                        raise ValueError(f"A checkout can contain at most {MAX_CHECKOUT_BOOKS} books.")
                except signing.BadSignature:
                    form.add_error(None, "That checkout basket expired. Start the checkout again.")
                    return render(request, "library/photo_circulation.html", _circulation_context(form))
                except (KeyError, ValueError) as exc:
                    form.add_error(None, str(exc))
                    return render(request, "library/photo_circulation.html", _circulation_context(form))

            copy = form.cleaned_data.get("manual_copy")
            if copy is None:
                try:
                    copy = _copy_from_photo(form.cleaned_data["book_photo"], action)
                except ValueError as exc:
                    form.add_error("book_photo", str(exc))
                    if basket_payload:
                        return _checkout_scan(request, form, basket_payload)
                    return render(request, "library/photo_circulation.html", _circulation_context(form))

            if action == PhotoCirculationForm.Action.CHECKOUT and copy.status != Copy.Status.AVAILABLE:
                form.add_error("book_photo", "This copy is not available for check out.")
                if basket_payload:
                    return _checkout_scan(request, form, basket_payload)
                return render(request, "library/photo_circulation.html", _circulation_context(form))
            loan = copy.active_loan
            if action == PhotoCirculationForm.Action.CHECKIN:
                if loan is None:
                    form.add_error("book_photo", "This copy has no active loan to check in.")
                    return render(request, "library/photo_circulation.html", _circulation_context(form))
                if loan.borrower_id != borrower.id:
                    form.add_error("borrower", "This copy is checked out to a different borrower.")
                    return render(request, "library/photo_circulation.html", _circulation_context(form))

            due_date = form.cleaned_data.get("due_date") or default_form_due_date()
            if action == PhotoCirculationForm.Action.CHECKOUT:
                copy_ids = list(basket_payload["copy_ids"]) if basket_payload else []
                if str(copy.id) in copy_ids:
                    form.add_error("manual_copy" if form.cleaned_data.get("manual_copy") else "book_photo", "This book is already in the checkout basket.")
                    return _checkout_scan(request, form, basket_payload)
                copy_ids.append(str(copy.id))
                payload = {
                    "copy_ids": copy_ids,
                    "borrower_id": str(borrower.id),
                    "action": action,
                    "due_date": basket_payload["due_date"] if basket_payload else due_date.isoformat(),
                }
                return _checkout_confirmation(request, form, payload)

            token = signing.dumps(
                {
                    "copy_ids": [str(copy.id)],
                    "borrower_id": str(borrower.id),
                    "action": action,
                    "due_date": "",
                },
                salt=CIRCULATION_SALT,
            )
            return render(
                request,
                "library/photo_circulation.html",
                _circulation_context(
                    form,
                    confirmation=True,
                    confirmation_token=token,
                    copy=copy,
                    borrower=borrower,
                    action=action,
                    due_date=due_date,
                ),
            )
    else:
        form = PhotoCirculationForm(
            initial={
                "borrower": request.GET.get("borrower", ""),
                "action": request.GET.get("action", PhotoCirculationForm.Action.CHECKOUT),
            }
        )
    return render(request, "library/photo_circulation.html", _circulation_context(form))


@login_required
def checkout(request):
    if request.method == "POST":
        form = CheckoutForm(request.POST)
        if form.is_valid():
            try:
                borrower_id = _uuid_from_code(form.cleaned_data["borrower_code"], "BORROWER")
                copy_id = _uuid_from_code(form.cleaned_data["copy_code"], "COPY")
            except ValueError as exc:
                form.add_error(None, str(exc))
            else:
                borrower = get_object_or_404(Borrower, pk=borrower_id, active=True)
                copy = get_object_or_404(Copy.objects.select_related("book"), pk=copy_id)
                if copy.status != Copy.Status.AVAILABLE:
                    form.add_error("copy_code", "This copy is not available.")
                else:
                    Loan.objects.create(copy=copy, borrower=borrower, due_date=form.cleaned_data["due_date"])
                    copy.status = Copy.Status.CHECKED_OUT
                    copy.save(update_fields=["status"])
                    messages.success(request, f"Checked out {copy.book.title} to {borrower.full_name}.")
                    return redirect("dashboard")
    else:
        form = CheckoutForm()
    return render(request, "library/checkout.html", {"form": form})


@login_required
def return_copy(request):
    if request.method == "POST":
        form = ReturnForm(request.POST)
        if form.is_valid():
            try:
                copy_id = _uuid_from_code(form.cleaned_data["copy_code"], "COPY")
            except ValueError as exc:
                form.add_error(None, str(exc))
            else:
                copy = get_object_or_404(Copy.objects.select_related("book"), pk=copy_id)
                loan = copy.loans.filter(return_date__isnull=True).first()
                if loan is None:
                    form.add_error("copy_code", "This copy has no active loan.")
                else:
                    loan.return_date = timezone.localdate()
                    loan.save(update_fields=["return_date"])
                    copy.status = Copy.Status.AVAILABLE
                    copy.save(update_fields=["status"])
                    messages.success(request, f"Returned {copy.book.title}.")
                    return redirect(copy)
    else:
        form = ReturnForm()
    return render(request, "library/return.html", {"form": form})


@login_required
def label(request, kind, pk):
    if kind == "copy":
        obj = get_object_or_404(Copy.objects.select_related("book"), pk=pk)
        title = f"{obj.book.title} #{obj.copy_number}"
        payload = obj.qr_code
    elif kind == "borrower":
        obj = get_object_or_404(Borrower, pk=pk)
        title = obj.full_name
        payload = obj.qr_code
    else:
        raise Http404("Unknown label type")
    return render(request, "library/label.html", {"title": title, "payload": payload, "qr_svg": mark_safe(svg_qr(payload))})


@login_required
def import_books(request):
    if request.method == "POST":
        form = CsvImportForm(request.POST, request.FILES)
        if form.is_valid():
            try:
                wrapper = TextIOWrapper(form.cleaned_data["csv_file"].file, encoding="utf-8-sig")
                reader = csv.DictReader(wrapper)
                if not reader.fieldnames or "Title" not in reader.fieldnames:
                    raise ValueError("CSV must include a Title column.")
                result = import_catalog_rows(reader)
            except (UnicodeDecodeError, csv.Error, ValueError) as exc:
                form.add_error("csv_file", str(exc))
            else:
                physical_label = "physical book" if result.copies_created == 1 else "physical books"
                title_label = "title" if result.titles_created == 1 else "titles"
                messages.success(
                    request,
                    f"Catalog import complete: {result.copies_created} {physical_label}, "
                    f"{result.titles_created} {title_label} created, {result.titles_matched} duplicate copies matched, "
                    f"{result.placeholder_titles} unidentified title, {result.existing_rows_skipped} existing rows skipped.",
                )
                return redirect("book_list")
    else:
        form = CsvImportForm()
    return render(request, "library/import_books.html", {"form": form})


@login_required
def export_books_csv(request):
    output = StringIO()
    writer = csv.writer(output)
    writer.writerow(
        [
            "Source photo", "Photo position", "Title", "Subtitle", "Contributors", "ISBN", "Publisher",
            "Publication year", "Language", "Pages", "Format", "Category", "Topics", "Description",
            "Suggested Montessori level", "Suggested age range", "Suggested reading level",
            "Identification confidence", "Review notes", "Bibliographic source URL",
        ]
    )
    for copy in Copy.objects.select_related("book").order_by("book__title", "copy_number"):
        book = copy.book
        writer.writerow(
            [
                copy.source_photo, copy.source_position, book.title, book.subtitle, book.authors,
                book.isbn13 or book.isbn10, book.publisher, book.publication_year or "", book.language,
                book.page_count or "", book.format, book.category, book.topics, book.description,
                book.montessori_levels, book.suggested_age_range, book.suggested_reading_level,
                book.identification_confidence, book.review_notes, book.bibliographic_source_url,
            ]
        )
    response = HttpResponse(output.getvalue(), content_type="text/csv")
    response["Content-Disposition"] = 'attachment; filename="library-books.csv"'
    return response


@staff_member_required
def backup_sqlite(request):
    database = settings.DATABASES["default"]
    if database["ENGINE"] != "django.db.backends.sqlite3":
        raise Http404("SQLite backup is only available when using SQLite.")
    path = database["NAME"]
    return FileResponse(open(path, "rb"), as_attachment=True, filename="library-db.sqlite3")


@staff_member_required
def school_settings(request):
    profile = SchoolProfile.current()
    if request.method == "POST":
        form = SchoolProfileForm(request.POST, request.FILES, instance=profile)
        if form.is_valid():
            profile = form.save(commit=False)
            profile.setup_completed = True
            profile.save()
            messages.success(request, "School settings saved.")
            return redirect("school_settings")
    else:
        form = SchoolProfileForm(instance=profile)
    return render(request, "library/school_settings.html", {"form": form})


@staff_member_required
def import_borrowers(request):
    if request.method == "POST":
        form = BorrowerCsvImportForm(request.POST, request.FILES)
        if form.is_valid():
            wrapper = TextIOWrapper(form.cleaned_data["csv_file"].file, encoding="utf-8-sig")
            reader = csv.DictReader(wrapper)
            required = {"Username", "First name", "Last name"}
            if not required.issubset(set(reader.fieldnames or [])):
                form.add_error("csv_file", "CSV must include Username, First name, and Last name columns.")
            else:
                created = 0
                updated = 0
                skipped = 0
                for row in reader:
                    username = (row.get("Username") or "").strip()
                    first_name = (row.get("First name") or "").strip()
                    last_name = (row.get("Last name") or "").strip()
                    if not username or not (first_name or last_name):
                        skipped += 1
                        continue
                    active_value = (row.get("Active") or "yes").strip().lower()
                    _borrower, was_created = Borrower.objects.update_or_create(
                        username=username,
                        defaults={
                            "first_name": first_name,
                            "last_name": last_name,
                            "class_name": (row.get("Class") or "").strip(),
                            "email": (row.get("Email") or "").strip(),
                            "active": active_value not in {"0", "false", "no", "inactive"},
                        },
                    )
                    created += int(was_created)
                    updated += int(not was_created)
                messages.success(request, f"Borrowers imported: {created} created, {updated} updated, {skipped} skipped.")
                return redirect("borrower_list")
    else:
        form = BorrowerCsvImportForm()
    return render(request, "library/import_borrowers.html", {"form": form})


@login_required
def overdue_loans(request):
    sort = request.GET.get("sort", "due")
    direction = request.GET.get("direction", "asc")
    sort_fields = {
        "due": ("due_date",),
        "book": ("copy__book__title",),
        "copy": ("copy__copy_number",),
        "borrower": ("borrower__last_name", "borrower__first_name"),
        "username": ("borrower__username",),
        "class": ("borrower__class_name",),
    }
    if sort not in sort_fields:
        sort = "due"
    if direction not in {"asc", "desc"}:
        direction = "asc"
    prefix = "-" if direction == "desc" else ""
    order_by = [f"{prefix}{field}" for field in sort_fields[sort]]
    if sort != "due":
        order_by.append("due_date")
    loans = Loan.objects.filter(
        return_date__isnull=True,
        due_date__lt=timezone.localdate(),
    ).select_related("copy__book", "borrower").order_by(*order_by)
    sort_headers = [
        {
            "key": key,
            "label": label,
            "active": sort == key,
            "direction": direction if sort == key else "",
            "next_direction": "desc" if sort == key and direction == "asc" else "asc",
        }
        for key, label in (
            ("due", "Due"),
            ("book", "Book"),
            ("copy", "Copy"),
            ("borrower", "Borrower"),
            ("username", "Username"),
            ("class", "Class"),
        )
    ]
    return render(request, "library/overdue_loans.html", {"loans": loans, "sort_headers": sort_headers})


@login_required
def overdue_loans_csv(request):
    output = StringIO()
    writer = csv.writer(output)
    writer.writerow(["Book", "Copy", "Borrower username", "Borrower", "Class", "Checked out", "Due date"])
    loans = Loan.objects.filter(
        return_date__isnull=True,
        due_date__lt=timezone.localdate(),
    ).select_related("copy__book", "borrower").order_by("due_date")
    for loan in loans:
        writer.writerow(
            [
                loan.copy.book.title,
                loan.copy.copy_number,
                loan.borrower.username or "",
                loan.borrower.full_name,
                loan.borrower.class_name,
                loan.checkout_date,
                loan.due_date,
            ]
        )
    response = HttpResponse(output.getvalue(), content_type="text/csv")
    response["Content-Disposition"] = 'attachment; filename="overdue-loans.csv"'
    return response
