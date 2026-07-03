import csv
import uuid
from io import StringIO, TextIOWrapper

from django.conf import settings
from django.contrib import messages
from django.contrib.auth.decorators import login_required
from django.db.models import Count, Max, Q
from django.http import FileResponse, Http404, HttpResponse
from django.shortcuts import get_object_or_404, redirect, render
from django.utils import timezone
from django.utils.safestring import mark_safe

from .forms import BookForm, BorrowerForm, CheckoutForm, CopyForm, CsvImportForm, PhotoCirculationForm, PhotoIntakeForm, ReturnForm, default_form_due_date
from .models import Book, Borrower, Copy, Loan
from .photo_intake import MetadataLookupError, clean_isbn, decode_barcodes_from_image, decode_isbn_from_image, lookup_book_by_isbn
from .qr import svg_qr


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


@login_required
def dashboard(request):
    active_loans = Loan.objects.filter(return_date__isnull=True)
    context = {
        "total_books": Book.objects.count(),
        "total_copies": Copy.objects.count(),
        "borrowed_books": active_loans.count(),
        "overdue_books": active_loans.filter(due_date__lt=timezone.localdate()).count(),
        "recent_books": Book.objects.order_by("-created_at")[:6],
        "recent_loans": Loan.objects.select_related("copy__book", "borrower").order_by("-checkout_date")[:8],
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
    return render(request, "library/book_detail.html", {"book": book, "loans": loans})


@login_required
def book_create(request):
    if request.method == "POST":
        form = BookForm(request.POST, request.FILES)
        if form.is_valid():
            book = form.save()
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
            book = Book.objects.create(
                title=title,
                subtitle=metadata.get("subtitle", ""),
                authors=authors,
                isbn10=metadata.get("isbn10") or (isbn if len(isbn) == 10 else ""),
                isbn13=metadata.get("isbn13") or (isbn if len(isbn) == 13 else ""),
                publisher=metadata.get("publisher", ""),
                publication_year=metadata.get("publication_year"),
                language=metadata.get("language", ""),
                description=metadata.get("description", ""),
                cover_image=photo,
            )
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
    return render(request, "library/copy_detail.html", {"copy": copy, "loans": loans})


@login_required
def borrower_list(request):
    query = request.GET.get("q", "").strip()
    borrowers = Borrower.objects.all()
    if query:
        borrowers = borrowers.filter(
            Q(username__icontains=query)
            | Q(first_name__icontains=query)
            | Q(last_name__icontains=query)
            | Q(class_name__icontains=query)
            | Q(email__icontains=query)
        )
    return render(request, "library/borrower_list.html", {"borrowers": borrowers, "query": query})


@login_required
def borrower_detail(request, pk):
    borrower = get_object_or_404(Borrower, pk=pk)
    active_loans = borrower.loans.filter(return_date__isnull=True).select_related("copy__book")
    loan_history = borrower.loans.select_related("copy__book")[:30]
    return render(
        request,
        "library/borrower_detail.html",
        {"borrower": borrower, "active_loans": active_loans, "loan_history": loan_history},
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
def photo_circulation(request):
    if request.method == "POST":
        form = PhotoCirculationForm(request.POST, request.FILES)
        if form.is_valid():
            action = form.cleaned_data["action"]
            borrower = form.cleaned_data["borrower"]
            try:
                copy = _copy_from_photo(form.cleaned_data["book_photo"], action)
            except ValueError as exc:
                form.add_error("book_photo", str(exc))
                return render(request, "library/photo_circulation.html", {"form": form})

            if action == PhotoCirculationForm.Action.CHECKOUT:
                if copy.status != Copy.Status.AVAILABLE:
                    form.add_error("book_photo", "This copy is not available for check out.")
                    return render(request, "library/photo_circulation.html", {"form": form})
                Loan.objects.create(copy=copy, borrower=borrower, due_date=form.cleaned_data.get("due_date") or default_form_due_date())
                copy.status = Copy.Status.CHECKED_OUT
                copy.save(update_fields=["status"])
                messages.success(request, f"Checked out {copy.book.title} to {borrower.full_name}.")
                return redirect(copy)

            loan = copy.loans.filter(return_date__isnull=True).select_related("borrower").first()
            if loan is None:
                form.add_error("book_photo", "This copy has no active loan to check in.")
                return render(request, "library/photo_circulation.html", {"form": form})
            if loan.borrower_id != borrower.id:
                form.add_error("borrower", "This copy is checked out to a different borrower.")
                return render(request, "library/photo_circulation.html", {"form": form})
            loan.return_date = timezone.localdate()
            loan.save(update_fields=["return_date"])
            copy.status = Copy.Status.AVAILABLE
            copy.save(update_fields=["status"])
            messages.success(request, f"Checked in {copy.book.title} from {borrower.full_name}.")
            return redirect(copy)
    else:
        form = PhotoCirculationForm()
    return render(request, "library/photo_circulation.html", {"form": form})


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


@login_required
def backup_sqlite(request):
    database = settings.DATABASES["default"]
    if database["ENGINE"] != "django.db.backends.sqlite3":
        raise Http404("SQLite backup is only available when using SQLite.")
    path = database["NAME"]
    return FileResponse(open(path, "rb"), as_attachment=True, filename="library-db.sqlite3")
