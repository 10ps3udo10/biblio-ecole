# Borrowers

Borrowers are students or teachers who may hold books. They are not Django
login accounts.

Each borrower stores:

- Username or school identifier.
- First and last name.
- Class.
- Email address.
- Active or inactive status.
- A generated borrower QR payload for optional future workflows.

## Add individually

Sign in, open **Borrowers**, and select **Add borrower**.

## Import CSV

The borrower import accepts UTF-8 CSV files with these columns:

```text
Username,First name,Last name,Class,Email,Active
```

Example:

```csv
Username,First name,Last name,Class,Email,Active
ana,Ana,Garcia,4A,ana@example.org,yes
leo,Leo,Martinez,4A,leo@example.org,true
```

Username is the update key. Importing an existing username updates that
borrower rather than creating a duplicate.

Inactive borrowers remain in historical loan records but are removed from the
public kiosk dropdown.
