from django.db import migrations, models


class Migration(migrations.Migration):
    dependencies = [("library", "0003_schoolprofile")]

    operations = [
        migrations.AddField(
            model_name="schoolprofile",
            name="logo",
            field=models.ImageField(blank=True, upload_to="branding/"),
        ),
        migrations.AddField(
            model_name="schoolprofile",
            name="setup_completed",
            field=models.BooleanField(default=False),
        ),
    ]
