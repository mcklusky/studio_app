import threading
import uuid

_local = threading.local()

REQUEST_ID_HEADER = "X-Request-ID"


def _valid_request_id(value):
    try:
        return str(uuid.UUID(str(value)))
    except (TypeError, ValueError):
        return None


class RequestIDMiddleware:
    """Attach a correlation ID to every request and echo it on the response.

    A client-supplied ID is accepted only if it is a well-formed UUID, so log
    lines and audit rows cannot be polluted with arbitrary text.
    """

    def __init__(self, get_response):
        self.get_response = get_response

    def __call__(self, request):
        request.request_id = _valid_request_id(request.headers.get(REQUEST_ID_HEADER)) or str(uuid.uuid4())
        _local.request_id = request.request_id
        try:
            response = self.get_response(request)
        finally:
            _local.request_id = None
        response[REQUEST_ID_HEADER] = request.request_id
        return response


def get_request_id(request):
    return getattr(request, "request_id", None) or getattr(getattr(request, "_request", None), "request_id", None)


def current_request_id():
    return getattr(_local, "request_id", None)
