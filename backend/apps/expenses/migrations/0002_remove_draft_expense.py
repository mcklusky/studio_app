"""Replace the draft-style Expense with the posted/reversal model.

Safe because no expenses were ever recorded before this change (the old model had
no API path to posting). 0003 creates the new table.
"""
from django.db import migrations


def refuse_if_data(apps, schema_editor):
    Expense = apps.get_model("expenses", "Expense")
    if Expense.objects.exists():
        raise RuntimeError("Expenses exist; write a data migration instead of dropping the table.")


class Migration(migrations.Migration):
    dependencies = [("expenses", "0001_initial")]

    operations = [
        migrations.RunPython(refuse_if_data, migrations.RunPython.noop),
        migrations.DeleteModel(name="Expense"),
    ]
