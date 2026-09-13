# Self-Service Circulation

The public kiosk at `/` is the center of Shelf-School. **It does not require a
staff member to remain signed in.**

The header identifies Shelf-School and the configured school. **Staff login**
is only for people who operate the library; borrowers do not use it.

## Browse without signing in

Select **Catalog** in the public header to search titles, contributors, topics,
ISBNs, or shelf locations. Each result shows how many copies are available.
Open a title to see copy numbers, shelf locations, and current availability.
Switch between **List view** for scanning titles and **Grid view** for browsing
covers. List is the initial default; the browser remembers your choice on that
device. Both views share search, sorting, and pagination.

Use **Available only**, **Shelf**, and **Language** to narrow the results.
Shelf and language filters appear when those values exist in the catalog.
When a shelf is selected, availability refers to copies on that shelf.
Filters remain selected when moving between pages. **Clear filters** restores
the full catalog.

Borrower names, loan histories, and editing controls are not shown. Employees
and students need no credentials to browse.

![Public Shelf-School circulation desk](/img/circulation-desk.png)

:::info Photo privacy
Circulation photos are decoded only for the current request. They are not saved
to `media/`, attached to the book, or retained as circulation history.
:::

## Check out a book

1. Keep **Check out** selected.
2. Type at least two letters from the borrower's ID or name.
3. Select the borrower from the small matching list.
4. Select **Continue**.
5. **Find manually** is selected by default. Search for the title, contributor,
   ISBN, shelf, or copy number, then select the exact copy.
6. Select **Review book** and review the checkout basket. Alternatively, select
   **Take photo**, photograph a copy QR label or clear ISBN barcode, and select
   **Identify book**.
7. To borrow more books, select **Add another book** and identify the next book
   by photo or manual search.
8. Remove any mistaken selection from the basket if needed.
9. Review the books, borrower, and due date, then select **Borrow 1 book**
   (the button shows the number selected).

![Shelf-School book photograph step](/img/circulation-scan.png)

No loan is created while books are being added to the basket. At final
confirmation, Shelf-School rechecks every copy and creates all loans in one
database transaction. If one copy is no longer available, **none of the books
are checked out**.

Shelf-School shows a completion screen with the borrower, selected books, and
due date. Select **Next borrower** to clear the selection, or **Same borrower**
to start another transaction for that person. Refreshing does not repeat the loan.

On the book step, **Change** returns to borrower selection and clears the current
basket. No loans have been created at that point.

![Shelf-School transaction confirmation screen](/img/transaction-confirmation.png)

## Return a book

1. Select **Check in / return**.
2. Search for and select the borrower returning the book.
3. Select **Continue**.
4. Select one or more books from that borrower's current loans.
5. Select **Review 1 book** (the count follows your selection).
6. Check the selected titles and select **Return 1 book** (or the selected count).

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

## Find a book

For checkout, **Find manually** is the default on every new book step.
**Take photo** remains available alongside it when a readable label is present.
The filter uses partial matching against title, contributor, ISBN, shelf, and
copy number. Only copies that are ready to borrow appear in the list, and
missing metadata is omitted from each option. Select one exact physical copy,
then continue to the normal review and confirmation screen. Availability and
borrower ownership are validated again on the server.

![Shelf-School manual book fallback](/img/manual-fallback.png)

The kiosk never displays recent named circulation activity to signed-out users.
