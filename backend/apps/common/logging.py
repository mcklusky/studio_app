import logging

from apps.common.middleware import current_request_id


class RequestIDFilter(logging.Filter):
    """Adds the current request ID to every log line so a user's error reference finds the log."""

    def filter(self, record):
        record.request_id = getattr(record, "request_id", None) or current_request_id() or "-"
        return True
