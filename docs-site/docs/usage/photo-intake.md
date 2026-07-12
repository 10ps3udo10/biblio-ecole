# Photo Intake

Photo intake is a staff workflow at `/books/photo-intake/`.

![Shelf-School photo intake screen](/img/photo-intake.png)

The regular **Add book** form is also ISBN-first. Entering ISBN-13 or ISBN-10
fills available title, author, publisher, year, language, and description fields
before saving. Its catalog cover is downloaded when the book is created.

## Add a title and first copy

1. Sign in as the administrator.
2. Open **Photo intake**.
3. Photograph the ISBN barcode closely and in focus.
4. Confirm the detected ISBN or enter it manually.
5. Add a title manually only when no ISBN is available.
6. Optionally set author, shelf, and condition.
7. Select **Track this book**.
8. Print the generated QR label and attach it to the physical book.

Barcode decoding runs locally with `zxing-cpp`. When an ISBN is available,
Shelf-School requests free metadata from Open Library. **No paid AI API is
required.**

When Open Library has a cover, Shelf-School downloads and stores it when staff
selects **Track this book**. The uploaded ISBN photograph is scanner input and
**is never stored**. If no catalog cover is available, the book remains without a
cover.

When staff intentionally adds a book without an ISBN using a manual title, the
uploaded image is treated as its cover and is stored.

Entering a valid ISBN triggers the free lookup immediately and fills available
title and author fields before submission. Publisher, publication year, and
other available metadata are stored when the book is tracked.

Open Library does not contain every published ISBN, especially recent
independently published titles. In that case Shelf-School clearly reports that
the ISBN is valid but no free metadata was found. The ISBN can still be saved;
enter title and author manually. Shelf-School also provides an exact-ISBN web
search as a no-cost fallback so staff can find and verify the missing details.

General search results are not imported automatically because search pages do
not provide a stable, licensed metadata API. Future structured providers can be
added without changing this review step.

Stored API or manual covers live under `media/covers/`. Staff can remove one
with **Delete stored photo** on the book detail page. Deleting the book record
also deletes its stored cover file.

## Existing ISBN

If the ISBN already exists, photo intake adds another physical `Copy` to the
existing `Book` instead of duplicating the title. Each new copy receives its own
QR payload and copy number.

## Cover-only photographs

The current implementation does not infer title and author from cover artwork.
Use a barcode photograph or enter the title manually. Cover recognition may be
added later as an optional matching aid, but uncertain recognition must always
require staff review.
