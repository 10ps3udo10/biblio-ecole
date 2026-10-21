"""Écran de prêt et de retour pour une douchette USB « clavier ».

Scanner la carte d'un élève le sélectionne ; scanner ensuite un livre enregistre
le prêt. Scanner un livre sans élève sélectionné enregistre son retour.
Un texte qui n'est pas un code lance une recherche manuelle (élève ou livre).
"""

import re
import time
import uuid

from django.db import transaction
from django.db.models import Q

from .forms import PhotoCirculationForm, default_form_due_date
from .models import Book, Borrower, Copy

SESSION_KEY = "desk"
BORROWER_TIMEOUT_SECONDS = 120
DUPLICATE_SECONDS = 30
LOG_SIZE = 8

CODE_PATTERN = re.compile(r"(COPY|BORROWER):([0-9a-f]{8}-?[0-9a-f]{4}-?[0-9a-f]{4}-?[0-9a-f]{4}-?[0-9a-f]{12})", re.IGNORECASE)

# A scanner configured as a QWERTY keyboard on an AZERTY computer types other characters
# (Windows and macOS layouts); map them back so the labels still work.
AZERTY_TO_QWERTY = str.maketrans({
    "&": "1", "é": "2", '"': "3", "'": "4", "(": "5", "-": "6", "§": "6", "è": "7", "_": "8", "!": "8",
    "ç": "9", "à": "0", ")": "-", "M": ":", "q": "a", "a": "q", "Q": "A", "A": "Q", "z": "w", "w": "z",
    "Z": "W", "W": "Z",
})


def parse_scan(text):
    """Return ("COPY" | "BORROWER", UUID) for a scanned label, or None for any other text."""
    text = text.strip()
    for candidate in (text, text.translate(AZERTY_TO_QWERTY)):
        match = CODE_PATTERN.fullmatch(candidate)
        if match:
            return match.group(1).upper(), uuid.UUID(match.group(2))
    return None


def describe(borrower):
    class_name = f" ({borrower.school_class})" if borrower.school_class_id else ""
    return f"{borrower.first_name} {borrower.last_name.upper()}{class_name}"


