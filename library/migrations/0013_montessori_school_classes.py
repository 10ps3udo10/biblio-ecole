from django.db import migrations


MONTESSORI_CLASSES = (
    "Assistants to Infancy (0-3)",
    "Children's House (3-6)",
    "Lower Elementary (6-9)",
    "Upper Elementary (9-12)",
    "Adolescent (12-18)",
)


def add_montessori_classes(apps, schema_editor):
    SchoolClass = apps.get_model("library", "SchoolClass")
    Borrower = apps.get_model("library", "Borrower")
    old_adolescent = SchoolClass.objects.filter(name__iexact="Adolescent").first()
    adolescent, _ = SchoolClass.objects.get_or_create(name="Adolescent (12-18)")
    if old_adolescent and old_adolescent.pk != adolescent.pk:
        Borrower.objects.filter(school_class=old_adolescent).update(school_class=adolescent)
        old_adolescent.delete()
    for name in MONTESSORI_CLASSES[:-1]:
        SchoolClass.objects.get_or_create(name=name)


class Migration(migrations.Migration):
    dependencies = [("library", "0012_generated_borrower_ids")]

    operations = [migrations.RunPython(add_montessori_classes, migrations.RunPython.noop)]
