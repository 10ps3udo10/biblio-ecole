BOOK_REQUIRED = (("Title", "The school library book"),)
BOOK_OPTIONAL = (
    ("Book details", (
        ("Subtitle", "A story about friendship"),
        ("Contributors", "Alex Writer; Sam Illustrator"),
        ("ISBN", "9780306406157"),
        ("Publisher", "Example Press"),
        ("Publication year", "2024"),
        ("Language", "English"),
        ("Pages", "32"),
        ("Format", "Paperback"),
        ("Description", "A short description of the book."),
    )),
    ("School topics and reading", (
        ("Category", "Science and nature"),
        ("Topics", "plants; seasons"),
        ("Suggested Montessori level", "Lower Elementary (6-9)"),
        ("Suggested age range", "6-9"),
        ("Suggested reading level", "Early reader"),
    )),
    ("Source and review", (
        ("Source photo", "photo-001.jpg"),
        ("Photo position", "top left"),
        ("Identification confidence", "high, medium, or low"),
        ("Review notes", "Verify the publisher."),
        ("Bibliographic source URL", "https://example.org/book"),
    )),
)
BORROWER_REQUIRED = (
    ("Borrower ID", "student-001"),
    ("First name", "Sam"),
    ("Last name", "Reader"),
)
BORROWER_OPTIONAL = (
    ("School role and assignment", (
        ("School role", "Student or Employee"),
        ("Position", "An employee position configured in Settings"),
        ("Class", "A student class configured in Settings"),
    )),
    ("Contact and status", (
        ("Email", "sam@example.org"),
        ("Active", "Yes or No"),
    )),
)


def csv_columns(kind):
    required, optional = (
        (BOOK_REQUIRED, BOOK_OPTIONAL) if kind == "books"
        else (BORROWER_REQUIRED, BORROWER_OPTIONAL)
    )
    return {
        "required_columns": required,
        "optional_groups": optional,
        "headers": [name for name, _ in required] + [
            name for _, fields in optional for name, _ in fields
        ],
    }
