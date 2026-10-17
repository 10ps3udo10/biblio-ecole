from datetime import date

import pytest
from django.db import IntegrityError, transaction

from library.models import Book, Borrower, Copy, Loan, SchoolClass, SchoolYear, school_year_bounds


def test_school_year_bounds_switch_on_september_first():
    assert school_year_bounds(date(2026, 8, 31)) == ("2025-2026", date(2025, 9, 1), date(2026, 8, 31))
    assert school_year_bounds(date(2026, 9, 1)) == ("2026-2027", date(2026, 9, 1), date(2027, 8, 31))


@pytest.mark.django_db
def test_current_school_year_is_created_once():
    SchoolClass.objects.all().delete()
    SchoolYear.objects.all().delete()

    first = SchoolYear.current()
    second = SchoolYear.current()

    assert first == second
    assert first.is_current
    assert SchoolYear.objects.count() == 1


@pytest.mark.django_db
def test_only_one_school_year_can_be_current():
    SchoolYear.current()

    with pytest.raises(IntegrityError), transaction.atomic():
        SchoolYear.objects.create(name="2099-2100", start_date=date(2099, 9, 1), end_date=date(2100, 8, 31), is_current=True)


@pytest.mark.django_db
def test_new_class_belongs_to_current_year_and_names_repeat_across_years():
    previous = SchoolYear.objects.create(name="2025-2026", start_date=date(2025, 9, 1), end_date=date(2026, 8, 31))
    old_cp = SchoolClass.objects.create(name="CP", school_year=previous, active=False)

    new_cp = SchoolClass.objects.create(name="CP")

    assert new_cp.school_year == SchoolYear.current()
    assert old_cp.school_year == previous
    with pytest.raises(IntegrityError), transaction.atomic():
        SchoolClass.objects.create(name="CP")


@pytest.mark.django_db
def test_loan_records_the_school_year():
    borrower = Borrower.objects.create(first_name="Lina", last_name="Martin", school_class=SchoolClass.objects.create(name="CP"))
    copy = Copy.objects.create(book=Book.objects.create(title="Petit Ours Brun"), copy_number=1)

    loan = Loan.objects.create(copy=copy, borrower=borrower)

    assert loan.school_year == SchoolYear.current()


@pytest.mark.django_db(transaction=True)
def test_migration_0015_attaches_existing_classes_and_loans_to_school_years():
    from django.db import connection
    from django.db.migrations.executor import MigrationExecutor

    executor = MigrationExecutor(connection)
    executor.migrate([("library", "0014_loan_school_class")])
    old_apps = executor.loader.project_state([("library", "0014_loan_school_class")]).apps
    OldClass = old_apps.get_model("library", "SchoolClass")
    OldBorrower = old_apps.get_model("library", "Borrower")
    OldBook = old_apps.get_model("library", "Book")
    OldCopy = old_apps.get_model("library", "Copy")
    OldLoan = old_apps.get_model("library", "Loan")
    ce2 = OldClass.objects.create(name="CE2")
    borrower = OldBorrower.objects.create(borrower_id="B999002", first_name="Noé", last_name="Petit", school_class=ce2)
    copy = OldCopy.objects.create(book=OldBook.objects.create(title="Le Petit Prince"), copy_number=1)
    old_loan = OldLoan.objects.create(
        copy=copy, borrower=borrower, school_class=ce2,
        checkout_date=date(2024, 10, 1), due_date=date(2024, 10, 15), return_date=date(2024, 10, 10),
    )

    executor = MigrationExecutor(connection)
    executor.loader.build_graph()
    executor.migrate(executor.loader.graph.leaf_nodes())

    current = SchoolYear.objects.get(is_current=True)
    assert SchoolClass.objects.get(pk=ce2.pk).school_year == current
    assert Loan.objects.get(pk=old_loan.pk).school_year.name == "2024-2025"
    assert not SchoolYear.objects.get(name="2024-2025").is_current


@pytest.mark.django_db
def test_class_form_allows_a_name_already_used_in_a_previous_year():
    from library.forms import SchoolClassForm

    previous = SchoolYear.objects.create(name="2025-2026", start_date=date(2025, 9, 1), end_date=date(2026, 8, 31))
    SchoolClass.objects.create(name="CE1", school_year=previous, active=False)

    assert SchoolClassForm({"name": "CE1", "active": True}).is_valid()
    SchoolClass.objects.create(name="CE1")
    assert not SchoolClassForm({"name": "ce1", "active": True}).is_valid()
