from dataclasses import dataclass

from django.core.exceptions import ValidationError
from django.db import transaction

from .models import Borrower, EmployeePosition, SchoolClass, SchoolYear


@dataclass
class BorrowerImportPreview:
    rows: list
    duplicates: list
    skipped: int = 0


@dataclass
class BorrowerImportResult:
    created: int
    duplicates: list
    skipped: int


def _normalized(value):
    return " ".join((value or "").split()).casefold()


def preview_borrower_rows(rows):
    prepared = []
    duplicates = []
    skipped = 0
    names_in_file = set()
    school_ids_in_file = set()
    existing = Borrower.objects.select_related("school_class", "position")

    for line, row in enumerate(rows, start=2):
        if None in row:
            raise ValueError(f"Row {line}: Too many columns. Check CSV quoting.")
        text = lambda key: " ".join((row.get(key) or "").split())
        if not any(text(key) for key in row):
            skipped += 1
            continue

        first_name, last_name = text("First name"), text("Last name")
        if not first_name or not last_name:
            raise ValueError(f"Row {line}: First name and Last name are required.")
        role = text("School role").lower() or Borrower.SchoolRole.STUDENT
        if role not in Borrower.SchoolRole.values:
            raise ValueError(f"Row {line}: School role must be Employee or Student.")

        position = None
        position_name = text("Position")
        class_name = text("Class")
        if role == Borrower.SchoolRole.STUDENT:
            if position_name:
                raise ValueError(f"Row {line}: Only employees can have a position.")
            school_class = SchoolClass.objects.filter(school_year=SchoolYear.current(), name__iexact=class_name).first() if class_name else None
            if class_name and school_class is None:
                raise ValueError(f"Row {line}: Unknown class '{class_name}'. Add it in Settings first.")
            if school_class and not school_class.active:
                raise ValueError(f"Row {line}: Class '{class_name}' is inactive.")
        else:
            if class_name:
                raise ValueError(f"Row {line}: Only students can have a class.")
            school_class = None
            position = EmployeePosition.objects.filter(name__iexact=position_name).first() if position_name else None
            if position_name and position is None:
                raise ValueError(f"Row {line}: Unknown position '{position_name}'. Add it in Settings first.")
            if position and not position.active:
                raise ValueError(f"Row {line}: Position '{position_name}' is inactive.")

        active_text = text("Active").lower()
        if active_text not in {"", "yes", "true", "1", "no", "false", "0", "inactive"}:
            raise ValueError(f"Row {line}: Active must be Yes or No.")
        school_id = text("School ID") or None
        name_key = (_normalized(first_name), _normalized(last_name))
        school_id_key = _normalized(school_id)
        match = existing.filter(first_name__iexact=first_name, last_name__iexact=last_name).first()
        reason = ""
        school_id_match = existing.filter(school_id__iexact=school_id).first() if school_id else None
        if school_id_match:
            reason = f"School ID {school_id} is already assigned to {school_id_match.full_name}."
        elif school_id_key and school_id_key in school_ids_in_file:
            reason = f"School ID {school_id} appears more than once in this file."
        elif match:
            reason = f"A borrower named {match.full_name} already exists ({match.borrower_id})."
        elif name_key in names_in_file:
            reason = "This name appears more than once in this file."

        candidate = {
            "line": line,
            "first_name": first_name,
            "last_name": last_name,
            "school_role": role,
            "position": position.name if position else "",
            "school_class": school_class.name if school_class else "",
            "email": text("Email"),
            "school_id": school_id or "",
            "active": active_text not in {"no", "false", "0", "inactive"},
        }
        if reason:
            duplicates.append({**candidate, "reason": reason})
        else:
            prepared.append(candidate)
        names_in_file.add(name_key)
        if school_id_key:
            school_ids_in_file.add(school_id_key)

    return BorrowerImportPreview(prepared, duplicates, skipped)


@transaction.atomic
def import_borrower_rows(rows):
    preview = preview_borrower_rows(rows)
    created = 0
    for row in preview.rows:
        borrower = Borrower(
            school_id=row.get("school_id") or None,
            first_name=row["first_name"],
            last_name=row["last_name"],
            school_role=row["school_role"],
            position=EmployeePosition.objects.filter(name__iexact=row.get("position", "")).first(),
            school_class=SchoolClass.objects.filter(school_year=SchoolYear.current(), name__iexact=row.get("school_class", "")).first(),
            email=row.get("email", ""),
            active=row.get("active", True),
        )
        try:
            borrower.full_clean(exclude=["borrower_id"])
        except ValidationError as exc:
            raise ValueError(f"Row {row['line']}: {'; '.join(exc.messages)}") from exc
        borrower.save()
        created += 1
    return BorrowerImportResult(created, preview.duplicates, preview.skipped)
