from typing import Protocol
import logging


class Loggable(Protocol):
    """Any class that provides a logger."""
    log: logging.Logger
