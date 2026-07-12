# Testing

Shelf-School uses pytest for model and view behavior and Playwright for browser
workflows.

Install browser support once:

```bash
python -m playwright install chromium
```

Run everything:

```bash
python -m pytest -q
```

Run only browser tests:

```bash
python -m pytest tests/test_playwright.py -q
```

Run Django validation and migration drift checks:

```bash
python manage.py check
python manage.py makemigrations --check --dry-run
```

The browser suite covers administrator workflows, photo intake, anonymous
self-checkout, transaction confirmation, repeated scans for one borrower, and
returns.

## Documentation

From `docs-site/`:

```bash
npm ci
npm run typecheck
npm run build
test -s build/search-index.json
```

Both GitHub Actions workflows are manual-only and must be started from the
repository **Actions** tab.
