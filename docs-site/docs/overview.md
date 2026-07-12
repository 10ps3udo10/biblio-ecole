# Overview

Shelf-School is an open-source library system for small schools. Its primary
screen is a public circulation kiosk where a student selects their name,
chooses checkout or return, and photographs one book at a time.

Students do not need passwords, accounts, or library cards. Staff use a single
administrator session for cataloging, borrower management, reports, settings,
and backups.

## Core workflow

<div className="workflow">
  <div><strong>Identify the borrower</strong>Select a username or name from the school list.</div>
  <div><strong>Identify the copy</strong>Photograph its Shelf-School QR or ISBN barcode.</div>
  <div><strong>Confirm the loan</strong>Review the book, borrower, action, and due date.</div>
</div>

## Current capabilities

- Public self-service checkout and return.
- Local QR and ISBN barcode decoding from photographs.
- Free book metadata lookup through Open Library.
- Separate records for titles, physical copies, borrowers, and loans.
- Printable QR labels for every physical copy.
- School branding and configurable loan duration.
- Borrower and book CSV import.
- Overdue reports, CSV export, and SQLite backup download.
- Django administration for maintenance.
- Pytest and Playwright browser coverage.

## Important boundary

A book must be cataloged before it can circulate. Photo identification finds a
known physical copy; it never creates a loan for an unregistered book.

Shelf-School currently processes one photograph and one physical copy per
transaction. Future multi-book recognition may propose several catalog matches,
but every copy must still be reviewed and confirmed before a loan is recorded.
