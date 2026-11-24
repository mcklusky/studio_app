"""Retry-safe writes.

Usage inside a view:

    return run_idempotent(request, organization=org, scope="sales.create",
                          handler=lambda: Response(post_sale(...), status=201))

* Same key + same request  -> the stored response is replayed (header Idempotent-Replayed: true).
* Same key + different body -> 409 conflict.
* The handler and the stored record commit in one transaction, so a failed
  handler leaves nothing behind and the client may retry with the same key.
"""

import hashlib
import json

from django.db import IntegrityError, transaction
from rest_framework.exceptions import ValidationError
from rest_framework.response import Response
from rest_framework.utils.encoders import JSONEncoder

from apps.common.exceptions import Conflict
from apps.common.models import IdempotencyRecord

HEADER = "Idempotency-Key"
MAX_KEY_LENGTH = 100


def request_fingerprint(request):
    body = json.dumps(request.data, sort_keys=True, cls=JSONEncoder, default=str)
    raw = f"{request.method}\n{request.path}\n{body}".encode()
    return hashlib.sha256(raw).hexdigest()


def _replay(record, request_hash):
    if record.request_hash != request_hash:
        raise Conflict("This Idempotency-Key was already used for a different request.")
    response = Response(record.response_body, status=record.response_status)
    response["Idempotent-Replayed"] = "true"
    return response


def run_idempotent(request, *, organization, scope, handler, required=False):
    key = (request.headers.get(HEADER) or "").strip()
    if not key:
        if required:
            raise ValidationError({HEADER: ["This operation requires an Idempotency-Key header."]})
        with transaction.atomic():
            return handler()
    if len(key) > MAX_KEY_LENGTH:
        raise ValidationError({HEADER: [f"Use at most {MAX_KEY_LENGTH} characters."]})

    request_hash = request_fingerprint(request)
    lookup = {"organization": organization, "scope": scope, "key": key}
    existing = IdempotencyRecord.objects.filter(**lookup).first()
    if existing:
        return _replay(existing, request_hash)

    try:
        with transaction.atomic():
            response = handler()
            if 200 <= response.status_code < 300:
                body = json.loads(json.dumps(response.data, cls=JSONEncoder))
                IdempotencyRecord.objects.create(
                    **lookup,
                    user=request.user,
                    request_hash=request_hash,
                    response_status=response.status_code,
                    response_body=body,
                )
            return response
    except IntegrityError:
        # A concurrent request with the same key won; our work was rolled back.
        winner = IdempotencyRecord.objects.filter(**lookup).first()
        if winner is None:
            raise
        return _replay(winner, request_hash)
