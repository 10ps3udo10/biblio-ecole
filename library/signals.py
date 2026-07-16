from django.contrib.auth import get_user_model
from django.db.models.signals import post_delete, post_save
from django.dispatch import receiver

from .models import Book, Borrower


@receiver(post_delete, sender=Book)
def delete_book_cover_file(sender, instance, **kwargs):
    if instance.cover_image:
        instance.cover_image.delete(save=False)


@receiver(post_save, sender=get_user_model())
def ensure_staff_borrower_profile(sender, instance, **kwargs):
    if not instance.is_staff:
        return
    if not instance.first_name:
        sender.objects.filter(pk=instance.pk).update(first_name=instance.username)
        instance.first_name = instance.username
    borrower = getattr(instance, "borrower_profile", None)
    if borrower is None:
        borrower = Borrower.objects.filter(username=instance.username, staff_account__isnull=True).first()
    if borrower is None:
        borrower = Borrower(staff_account=instance, class_name="Staff")
    borrower.staff_account = instance
    borrower.username = instance.username
    borrower.first_name = instance.first_name
    borrower.last_name = instance.last_name
    borrower.email = instance.email
    borrower.save()
