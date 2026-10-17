"""Passage d'une année scolaire à la suivante.

Rien n'est supprimé : les anciennes classes sont désactivées, les élèves qui
partent sont archivés et les emprunts en cours restent ouverts et signalés.
"""

from datetime import date

from django.db import transaction
from django.utils import timezone

from .models import Borrower, Loan, SchoolClass, SchoolYear

LEAVES_SCHOOL = "__leaves__"


def next_year_defaults():
    first_year = SchoolYear.current().start_date.year + 1
    return f"{first_year}-{first_year + 1}", date(first_year, 9, 1), date(first_year + 1, 8, 31)


def parse_class_names(text):
    names, seen = [], set()
    for line in text.splitlines():
        name = line.strip()
        if name and name.casefold() not in seen:
            seen.add(name.casefold())
            names.append(name)
    return names


def students_to_place():
    return (
        Borrower.objects.filter(active=True, school_role=Borrower.SchoolRole.STUDENT, school_class__school_year=SchoolYear.current())
        .select_related("school_class")
        .order_by("school_class__name", "last_name", "first_name")
    )


def open_loans_from_previous_years():
    return (
        Loan.objects.filter(return_date__isnull=True)
        .exclude(school_year=SchoolYear.current())
        .select_related("copy__book", "borrower", "school_class", "school_year")
        .order_by("checkout_date")
    )


def start_new_school_year(*, name, start_date, end_date, class_names, placements):
    """Create the new year and its classes, then place or archive each student.

    placements maps a borrower pk (str) to a new class name, LEAVES_SCHOOL, or "" (no class yet).
    """
    name = name.strip()
    if not name:
        raise ValueError("Le nom de l'année est obligatoire.")
    if SchoolYear.objects.filter(name__iexact=name).exists():
        raise ValueError(f"L'année {name} existe déjà.")
    if not class_names:
        raise ValueError("Ajoutez au moins une classe pour la nouvelle année.")
    if start_date >= end_date:
        raise ValueError("La date de fin doit suivre la date de début.")
    by_name = {class_name.casefold(): class_name for class_name in class_names}
    for destination in placements.values():
        if destination not in ("", LEAVES_SCHOOL) and destination.casefold() not in by_name:
            raise ValueError(f"Classe inconnue : {destination}.")

    today = timezone.localdate()
    with transaction.atomic():
        previous = SchoolYear.current()
        students = list(students_to_place().select_for_update())
        SchoolYear.objects.filter(pk=previous.pk).update(is_current=False)
        new_year = SchoolYear.objects.create(name=name, start_date=start_date, end_date=end_date, is_current=True)
        new_classes = {
            class_name.casefold(): SchoolClass.objects.create(name=class_name, school_year=new_year) for class_name in class_names
        }
        SchoolClass.objects.filter(school_year=previous).update(active=False)

        moved = archived = unplaced = 0
        for student in students:
            destination = placements.get(str(student.pk), "")
            if destination == LEAVES_SCHOOL:
                student.active = False
                student.archived_on = today
                student.save(update_fields=["active", "archived_on"])
                archived += 1
            elif destination:
                student.school_class = new_classes[destination.casefold()]
                student.save(update_fields=["school_class"])
                moved += 1
            else:
                student.school_class = None
                student.save(update_fields=["school_class"])
                unplaced += 1

    summary = {
        "moved": moved,
        "archived": archived,
        "unplaced": unplaced,
        "open_loans": open_loans_from_previous_years().count(),
    }
    return new_year, summary
