from django.db.models.signals import post_delete
from django.dispatch import receiver

from .models import Book


@receiver(post_delete, sender=Book)
def delete_book_cover_file(sender, instance, **kwargs):
    if instance.cover_image:
        instance.cover_image.delete(save=False)
