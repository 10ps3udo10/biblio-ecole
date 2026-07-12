import csv
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
from django.utils.safestring import mark_safe
from django.views.decorators.http import require_GET, require_POST

from .forms import (
    BookForm,
    BorrowerCsvImportForm,
    BorrowerForm,
    CheckoutForm,
    CopyForm,
    CsvImportForm,
    PhotoCirculationForm,
    PhotoIntakeForm,
    ReturnForm,
    SchoolProfileForm,
    default_form_due_date,
)
from .models import Book, Borrower, Copy, Loan, SchoolProfile
from .photo_intake import MetadataLookupError, clean_isbn, decode_barcodes_from_image, decode_isbn_from_image, download_cover_by_isbn, is_valid_isbn, lookup_book_by_isbn
from .qr import svg_qr


CIRCULATION_SALT = "shelf-school-circulation"


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


def _circulation_context(form, **extra):
    borrower_loans = {}
    active_loans = Loan.objects.filter(return_date__isnull=True).select_related("copy__book", "borrower").order_by("copy__book__title")
    for loan in active_loans:
        borrower_loans.setdefault(str(loan.borrower_id), []).append(
            {
                "copy_id": str(loan.copy_id),
                "title": loan.copy.book.title,
                "copy_number": loan.copy.copy_number,
                "due_date": loan.due_date.isoformat(),
            }
        )
    context = {
        "form": form,
        "has_borrowers": Borrower.objects.filter(active=True).exists(),
        "borrower_loans": borrower_loans,
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
            | Q(copies__shelf_location__icontains=query)
            | Q(copies__status__icontains=query)
        ).distinct()
    return render(request, "library/book_list.html", {"books": books, "query": query})


@login_required
def book_detail(request, pk):
    book = get_object_or_404(Book, pk=pk)
    loans = Loan.objects.filter(copy__book=book).select_related("copy", "borrower")[:20]
    copies = list(book.copies.all())
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
    return render(request, "library/book_form.html", {"form": form, "title": "Add book"})


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
    return render(
        request,
        "library/borrower_list.html",
        {
            "borrowers": borrowers,
            "query": query,
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


def photo_circulation(request):
    if request.method == "POST":
        confirmation_token = request.POST.get("confirmation_token")
        if confirmation_token:
            try:
                payload = signing.loads(confirmation_token, salt=CIRCULATION_SALT, max_age=600)
                borrower = Borrower.objects.get(pk=payload["borrower_id"], active=True)
                action = payload["action"]
                due_date = payload.get("due_date") or None
                with transaction.atomic():
                    copy_ids = payload.get("copy_ids") or []
                    if copy_ids:
                        copies = list(Copy.objects.select_for_update().select_related("book").filter(pk__in=copy_ids))
                        if len(copies) != len(copy_ids):
                            raise ValueError("One of the selected books is no longer available.")
                        for selected_copy in copies:
                            _perform_circulation(selected_copy, borrower, action)
                        copy = copies[0]
                        success_message = f"Returned {len(copies)} book{'s' if len(copies) != 1 else ''} for {borrower.full_name}."
                    else:
                        copy = Copy.objects.select_for_update().select_related("book").get(pk=payload["copy_id"])
                        success_message = _perform_circulation(copy, borrower, action, due_date)
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
            copy = form.cleaned_data.get("manual_copy")
            if copy is None:
                try:
                    copy = _copy_from_photo(form.cleaned_data["book_photo"], action)
                except ValueError as exc:
                    form.add_error("book_photo", str(exc))
                    return render(request, "library/photo_circulation.html", _circulation_context(form))

            if action == PhotoCirculationForm.Action.CHECKOUT and copy.status != Copy.Status.AVAILABLE:
                form.add_error("book_photo", "This copy is not available for check out.")
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
            token = signing.dumps(
                {
                    "copy_id": str(copy.id),
                    "borrower_id": str(borrower.id),
                    "action": action,
                    "due_date": due_date.isoformat() if action == PhotoCirculationForm.Action.CHECKOUT else "",
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
            wrapper = TextIOWrapper(form.cleaned_data["csv_file"].file, encoding="utf-8-sig")
            imported = 0
            for row in csv.DictReader(wrapper):
                title = (row.get("Title") or "").strip()
                if not title:
                    continue
                copies_count = int((row.get("Copies") or "1").strip() or "1")
                isbn = (row.get("ISBN") or "").replace("-", "").strip()
                book = None
                if isbn:
                    book = Book.objects.filter(Q(isbn13=isbn) | Q(isbn10=isbn)).first()
                if book is None:
                    book = Book.objects.create(
                        title=title,
                        authors=(row.get("Author") or "").strip(),
                        isbn13=isbn if len(isbn) == 13 else "",
                        isbn10=isbn if len(isbn) == 10 else "",
                        publisher=(row.get("Publisher") or "").strip(),
                        publication_year=int(row["Year"]) if (row.get("Year") or "").strip().isdigit() else None,
                        language=(row.get("Language") or "").strip(),
                    )
                    imported += 1
                for _ in range(max(copies_count, 1)):
                    Copy.objects.create(
                        book=book,
                        copy_number=_next_copy_number(book),
                        shelf_location=(row.get("Shelf") or "").strip(),
                    )
            messages.success(request, f"Imported {imported} new books.")
            return redirect("book_list")
    else:
        form = CsvImportForm()
    return render(request, "library/import_books.html", {"form": form})


@login_required
def export_books_csv(request):
    output = StringIO()
    writer = csv.writer(output)
    writer.writerow(["Title", "Author", "ISBN", "Publisher", "Year", "Language", "Copies", "Shelf"])
    for book in Book.objects.prefetch_related("copies"):
        shelves = ", ".join(sorted({copy.shelf_location for copy in book.copies.all() if copy.shelf_location}))
        writer.writerow(
            [
                book.title,
                book.authors,
                book.isbn13 or book.isbn10,
                book.publisher,
                book.publication_year or "",
                book.language,
                book.copies.count(),
                shelves,
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
    loans = Loan.objects.filter(
        return_date__isnull=True,
        due_date__lt=timezone.localdate(),
    ).select_related("copy__book", "borrower").order_by("due_date")
    return render(request, "library/overdue_loans.html", {"loans": loans})


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
