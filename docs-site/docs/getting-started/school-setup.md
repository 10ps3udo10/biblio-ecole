# School Setup

Staff settings are available at `/settings/` after staff login.

![Shelf-School school settings screen](/img/school-settings.png)

Configure:

- School name and short display name.
- School logo.
- Address, email, and telephone details.
- Default loan duration in days.
- Footer printed on copy and borrower labels.

**The current design supports one school per installation.** Separate schools
should run separate Shelf-School installations and databases.

## Staff accounts and borrowers

Staff accounts belong to adults who sign in and operate Shelf-School. Borrower
profiles represent students or teachers who receive books.
**Borrowers do not log in and do not need passwords.**

Creating a staff account automatically creates its borrower profile. If a
borrower with the same identifier already exists, Shelf-School links that record
instead so its loans and history remain intact. The Borrower ID, name, and email
match the staff account; passwords remain private to staff login and circulation
data remains on the borrower profile.

One staff administrator is enough for a local deployment. When several adults
maintain the library, open **Settings > Manage staff accounts** to create their
Shelf-School logins. **Advanced (Django Admin)** is the underlying technical
interface and is not needed for normal library work.

See [Staff Accounts](../usage/staff-accounts.md) for account creation, password
reset, and role details.

## First operational check

Before opening the kiosk to students:

1. Add a test borrower.
2. Catalog a book and print its physical copy QR label.
3. Sign out of the staff account.
4. Check out and return the book from `/`.
5. Sign back in and verify the loan history.
