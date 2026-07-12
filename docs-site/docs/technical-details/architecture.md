# Architecture

Shelf-School is a server-rendered Django application with a public circulation
surface and authenticated staff operations.

```text
Browser camera or uploaded image
  -> Django form and local barcode decoder
  -> Book / Copy lookup
  -> signed confirmation token
  -> transactional Loan update
  -> SQLite database
```

## Domain model

| Model | Purpose |
| --- | --- |
| `SchoolProfile` | Singleton branding and loan defaults. |
| `Book` | Bibliographic title or edition. |
| `Copy` | One physical item with a unique QR payload. |
| `Borrower` | Student or teacher who can receive books. |
| `Loan` | Checkout, due date, and optional return date for one copy. |

**The database enforces one active loan per physical copy.**

## Trust boundaries

The root circulation route is intentionally public for a supervised school
kiosk. Catalog, borrowers, reports, backups, settings, and Django administration
require authentication. Named recent activity is not rendered for signed-out
users.

Photo identification does not mutate circulation state. It creates a signed,
short-lived confirmation token containing copy, borrower, action, and due date.
The confirmation request locks and revalidates the copy before changing the
loan, **protecting against stale or repeated submissions**.

## Storage and external services

- SQLite is the default structured store.
- Uploaded files use local media storage.
- `zxing-cpp` decodes QR and ISBN barcodes locally.
- Open Library is queried only for optional ISBN metadata during intake.
- No paid AI service is required.
