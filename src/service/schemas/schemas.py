from pydantic import BaseModel, Field
from typing import List, Dict, Any


class Schema(BaseModel):
    __version__: str = "1.0.0"


class LogSchema(Schema):
    logID: int = 0
    log: str = ""
    logSource: str = "example-source"
    hostname: str = "example.com"


class ParserSchema(Schema):
    parserType: str = ""
    EventID: int = 0
    template: str = ""
    variables: List[Any] = Field(default_factory=list)
    parserID: int = 0
    logID: int = 0
    log: str = ""
    logFormatVariables: Dict[str, Any] = Field(default_factory=dict)


class DetectorSchema(Schema):
    detectorID: str = ""
    detectorType: str = ""
    alertID: int = 0
    detectionTimestamp: int = 0
    logID: List[int] = Field(default_factory=list)
    predictionLabel: bool = False
    score: float = 0.2
    extractedTimestamps: List[str] = Field(default_factory=list)