class Desk:
    """Scanning state kept in the session: selected student and last operation."""

    def __init__(self, session):
        self.session = session
        self.state = dict(session.get(SESSION_KEY) or {})

    def save(self):
        self.session[SESSION_KEY] = self.state

    @property
    def borrower(self):
        borrower_id = self.state.get("borrower")
        if not borrower_id:
            return None
        if time.time() - self.state.get("borrower_at", 0) > BORROWER_TIMEOUT_SECONDS:
            self.clear()
            return None
        return Borrower.objects.filter(pk=borrower_id, active=True).select_related("school_class").first()

    def select(self, borrower):
        self.state["borrower"] = str(borrower.pk)
        self.state["borrower_at"] = time.time()

    def clear(self):
        self.state["borrower"] = None
        self.state["borrower_at"] = None

    @property
    def log(self):
        return self.state.get("log", [])

    def _record(self, level, text, copy=None, action=None):
        self.state["log"] = [{"level": level, "text": text}, *self.log][:LOG_SIZE]
        if copy is not None:
            self.state["last"] = {"copy": str(copy.pk), "action": action, "at": time.time()}
        return {"level": level, "text": text}

    def _is_duplicate(self, copy):
        last = self.state.get("last") or {}
        return last.get("copy") == str(copy.pk) and time.time() - last.get("at", 0) <= DUPLICATE_SECONDS

    def scan(self, text):
        parsed = parse_scan(text)
        if parsed is None:
            return None
        kind, pk = parsed
        if kind == "BORROWER":
            return self._scan_borrower(pk)
        return self._scan_copy(pk)

    def _scan_borrower(self, pk):
        borrower = Borrower.objects.filter(pk=pk).select_related("school_class").first()
        if borrower is None:
            return {"level": "error", "text": "Carte inconnue : cet élève n'existe pas dans la bibliothèque."}
        if not borrower.active:
            self.clear()
            return {"level": "error", "text": f"{describe(borrower)} est archivé : emprunt impossible."}
        self.select(borrower)
        return {"level": "info", "text": f"{describe(borrower)} : scannez le livre."}

    def _scan_copy(self, pk):
        borrower = self.borrower
        with transaction.atomic():
            copy = Copy.objects.select_for_update().select_related("book").filter(pk=pk).first()
            if copy is None:
                return {"level": "error", "text": "Étiquette inconnue : ce livre n'existe pas dans la bibliothèque."}
            title = f"« {copy.book.title} » n°{copy.copy_number}"
            loan = copy.loans.filter(return_date__isnull=True).select_related("borrower__school_class").first()
            if self._is_duplicate(copy) and (loan is None or borrower is None or loan.borrower_id == borrower.pk):
                return {"level": "info", "text": f"{title} : déjà enregistré (scan en double ignoré)."}

            if borrower is None:
                if loan is None:
                    return {"level": "error", "text": f"{title} n'est pas emprunté. Pour le prêter, scannez d'abord la carte de l'élève."}
                _perform(copy, loan.borrower, PhotoCirculationForm.Action.CHECKIN)
                return self._record("success", f"Retour enregistré : {title} rendu par {describe(loan.borrower)}.", copy, "checkin")

            if loan is not None:
                since = loan.checkout_date.strftime("%d/%m/%Y")
                if loan.borrower_id == borrower.pk:
                    return {"level": "info", "text": f"{title} est déjà emprunté par {describe(borrower)} depuis le {since}."}
                return {"level": "error", "text": f"{title} est déjà emprunté par {describe(loan.borrower)} depuis le {since}. Faites d'abord le retour."}
            if copy.status != Copy.Status.AVAILABLE:
                return {"level": "error", "text": f"{title} est « {copy.get_status_display()} » : prêt impossible."}

            due_date = default_form_due_date()
            _perform(copy, borrower, PhotoCirculationForm.Action.CHECKOUT, due_date)
            self.clear()
            return self._record(
                "success",
                f"Prêt enregistré : {title} pour {describe(borrower)}, à rendre le {due_date.strftime('%d/%m/%Y')}.",
                copy,
                "checkout",
            )

    def return_copy(self, pk):
        """Explicit « Rendu » button: returns the copy whoever the selected student is."""
        with transaction.atomic():
            copy = Copy.objects.select_for_update().select_related("book").filter(pk=pk).first()
            loan = copy.loans.filter(return_date__isnull=True).select_related("borrower__school_class").first() if copy else None
            if loan is None:
                return {"level": "info", "text": "Ce livre a déjà été rendu."}
            _perform(copy, loan.borrower, PhotoCirculationForm.Action.CHECKIN)
            title = f"« {copy.book.title} » n°{copy.copy_number}"
            return self._record("success", f"Retour enregistré : {title} rendu par {describe(loan.borrower)}.", copy, "checkin")


def _perform(copy, borrower, action, due_date=None):
    from .views import _perform_circulation

    _perform_circulation(copy, borrower, action, due_date)


def search(text):
    """Manual method: students by first or last name, books by title (not removed)."""
    words = text.split()
    borrowers = Borrower.objects.filter(active=True).select_related("school_class")
    books = Book.objects.filter(archived_on__isnull=True)
    for word in words:
        borrowers = borrowers.filter(Q(first_name__icontains=word) | Q(last_name__icontains=word) | Q(borrower_id__iexact=word))
        books = books.filter(Q(title__icontains=word) | Q(authors__icontains=word))
    books = list(books.prefetch_related("copies__loans__borrower")[:8])
    for book in books:
        book.desk_copies = [copy for copy in book.copies.all() if copy.status != Copy.Status.ARCHIVED]
        for copy in book.desk_copies:
            copy.desk_loan = next((loan for loan in copy.loans.all() if loan.return_date is None), None)
    return list(borrowers.order_by("last_name", "first_name")[:8]), books
