from django.urls import path

from . import views


urlpatterns = [
    path("", views.dashboard, name="dashboard"),
    path("books/", views.book_list, name="book_list"),
    path("books/add/", views.book_create, name="book_create"),
    path("books/photo-intake/", views.photo_intake, name="photo_intake"),
    path("books/import/", views.import_books, name="import_books"),
    path("books/export.csv", views.export_books_csv, name="export_books_csv"),
    path("books/<uuid:pk>/", views.book_detail, name="book_detail"),
    path("books/<uuid:book_pk>/copies/add/", views.add_copy, name="add_copy"),
    path("copies/<uuid:pk>/", views.copy_detail, name="copy_detail"),
    path("borrowers/", views.borrower_list, name="borrower_list"),
    path("borrowers/add/", views.borrower_create, name="borrower_create"),
    path("borrowers/<uuid:pk>/", views.borrower_detail, name="borrower_detail"),
    path("circulation/", views.photo_circulation, name="photo_circulation"),
    path("checkout/", views.checkout, name="checkout"),
    path("return/", views.return_copy, name="return_copy"),
    path("labels/<str:kind>/<uuid:pk>/", views.label, name="label"),
    path("backup/sqlite/", views.backup_sqlite, name="backup_sqlite"),
]
