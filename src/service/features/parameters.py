from pydantic import BaseModel


class BaseParameters(BaseModel):
    """Base class for all service parameters.

    Specific services should subclass this to define their own
    parameters.
    """
    pass
