import logging
import secrets
from typing import Any, Optional

from fastapi import Depends, HTTPException, Request, status
from fastapi.security import APIKeyHeader

API_KEY_HEADER_NAME = "X-Auth-Token"
api_key_header = APIKeyHeader(name=API_KEY_HEADER_NAME, auto_error=False)

logger = logging.getLogger(__name__)


def get_service() -> Any:
    # This gets overridden by the server setup in server.py
    raise NotImplementedError


def require_api_key(
    request: Request,
    token: Optional[str] = Depends(api_key_header),
    service: Any = Depends(get_service),
) -> None:
    """Reject the request if X-Auth-Token does not match settings.http_api_key.

    no key configured means no auth required.
    """
    expected = service.settings.http_api_key
    if expected is None:
        return
    if token is None or not secrets.compare_digest(
        token.encode(), expected.get_secret_value().encode()
    ):
        client_host = request.client.host if request.client else "unknown"
        logger.warning("Rejected unauthenticated admin request from %s to %s", client_host, request.url.path)
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Invalid authentication credentials",
        )
