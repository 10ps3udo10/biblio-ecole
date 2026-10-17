import importlib

import pytest

from library.models import Book, Borrower, Copy, Loan, SchoolClass


@pytest.mark.django_db
def test_loan_records_the_borrower_class_at_checkout_time():
    cp = SchoolClass.objects.create(name="CP")
    ce1 = SchoolClass.objects.create(name="CE1")
    borrower = Borrower.objects.create(first_name="Lina", last_name="Martin", school_class=cp)
    copy = Copy.objects.create(book=Book.objects.create(title="Petit Ours Brun"), copy_number=1)

    loan = Loan.objects.create(copy=copy, borrower=borrower)
    borrower.school_class = ce1
    borrower.save()

    loan.refresh_from_db()
    assert loan.school_class == cp


@pytest.mark.django_db
def test_loan_without_class_stays_empty():
    borrower = Borrower.objects.create(first_name="Paul", last_name="Durand")
    copy = Copy.objects.create(book=Book.objects.create(title="Max et les Maximonstres"), copy_number=1)

    loan = Loan.objects.create(copy=copy, borrower=borrower)

    assert loan.school_class is None


@pytest.mark.django_db
def test_backfill_function_fills_loans_without_class():
    migration = importlib.import_module("library.migrations.0014_loan_school_class")
    cp = SchoolClass.objects.create(name="CP")
    borrower = Borrower.objects.create(first_name="Lina", last_name="Martin", school_class=cp)
    copy = Copy.objects.create(book=Book.objects.create(title="Petit Ours Brun"), copy_number=1)
    loan = Loan.objects.create(copy=copy, borrower=borrower)
    Loan.objects.filter(pk=loan.pk).update(school_class=None)

    from django.apps import apps

    migration.fill_loan_school_class(apps, None)

    loan.refresh_from_db()
    assert loan.school_class == cp


@pytest.mark.django_db(transaction=True)
def test_migration_0014_backfills_loans_created_before_it():
    from django.db import connection
    from django.db.migrations.executor import MigrationExecutor

    executor = MigrationExecutor(connection)
    executor.migrate([("library", "0013_montessori_school_classes")])
    old_apps = executor.loader.project_state([("library", "0013_montessori_school_classes")]).apps
    OldClass = old_apps.get_model("library", "SchoolClass")
    OldBorrower = old_apps.get_model("library", "Borrower")
    OldBook = old_apps.get_model("library", "Book")
    OldCopy = old_apps.get_model("library", "Copy")
    OldLoan = old_apps.get_model("library", "Loan")
    cm1 = OldClass.objects.create(name="CM1")
    borrower = OldBorrower.objects.create(borrower_id="B999001", first_name="Noé", last_name="Petit", school_class=cm1)
    copy = OldCopy.objects.create(book=OldBook.objects.create(title="Le Petit Prince"), copy_number=1)
    loan = OldLoan.objects.create(copy=copy, borrower=borrower)

    executor = MigrationExecutor(connection)
    executor.loader.build_graph()
    executor.migrate(executor.loader.graph.leaf_nodes())

    assert Loan.objects.get(pk=loan.pk).school_class_id == cm1.pk
