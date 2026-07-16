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

Staff accounts belong to adults who sign in and operate Shelf-School. Borrowers
are separate records representing students or teachers who receive books.
**Borrowers do not log in and do not need passwords.**

Creating a staff account never creates, updates, or links a borrower. If a
teacher is both a staff operator and a borrower, keep one record in each area.
The records remain independent even when their names, usernames, or email
addresses match.

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
