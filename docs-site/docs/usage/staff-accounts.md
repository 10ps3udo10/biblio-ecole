# Staff Accounts

Shelf-School has two independent types of people:

| Type | Signs in? | Purpose |
| --- | --- | --- |
| **Staff account** | Yes | Operates the catalog, borrowers, circulation records, reports, and settings. |
| **Borrower** | No | Receives and returns books through the circulation desk. |

:::important One person can have both records
A teacher may operate Shelf-School and also borrow books. Create one staff
account and one borrower record. Matching names, usernames, or email addresses
do not link or merge them.
:::

## Add staff

Only the system administrator can manage staff accounts.

1. Sign in and open **Settings**.
2. Select **Manage staff accounts**.
3. Select **Add staff account**.
4. Enter the adult's name, username, email address, and initial password.
5. Select **Save staff account**.

The new account receives ordinary Shelf-School staff access. It does not become
a system administrator and it does not change any borrower with the same
username.

## Maintain access

Open **Settings > Manage staff accounts** to:

- Edit a username, name, or email address.
- Deactivate an account without deleting its history.
- Reset a forgotten password.
- Distinguish ordinary **Staff** from the **System administrator**.

Shelf-School prevents the signed-in system administrator from deactivating
their own account through this screen.

## Advanced

**Advanced (Django Admin)** is the framework's technical database and permission
interface. It is visible only to a system administrator and is not required for
normal library work or routine staff-account management.
