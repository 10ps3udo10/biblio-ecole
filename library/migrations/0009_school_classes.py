from django.db import migrations, models
import django.db.models.deletion


def preserve_classes(apps, schema_editor):
    Borrower = apps.get_model("library", "Borrower")
    SchoolClass = apps.get_model("library", "SchoolClass")
    alias = schema_editor.connection.alias
    for borrower in Borrower.objects.using(alias).filter(school_role="student").exclude(class_name="").iterator():
        name = borrower.class_name.strip()
        if not name:
            continue
        school_class = SchoolClass.objects.using(alias).filter(name__iexact=name).first()
        if school_class is None:
            school_class = SchoolClass.objects.using(alias).create(name=name)
        Borrower.objects.using(alias).filter(pk=borrower.pk).update(school_class_id=school_class.pk)


class Migration(migrations.Migration):
    dependencies = [("library", "0008_employee_nomenclature")]

    operations = [
        migrations.CreateModel(
            name="SchoolClass",
            fields=[
                ("id", models.BigAutoField(auto_created=True, primary_key=True, serialize=False, verbose_name="ID")),
                ("name", models.CharField(max_length=120, unique=True)),
                ("active", models.BooleanField(default=True)),
            ],
            options={"ordering": ["name"], "verbose_name_plural": "school classes"},
        ),
        migrations.AddField(
            model_name="borrower",
            name="school_class",
            field=models.ForeignKey(blank=True, null=True, on_delete=django.db.models.deletion.PROTECT, related_name="borrowers", to="library.schoolclass", verbose_name="Class"),
        ),
        migrations.RunPython(preserve_classes),
        migrations.RemoveIndex(model_name="borrower", name="library_bor_class_ccb142_idx"),
        migrations.RemoveField(model_name="borrower", name="class_name"),
    ]
