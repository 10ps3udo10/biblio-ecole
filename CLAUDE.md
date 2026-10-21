# biblio-ecole

Application locale de gestion de la bibliothèque d'une école primaire française
(maternelle et élémentaire). Fork de Shelf-School (MIT) : voir `NOTICE.md`.
Django 5.2 + SQLite, utilisée dans un navigateur sur un PC de l'école.

## Commandes

```bash
python -m venv .venv && source .venv/bin/activate
python -m pip install -r requirements.txt
python manage.py migrate && python manage.py createsuperuser
python manage.py runserver 127.0.0.1:8427

python -m pytest -q -m "not playwright"        # suite rapide, à faire passer avant chaque commit
python -m pytest tests/test_playwright.py -q   # navigateur requis : python -m playwright install chromium
python manage.py makemigrations --check --dry-run
```

## Règles du domaine (non négociables)

- **Ne jamais supprimer d'historique.** Livres et exemplaires sont retirés par
  `archived_on` (+ statut `archived`), les élèves qui partent par `active=False`
  et `archived_on`. Les prêts (`Loan`) ne sont jamais supprimés.
- Un exemplaire emprunté ne se retire qu'après une confirmation explicite
  (`confirm_borrowed=1`) ; il reste en prêt et passe en `archived` à son retour.
- Les QR codes ne contiennent qu'un identifiant technique : `COPY:<uuid>` et
  `BORROWER:<uuid>`. Jamais de nom ni d'autre donnée personnelle.
- `Loan.school_class` et `Loan.school_year` figent la classe et l'année au moment
  de l'emprunt (remplis dans `Loan.save()`). Ne pas les recalculer depuis l'élève.
- Une seule `SchoolYear` a `is_current=True` (contrainte en base). Les classes
  appartiennent à une année ; le nom est unique par année. Toute recherche de
  classe par nom doit se limiter à `SchoolYear.current()`.
- Le passage d'année (`library/school_year.py`) désactive les anciennes classes,
  déplace ou archive les élèves, et laisse les prêts en cours ouverts et signalés.
- RGPD : données d'élèves uniquement en local. Ne jamais versionner
  `db.sqlite3`, `media/`, `backups/` ni de CSV réels d'élèves. Pas de service en
  ligne ajouté sans accord explicite.

## Conventions

- Interface en français, écrite directement dans les gabarits et le code (pas de
  gettext, une seule langue). Vouvoiement, typographie française (« », espace
  avant « : ; ? ! »). Termes : Élève, Exemplaire, Emprunt, Retour, Retirer du catalogue.
- Exceptions volontaires en anglais : clés de colonnes du CSV d'import/export des
  livres et élèves (`Title`, `First name`…), valeurs stockées des `choices`.
- Code (identifiants, docstrings existantes) en anglais comme le projet d'origine ;
  commentaires nouveaux en anglais ou en français, au choix du fichier.
- Planches d'étiquettes : A4, 3 × 8 étiquettes de 70 × 37 mm
  (`templates/library/label_sheet.html`, constantes `LABEL_COLUMNS/ROWS` dans `views.py`).
- Tests : pytest + pytest-django, objets créés directement avec l'ORM.
  Les critères de validation du cahier des charges (tests 1 à 8) vivent dans
  `tests/test_cahier_des_charges.py`.
- Un commit par fonctionnalité, message en français (Conventional Commits),
  tests verts à chaque commit. Toute modification de modèle vient avec sa
  migration ; les migrations qui transforment des données ont un test.

## Repères dans le code

- `library/models.py` : Book, Copy, Borrower, SchoolClass, SchoolYear, Loan, SchoolProfile.
- `library/views.py` : `_perform_circulation` (prêt/retour), `checkout`, `return_copy`,
  `photo_circulation` (borne pour les enfants), `delete_book`/`delete_copy` (retrait
  logique), `class_label_sheet`/`copy_label_sheet`, assistant `school_year_new`.
- `library/school_year.py` : logique du passage d'année.
- Remotes git : `origin` = ce dépôt, `upstream` = mrueda/shelf-school ; le tag
  `upstream-base` marque le commit d'origine du fork.
