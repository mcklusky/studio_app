from django.db import transaction

from apps.common.models import DocumentSequence


def next_number(organization, key, width=4):
    """Allocate the next number for `key` (e.g. "PO" -> "PO-0001"). Call inside the posting transaction
    so a rolled-back document does not consume its number."""
    with transaction.atomic():
        sequence, _ = DocumentSequence.objects.select_for_update().get_or_create(organization=organization, key=key)
        value = sequence.next_value
        sequence.next_value = value + 1
        sequence.save(update_fields=["next_value"])
    return f"{key}-{value:0{width}d}"
