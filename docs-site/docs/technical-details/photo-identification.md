# Photo Identification

Shelf-School treats a photograph as input to an identifier decoder, not as the
library record itself.

:::info Storage behavior
ISBN-intake and circulation images are temporary request data and are discarded
after decoding. Available Open Library covers are downloaded when the book is
created. A no-ISBN intake image is stored only when staff supplies a manual
title and intends that image to be the cover.
:::

## Current pipeline

1. The browser optionally tries `BarcodeDetector` for immediate feedback.
2. The uploaded file is sent to Django.
3. Pillow opens the image locally.
4. `zxing-cpp` decodes supported barcodes and QR codes.
5. A `COPY:<uuid>` payload resolves directly to one copy.
6. An ISBN resolves through cataloged books and eligible copies.
7. The user reviews the result before confirming circulation.

For checkout, an ISBN candidate must have exactly one available matching copy.
For return, it must have exactly one checked-out matching copy with an active
loan. Ambiguous ISBNs require the unique copy QR.

## Future multi-book recognition

An optional recognizer may eventually accept one scene containing several
books and propose catalog matches. A safe implementation must:

- Keep the existing local barcode path as the default.
- Make paid or remote providers optional and explicit.
- Show confidence and provenance for every proposed match.
- Reject unknown or ambiguous physical copies.
- Require review before creating any loan.
- Preserve one `Loan` record per `Copy`.

Cover recognition alone cannot reliably identify which physical copy is being
borrowed when several copies share the same title.
