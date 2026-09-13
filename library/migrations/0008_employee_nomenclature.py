from django.db import migrations, models


def rename_school_role(apps, schema_editor):
    Borrower = apps.get_model("library", "Borrower")
    Borrower.objects.using(schema_editor.connection.alias).filter(
        school_role="staff"
    ).update(school_role="employee")


class Migration(migrations.Migration):
    dependencies = [("library", "0007_staff_positions")]

    operations = [
        migrations.RenameModel(old_name="StaffPosition", new_name="EmployeePosition"),
        migrations.RunPython(rename_school_role),
        migrations.AlterField(
            model_name="borrower",
            name="school_role",
            field=models.CharField(
                choices=[("student", "Student"), ("employee", "Employee")],
                default="student",
                max_length=16,
            ),
        ),
    ]
