# Self-Service Circulation

The public kiosk at `/` is the center of Shelf-School. **It does not require the
administrator to remain signed in.**

The header identifies Shelf-School and the configured school. **Admin login**
opens the staff sign-in; students do not use it.

![Public Shelf-School circulation desk](/img/circulation-desk.png)

:::info Photo privacy
Circulation photos are decoded only for the current request. They are not saved
to `media/`, attached to the book, or retained as circulation history.
:::

## Check out a book

1. Keep **Check out** selected.
2. Type at least two letters from the borrower's username or name.
3. Select the borrower from the small matching list.
4. Select **Continue**.
5. Keep **Take photo** selected and photograph the copy QR label or ISBN barcode.
6. Select **Identify book**.
7. Review the identified title, copy, borrower, and due date.
8. Select **Confirm checkout**.

![Shelf-School book photograph step](/img/circulation-scan.png)

Shelf-School returns to the kiosk with the same borrower and action selected so
another book can be processed immediately.

![Shelf-School transaction confirmation screen](/img/transaction-confirmation.png)

## Return a book

1. Select **Check in / return**.
2. Search for and select the borrower returning the book.
3. Select **Continue**.
4. Select one or more books from that borrower's current loans.
5. Select **Review return**.
6. Check the selected titles and select **Confirm return**.

Only books currently loaned to the selected borrower appear. The list is also
validated on the server, preventing a mistaken name selection from changing
another student's record. **A return does not require a photograph.**

The kiosk never downloads the complete borrower directory. It requests at most
eight matches after two letters are entered, and fetches loans only for the
selected borrower. Email addresses and borrower QR payloads are not exposed.

## Identifier behavior

| Photograph contains | Result |
| --- | --- |
| Shelf-School copy QR | Identifies one exact physical copy. |
| ISBN with one eligible copy | Uses that copy. |
| ISBN with several eligible copies | Requests the copy QR label. |
| Unknown ISBN | Requests staff cataloging. |
| No readable code | Requests a closer photograph. |

## Manual fallback

For checkout, photo and manual lookup have equal weight on the book step. Select
**Find manually** whenever it is faster or the camera cannot read a code.
The filter uses partial matching against title, author, ISBN, shelf, and copy
number. Select one exact physical copy, then continue to the normal review and
confirmation screen. Availability and borrower ownership are validated again
on the server.

![Shelf-School manual book fallback](/img/manual-fallback.png)

The kiosk never displays recent named circulation activity to signed-out users.
