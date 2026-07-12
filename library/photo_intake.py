import json
import re
import urllib.error
import urllib.parse
import urllib.request


class MetadataLookupError(Exception):
    pass


def clean_isbn(value):
    return re.sub(r"[^0-9Xx]", "", value or "")[:13]


def is_valid_isbn(value):
    isbn = clean_isbn(value)
    if len(isbn) == 13 and isbn.isdigit():
        total = sum(int(digit) * (1 if index % 2 == 0 else 3) for index, digit in enumerate(isbn[:12]))
        return (10 - total % 10) % 10 == int(isbn[-1])
    if len(isbn) == 10 and isbn[:9].isdigit() and (isbn[-1].isdigit() or isbn[-1].upper() == "X"):
        digits = [int(digit) for digit in isbn[:9]] + [10 if isbn[-1].upper() == "X" else int(isbn[-1])]
        return sum((10 - index) * digit for index, digit in enumerate(digits)) % 11 == 0
    return False


def publication_year(value):
    match = re.search(r"(1[5-9][0-9]{2}|20[0-9]{2})", value or "")
    return int(match.group(1)) if match else None


def normalize_open_library_record(isbn, record):
    identifiers = record.get("identifiers") or {}
    authors = record.get("authors") or []
    publishers = record.get("publishers") or []
    subjects = record.get("subjects") or []
    excerpts = record.get("excerpts") or []
    cover = record.get("cover") or {}
    return {
        "title": record.get("title") or "",
        "subtitle": record.get("subtitle") or "",
        "authors": ", ".join(author.get("name", "") for author in authors if author.get("name")),
        "isbn10": (identifiers.get("isbn_10") or [""])[0],
        "isbn13": (identifiers.get("isbn_13") or [isbn if len(isbn) == 13 else ""])[0],
        "publisher": (publishers[0].get("name") if publishers else "") or "",
        "publication_year": publication_year(record.get("publish_date")),
        "language": "",
        "description": (excerpts[0].get("text") if excerpts else "") or "",
        "cover_url": (cover.get("large") or cover.get("medium") or "").replace("http://", "https://"),
        "suggested_category": (subjects[0].get("name") if subjects else "") or "",
    }


def download_cover_by_isbn(isbn, timeout=8, max_bytes=5 * 1024 * 1024):
    isbn = clean_isbn(isbn)
    if not is_valid_isbn(isbn):
        return None
    url = f"https://covers.openlibrary.org/b/isbn/{isbn}-L.jpg?default=false"
    request = urllib.request.Request(url, headers={"User-Agent": "Shelf-School/0.1"})
    try:
        with urllib.request.urlopen(request, timeout=timeout) as response:
            content_type = response.headers.get_content_type()
            if not content_type.startswith("image/"):
                return None
            content = response.read(max_bytes + 1)
    except (urllib.error.URLError, TimeoutError):
        return None
    if not content or len(content) > max_bytes:
        return None
    extension = "png" if content_type == "image/png" else "jpg"
    return content, extension


def lookup_book_by_isbn(isbn, timeout=8):
    isbn = clean_isbn(isbn)
    if not isbn:
        return {}
    query = urllib.parse.urlencode({"bibkeys": f"ISBN:{isbn}", "jscmd": "data", "format": "json"})
    url = f"https://openlibrary.org/api/books?{query}"
    request = urllib.request.Request(url, headers={"User-Agent": "school-library-mvp/0.1"})
    try:
        with urllib.request.urlopen(request, timeout=timeout) as response:
            payload = json.loads(response.read().decode("utf-8"))
    except (urllib.error.URLError, TimeoutError, json.JSONDecodeError) as exc:
        raise MetadataLookupError(str(exc)) from exc
    record = payload.get(f"ISBN:{isbn}")
    return normalize_open_library_record(isbn, record) if record else {}


def decode_barcodes_from_image(uploaded_file):
    try:
        from PIL import Image
        import zxingcpp
    except ImportError:
        return []

    position = uploaded_file.tell()
    try:
        uploaded_file.seek(0)
        image = Image.open(uploaded_file)
        return [getattr(barcode, "text", "") for barcode in zxingcpp.read_barcodes(image)]
    except Exception:
        return []
    finally:
        uploaded_file.seek(position)


def decode_isbn_from_image(uploaded_file):
    for value in decode_barcodes_from_image(uploaded_file):
        isbn = clean_isbn(value)
        if isbn.startswith(("978", "979")) and len(isbn) == 13:
            return isbn
    return ""
