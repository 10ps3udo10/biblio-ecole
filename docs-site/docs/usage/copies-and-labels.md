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

Staff can select **Edit copy** to correct its shelf, condition, or status. While
a copy is checked out, its status remains controlled by circulation, but shelf
and condition corrections are still allowed.

## Delete one copy

When a title has multiple physical copies, staff can open a copy and select
**Delete copy**. This removes only that physical copy and its completed loan
history. Other copies and the shared book metadata remain unchanged.

A checked-out copy cannot be deleted. The last remaining copy must be removed
with **Delete book** so the application does not leave a title with no physical
items.

## Delete a book

Staff can delete a book from its detail page when none of its copies is checked
out. This also deletes its physical copies, stored cover, and loan history.
Shelf-School blocks deletion until every active copy has been returned.
