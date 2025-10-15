from pydantic import BaseModel


class BaseConfig(BaseModel):
    """Base class for all service config.

    Specific services should subclass this to define their own
    parameters.
    """
    pass


# this part is for testing only, to ensure the status returns the parameters
#
# because the BaseConfig class is empty, so when Pydantic validates the data
# from the YAML file against this schema, it ignores all the fields
#
# in the core.py , the get_config_schema function should return this class
# TODO: remove, this is part of the library?
# from pydantic import Field
# class DetectorParameters(BaseConfig):
#    """Parameters for a detector service."""
#    threshold: float = Field(0.5, ge=0.0, le=1.0, description="Detection threshold")
#    window_size: int = Field(10, ge=1, description="Window size for detection")
#    enabled: bool = Field(True, description="Whether the detector is enabled")
