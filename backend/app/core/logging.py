import logging
import sys

_CONFIGURED = False


def configure_logging(level: int = logging.INFO) -> None:
    """
    Configure root logging once. JSON-ish structured output is overkill for
    B1; we use a plain format now and revisit when we add request IDs in B3.

    IMPORTANT (GDPR): never log chat message bodies, tokens, or passwords at
    INFO or below. Use DEBUG only in local dev for throwaway diagnostics.
    """
    global _CONFIGURED
    if _CONFIGURED:
        return

    handler = logging.StreamHandler(sys.stdout)
    handler.setFormatter(
        logging.Formatter(
            fmt="%(asctime)s %(levelname)-8s %(name)s :: %(message)s",
            datefmt="%Y-%m-%dT%H:%M:%S%z",
        )
    )

    root = logging.getLogger()
    root.setLevel(level)
    root.handlers = [handler]

    # Tame chatty libraries
    logging.getLogger("uvicorn.access").setLevel(logging.WARNING)
    logging.getLogger("sqlalchemy.engine").setLevel(logging.WARNING)

    _CONFIGURED = True
