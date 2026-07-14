import logging
import sys


class RequestIdFilter(logging.Filter):
    def filter(self, record: logging.LogRecord) -> bool:
        if not hasattr(record, "request_id"):
            record.request_id = "-"
        return True


def configure_logging(level: str) -> None:
    logging.basicConfig(
        level=getattr(logging, level.upper(), logging.INFO),
        format="%(asctime)s %(levelname)s %(name)s request_id=%(request_id)s %(message)s",
        stream=sys.stdout,
    )
    for handler in logging.getLogger().handlers:
        handler.addFilter(RequestIdFilter())


def get_logger(name: str) -> logging.Logger:
    return logging.getLogger(name)
