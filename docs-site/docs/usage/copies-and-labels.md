# Copies and Labels

Shelf-School separates a bibliographic title from each physical item:

- `Book` is a title or edition, identified by metadata such as ISBN.
- `Copy` is one physical book on a shelf.
- `Loan` always references a `Copy`.

Every copy receives a unique payload:

```text
COPY:<copy-uuid>
```

Print the QR label from the copy detail page and attach it where a camera can
see it clearly. The copy QR is preferred for circulation because it remains
unambiguous when the library owns several copies of one ISBN.

## Copy state

| State | Meaning |
| --- | --- |
| Available | May be checked out. |
| Checked out | Has an active loan. |
| Missing | Not currently available. |
| Damaged | Removed from normal circulation. |
| Archived | Retained in records but not in active use. |

Condition is recorded separately as new, good, worn, or damaged.

## Delete a book

Staff can delete a book from its detail page when none of its copies is checked
out. This also deletes its physical copies, stored cover, and loan history.
Shelf-School blocks deletion until every active copy has been returned.
