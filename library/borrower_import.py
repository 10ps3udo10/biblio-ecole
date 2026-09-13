from django.core.exceptions import ValidationError
from django.db import transaction

from .models import Borrower, EmployeePosition, SchoolClass


@transaction.atomic
def import_borrower_rows(rows):
    created = updated = skipped = 0
    for line, row in enumerate(rows, start=2):
        if None in row:
            raise ValueError(f"Row {line}: Too many columns. Check CSV quoting.")
        text = lambda key: (row.get(key) or "").strip()
        identifier = text("Borrower ID")
        if not identifier or not (text("First name") or text("Last name")):
            skipped += 1
            continue
        borrower = Borrower.objects.filter(username=identifier).first()
        new = borrower is None
        if new:
            borrower = Borrower(username=identifier)
        role = text("School role").lower() or borrower.school_role
        if role not in Borrower.SchoolRole.values:
            raise ValueError(f"Row {line}: School role must be Employee or Student.")
        position = borrower.position
        if "Position" in row:
            name = text("Position")
            position = EmployeePosition.objects.filter(name__iexact=name).first() if name else None
            if name and position is None:
                raise ValueError(f"Row {line}: Unknown position '{name}'. Add it in Settings first.")
            if position and not position.active and borrower.position_id != position.pk:
                raise ValueError(f"Row {line}: Position '{name}' is inactive.")
        if role == Borrower.SchoolRole.STUDENT:
            if text("Position"):
                raise ValueError(f"Row {line}: Only employees can have a position.")
            position = None
        borrower.school_role = role
        borrower.position = position
        borrower.first_name = text("First name")
        borrower.last_name = text("Last name")
        if role == Borrower.SchoolRole.EMPLOYEE:
            borrower.school_class = None
        elif "Class" in row:
            name = text("Class")
            school_class = SchoolClass.objects.filter(name__iexact=name).first() if name else None
            if name and school_class is None:
                raise ValueError(f"Row {line}: Unknown class '{name}'. Add it in Settings first.")
            if school_class and not school_class.active and borrower.school_class_id != school_class.pk:
                raise ValueError(f"Row {line}: Class '{name}' is inactive.")
            borrower.school_class = school_class
        if "Email" in row:
            borrower.email = text("Email")
        if "Active" in row:
            active = text("Active").lower()
            if active not in {"", "yes", "true", "1", "no", "false", "0", "inactive"}:
                raise ValueError(f"Row {line}: Active must be Yes or No.")
            borrower.active = active not in {"no", "false", "0", "inactive"}
        if borrower.staff_account_id:
            account = borrower.staff_account
            borrower.first_name, borrower.last_name, borrower.email = account.first_name, account.last_name, account.email
        try:
            borrower.full_clean(exclude=["first_name", "last_name", "email"] if borrower.staff_account_id else None)
        except ValidationError as exc:
            raise ValueError(f"Row {line}: {'; '.join(exc.messages)}") from exc
        borrower.save()
        created += int(new)
        updated += int(not new)
    return created, updated, skipped
