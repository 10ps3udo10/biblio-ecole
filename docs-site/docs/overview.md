# Overview

Shelf-School is an open-source library system for schools. Its primary
screen is a public circulation kiosk where a student selects their name,
chooses checkout or return, and photographs one book at a time.

:::caution Development status
Shelf-School is currently **`0.1.0-dev`** and has not reached its first stable
release. Back up school data before upgrades.
:::

**Students do not need passwords, accounts, or library cards.** Staff sign in
for cataloging, borrower management, reports, settings, and backups. The public
header labels this entry point **Staff login**.

## Core workflow

<div className="workflow">
  <div><strong>Identify the borrower</strong>Select a Borrower ID or name from the school list.</div>
  <div><strong>Identify the copy</strong>Photograph its Shelf-School QR or ISBN barcode.</div>
  <div><strong>Confirm the loan</strong>Review the book, borrower, action, and due date.</div>
</div>

## Current capabilities

- Public self-service checkout and return.
- Multi-book checkout with one final, atomic confirmation.
- Multi-book return from the selected borrower's current loans.
- Local QR and ISBN barcode decoding from photographs.
- Free book metadata lookup through Open Library.
- Selectable bulk retrieval of missing catalog covers after import.
- Separate records for titles, physical copies, borrowers, and loans.
- Staff correction of book, copy, borrower, and active-loan borrower records.
- Private borrower search without sending the full directory to the kiosk.
- Printable QR labels for every physical copy.
- School branding and configurable loan duration.
- Native staff login, account management, and password reset.
- Borrower and book CSV import.
- Optional topics, reading guidance, Montessori levels, and catalog-review status.
- Overdue reports, CSV export, and SQLite backup download.
- Explicitly separated **Advanced (Django Admin)** access for technical maintenance.
- Pytest and Playwright browser coverage.

## Important boundary

**A book must be cataloged before it can circulate.** Photo identification finds a
known physical copy; it never creates a loan for an unregistered book.

Shelf-School identifies checkout books one at a time, by photograph or manual
search, and collects them in a basket. Several books can then be checked out in
one transaction. Future multi-book recognition may propose several catalog
matches from one photograph, but every physical copy must still be reviewed and
confirmed before a loan is recorded.
