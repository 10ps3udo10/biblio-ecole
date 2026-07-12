# Troubleshooting

## No barcode is detected

- Photograph the barcode straight on.
- Fill most of the image with the barcode.
- Avoid glare and motion blur.
- Try the Shelf-School copy QR instead of the ISBN.
- Confirm `zxing-cpp` and Pillow are installed through `requirements.txt`.

The browser may not implement `BarcodeDetector`. This is not fatal: the server
performs a second local decode after submission.

## ISBN matches multiple copies

ISBN identifies an edition, not one physical item. Attach and photograph the
unique Shelf-School copy QR label.

## Book is not cataloged

Sign in as staff and use **Photo intake**. Public circulation never creates an
unknown book automatically.

## Borrower is not listed

Open the staff borrower list and confirm that the borrower exists and is
active. Inactive borrowers are intentionally excluded from self-service.

## Return says a different borrower holds the book

Select the borrower shown on the active loan. Staff can verify this on the copy
detail or borrower detail page.

## Development server will not start

If port `8001` is occupied, choose another port:

```bash
python manage.py runserver 127.0.0.1:8002
```

Apply migrations and run checks:

```bash
python manage.py migrate
python manage.py check
```

## GitHub Pages does not update

The documentation workflow is intentionally manual. Open the repository's
**Actions** tab and run the **Documentation** workflow. It typechecks, builds,
verifies the local search index, uploads the Pages artifact, and deploys it.
