BOOK_REQUIRED = (("Title", "Le livre de la bibliothèque"),)
BOOK_OPTIONAL = (
    ("Informations sur le livre", (
        ("Subtitle", "Une histoire d'amitié"),
        ("Contributors", "Alex Auteur ; Sam Illustrateur"),
        ("ISBN", "9780306406157"),
        ("Publisher", "Éditions Exemple"),
        ("Publication year", "2024"),
        ("Language", "Français"),
        ("Pages", "32"),
        ("Format", "Broché"),
        ("Description", "Une courte description du livre."),
    )),
    ("Thèmes et lecture", (
        ("Category", "Sciences et nature"),
        ("Topics", "plantes ; saisons"),
        ("Suggested Montessori level", "Élémentaire inférieur (6-9)"),
        ("Suggested age range", "6-9"),
        ("Suggested reading level", "Lecteur débutant"),
    )),
    ("Source et vérification", (
        ("Source photo", "photo-001.jpg"),
        ("Photo position", "en haut à gauche"),
        ("Identification confidence", "high, medium ou low"),
        ("Review notes", "Vérifier l'éditeur."),
        ("Bibliographic source URL", "https://example.org/book"),
    )),
)
BORROWER_REQUIRED = (
    ("First name", "Samir"),
    ("Last name", "Lecteur"),
)
BORROWER_OPTIONAL = (
    ("Dossier scolaire", (
        ("School ID", "Numéro d'élève ou de personnel (facultatif)"),
    )),
    ("Rôle et affectation", (
        ("School role", "Student ou Employee"),
        ("Position", "Une fonction créée dans les paramètres"),
        ("Class", "Élémentaire inférieur (6-9)"),
    )),
    ("Contact et statut", (
        ("Email", "sam@example.org"),
        ("Active", "Yes ou No"),
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
