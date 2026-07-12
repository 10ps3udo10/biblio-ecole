# School Setup

Staff settings are available at `/settings/` after administrator login.

![Shelf-School school settings screen](/img/school-settings.png)

Configure:

- School name and short display name.
- School logo.
- Address, email, and telephone details.
- Default loan duration in days.
- Footer printed on copy and borrower labels.

The current design supports one school per installation. Separate schools
should run separate Shelf-School installations and databases.

## Accounts and borrowers

The administrator account operates Shelf-School and Django administration.
Borrowers are separate records representing students or teachers who receive
books. Borrowers do not log in and do not need passwords.

One administrator is enough for a small deployment. Additional Django staff
accounts are only necessary when several adults maintain the catalog or school
configuration.

## First operational check

Before opening the kiosk to students:

1. Add a test borrower.
2. Catalog a book and print its physical copy QR label.
3. Sign out of administration.
4. Check out and return the book from `/`.
5. Sign back in and verify the loan history.
