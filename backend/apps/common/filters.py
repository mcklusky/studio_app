from datetime import date

from rest_framework.exceptions import ValidationError


def date_param(request, name):
    """Parse an optional YYYY-MM-DD query parameter or raise a 400."""
    value = request.query_params.get(name)
    if not value:
        return None
    try:
        return date.fromisoformat(value)
    except ValueError as exc:
        raise ValidationError({name: ["Use the date format YYYY-MM-DD."]}) from exc
