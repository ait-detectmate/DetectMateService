from abc import abstractmethod


class BaseProcessor:
    @abstractmethod  # ensure that anything that inherits from BasicProcessor has a process() method
    def __call__(self, _raw_message: bytes) -> bytes | None:
        """Decode raw_message, run parser(s)/detector(s), and return something
        to publish (or None to skip)."""
        pass


class ProcessorException(Exception):
    """Custom exception for processor-related errors."""
    pass
