# Staff Accounts

Shelf-School uses two related records for staff members:

| Type | Signs in? | Purpose |
| --- | --- | --- |
| **Staff account** | Yes | Operates the catalog, borrowers, circulation records, reports, and settings. |
| **Borrower** | No | Receives and returns books through the circulation desk. |

:::important Staff can always borrow
Creating a staff account automatically creates its borrower profile. If that
Borrower ID already exists, Shelf-School links the existing profile so its
loans and history are preserved. The Borrower ID, name, and email always match
the staff account.
:::

## Add staff

Only the system administrator can manage staff accounts.

1. Sign in and open **Settings**.
2. Select **Manage staff accounts**.
3. Select **Add staff account**.
4. Enter the adult's name, Borrower ID, email address, and initial password.
5. Select **Save staff account**.

The new account receives ordinary Shelf-School staff access. Shelf-School also
creates its borrower profile automatically. When a borrower with the same
identifier already exists, that profile is linked instead, preserving its loans
and history. The new account does not become a system administrator.

## Maintain access

Open **Settings > Manage staff accounts** to:

- Edit a Borrower ID, name, or email address for both linked records.
- Deactivate an account without deleting its history.
- Reset a forgotten password.
- Distinguish ordinary **Staff** from the **System administrator**.
- Open the linked borrower profile used for circulation.

Shelf-School prevents the signed-in system administrator from deactivating
their own account through this screen.

Deactivating staff access does not deactivate or delete the borrower profile or
its circulation history. The person can still return or borrow books.

## Advanced

**Advanced (Django Admin)** is the framework's technical database and permission
interface. It is visible only to a system administrator and is not required for
normal library work or routine staff-account management.
