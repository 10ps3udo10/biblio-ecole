from dataclasses import dataclass

from django.db import transaction
from django.db.models import Max, Q

from .models import Book, Copy
from .photo_intake import clean_isbn, is_valid_isbn


@dataclass
class CatalogImportResult:
    rows_seen: int = 0
    titles_created: int = 0
    titles_matched: int = 0
    copies_created: int = 0
    existing_rows_skipped: int = 0
    placeholder_titles: int = 0
    invalid_isbns: int = 0


def _text(row, name):
    return str(row.get(name) or "").strip()


def _positive_integer(value):
    value = str(value or "").strip()
    return int(value) if value.isdigit() and int(value) > 0 else None


def _book_values(row, title, isbn):
    confidence = _text(row, "Identification confidence").lower()
    valid_confidences = {choice for choice, _label in Book.IdentificationConfidence.choices}
    return {
        "title": title,
        "subtitle": _text(row, "Subtitle"),
        "authors": _text(row, "Contributors"),
        "isbn13": isbn if len(isbn) == 13 else "",
        "isbn10": isbn if len(isbn) == 10 else "",
        "publisher": _text(row, "Publisher"),
        "publication_year": _positive_integer(_text(row, "Publication year")),
        "language": _text(row, "Language"),
        "page_count": _positive_integer(_text(row, "Pages")),
        "format": _text(row, "Format"),
        "category": _text(row, "Category"),
        "topics": _text(row, "Topics"),
        "description": _text(row, "Description"),
        "montessori_levels": _text(row, "Suggested Montessori level"),
        "suggested_age_range": _text(row, "Suggested age range"),
        "suggested_reading_level": _text(row, "Suggested reading level"),
        "identification_confidence": confidence if confidence in valid_confidences else "",
        "review_notes": _text(row, "Review notes"),
        "bibliographic_source_url": _text(row, "Bibliographic source URL"),
    }


def _find_book(values, isbn):
    if isbn:
        match = Book.objects.filter(Q(isbn13=isbn) | Q(isbn10=isbn)).first()
        if match:
            return match
    candidates = Book.objects.all()
    if isbn:
        # Metadata alone cannot establish that two different ISBNs are one edition.
        candidates = candidates.filter(isbn10="", isbn13="")
    return candidates.filter(
        title__iexact=values["title"],
        subtitle=values["subtitle"],
        authors=values["authors"],
        publisher=values["publisher"],
        language=values["language"],
    ).first()


def _enrich_blank_book_fields(book, values):
    changed = []
    for field, value in values.items():
        if field == "title" or value in ("", None):
            continue
        if getattr(book, field) in ("", None):
            setattr(book, field, value)
            changed.append(field)
    return changed


@transaction.atomic
def import_catalog_rows(rows):
    result = CatalogImportResult()
    for row in rows:
        if not any(str(value or "").strip() for value in row.values()):
            continue
        result.rows_seen += 1
        source_photo = _text(row, "Source photo")
        source_position = _text(row, "Photo position")
        if source_photo and source_position and Copy.objects.filter(
            source_photo=source_photo,
            source_position=source_position,
        ).exists():
            result.existing_rows_skipped += 1
            continue

        title = _text(row, "Title")
        placeholder = not title
        if placeholder:
            source = ", ".join(value for value in (source_photo, source_position) if value)
            title = f"Unidentified book ({source or result.rows_seen})"
            result.placeholder_titles += 1

        raw_isbn = _text(row, "ISBN")
        isbn = clean_isbn(raw_isbn)
        if raw_isbn and not is_valid_isbn(isbn):
            isbn = ""
            result.invalid_isbns += 1
        values = _book_values(row, title, isbn)
        needs_information = bool(
            placeholder
            or not isbn
            or not values["authors"]
            or not values["language"]
            or values["review_notes"]
        )

        book = _find_book(values, isbn)
        if book is None:
            book = Book.objects.create(**values, needs_information=needs_information)
            result.titles_created += 1
        else:
            changed = _enrich_blank_book_fields(book, values)
            if needs_information and not book.needs_information:
                book.needs_information = True
                changed.append("needs_information")
            if changed:
                book.save(update_fields=[*changed, "updated_at"])
            result.titles_matched += 1

        next_copy = (book.copies.aggregate(highest=Max("copy_number"))["highest"] or 0) + 1
        Copy.objects.create(
            book=book,
            copy_number=next_copy,
            source_photo=source_photo,
            source_position=source_position,
        )
        result.copies_created += 1
    return result
