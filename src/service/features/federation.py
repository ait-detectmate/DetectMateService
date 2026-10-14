from dataclasses import dataclass
from typing import Optional


@dataclass
class FederationState:
    """Service-side bookkeeping for stack-later federation rounds.

    The library keeps the stacked peers itself; this only tracks what
    the HTTP API needs to report and guard against.
    """
    stacked_peers: int = 0
    rounds_aggregated: int = 0
    last_aggregated_at: Optional[str] = None
    finalized: bool = False
