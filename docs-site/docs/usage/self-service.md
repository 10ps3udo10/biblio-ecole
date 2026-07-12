# Self-Service Circulation

The public kiosk at `/` is the center of Shelf-School. It does not require the
administrator to remain signed in.

![Public Shelf-School circulation desk](/img/circulation-desk.png)

:::info Photo privacy
Circulation photos are decoded only for the current request. They are not saved
to `media/`, attached to the book, or retained as circulation history.
:::

## Check out a book

1. Keep **Check out** selected.
2. Find the borrower by username or name.
3. Select the borrower.
4. Confirm the due date.
5. Take a close photograph of the copy QR label or ISBN barcode.
6. Select **Identify book**.
7. Review the identified title and copy.
8. Select **Confirm checkout**.

![Shelf-School book photograph step](/img/circulation-scan.png)

Shelf-School returns to the kiosk with the same borrower and action selected so
another book can be processed immediately.

![Shelf-School transaction confirmation screen](/img/transaction-confirmation.png)

## Return a book

1. Select **Check in / return**.
2. Find and select the borrower returning the book.
3. Photograph the book label.
4. Review the identified copy.
5. Select **Confirm return**.

Shelf-School refuses a return when the selected borrower does not hold the
active loan. This prevents a mistaken name selection from silently changing
another student's record.

## Identifier behavior

| Photograph contains | Result |
| --- | --- |
| Shelf-School copy QR | Identifies one exact physical copy. |
| ISBN with one eligible copy | Uses that copy. |
| ISBN with several eligible copies | Requests the copy QR label. |
| Unknown ISBN | Requests staff cataloging. |
| No readable code | Requests a closer photograph. |

## Manual fallback

Photo and manual lookup have equal weight on the book step. Select **Find
manually** whenever it is faster or the camera cannot read a code.
The filter uses partial matching against title, author, ISBN, shelf, and copy
number. Select one exact physical copy, then continue to the normal review and
confirmation screen. Availability and borrower ownership are validated again
on the server.

![Shelf-School manual book fallback](/img/manual-fallback.png)

The kiosk never displays recent named circulation activity to signed-out users.
