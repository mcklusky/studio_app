"""Uniform error envelope: {"error": {code, message, field_errors, request_id}}."""

import logging

from django.core.exceptions import PermissionDenied as DjangoPermissionDenied
from django.http import Http404
from rest_framework import exceptions, status
from rest_framework.response import Response
from rest_framework.views import exception_handler as drf_exception_handler

from apps.common.middleware import get_request_id

logger = logging.getLogger(__name__)


class Conflict(exceptions.APIException):
    status_code = status.HTTP_409_CONFLICT
    default_detail = "This request conflicts with the current state of the record."
    default_code = "conflict"


MESSAGES = {
    "validation_error": "Review the highlighted fields.",
    "not_authenticated": "Sign in to continue.",
    "authentication_failed": "Sign in to continue.",
    "permission_denied": "You do not have permission to perform this action.",
    "not_found": "The record was not found.",
    "method_not_allowed": "This action is not available.",
    "throttled": "Too many attempts. Wait a moment and try again.",
}


def _flatten(detail, prefix=""):
    """Turn nested DRF error detail into {"items.0.quantity": ["..."]}."""
    flat = {}
    if isinstance(detail, dict):
        for key, value in detail.items():
            flat.update(_flatten(value, f"{prefix}.{key}" if prefix else str(key)))
    elif isinstance(detail, list):
        if all(not isinstance(item, (dict, list)) for item in detail):
            flat[prefix or "non_field_errors"] = [str(item) for item in detail]
        else:
            for index, item in enumerate(detail):
                flat.update(_flatten(item, f"{prefix}.{index}" if prefix else str(index)))
    else:
        flat[prefix or "non_field_errors"] = [str(detail)]
    return flat


def api_exception_handler(exc, context):
    request = context.get("request")
    request_id = get_request_id(request) if request is not None else None

    if isinstance(exc, Http404):
        exc = exceptions.NotFound()
    elif isinstance(exc, DjangoPermissionDenied):
        exc = exceptions.PermissionDenied()

    response = drf_exception_handler(exc, context)
    if response is None:
        logger.exception("Unhandled API error", extra={"request_id": request_id})
        return Response(
            {
                "error": {
                    "code": "server_error",
                    "message": "Something went wrong. Try again, and contact an administrator if it continues.",
                    "field_errors": {},
                    "request_id": request_id,
                }
            },
            status=status.HTTP_500_INTERNAL_SERVER_ERROR,
        )

    if isinstance(exc, exceptions.ValidationError):
        code = "validation_error"
        field_errors = _flatten(exc.detail)
        non_field = field_errors.get("non_field_errors")
        message = non_field[0] if non_field and len(field_errors) == 1 else MESSAGES[code]
    else:
        codes = exc.get_codes() if isinstance(exc, exceptions.APIException) else None
        code = codes if isinstance(codes, str) else "error"
        field_errors = {}
        detail = getattr(exc, "detail", None)
        message = str(detail) if isinstance(detail, str) and detail else MESSAGES.get(code, "The request could not be completed.")

    response.data = {"error": {"code": code, "message": message, "field_errors": field_errors, "request_id": request_id}}
    return response
