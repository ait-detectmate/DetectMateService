import json
import logging

from fastapi import APIRouter, Depends, HTTPException
from typing import Any, Dict, Optional
from pydantic import BaseModel

from detectmatelibrary.utils.persistency import PersistencyLoadError

_log = logging.getLogger(__name__)

router = APIRouter(prefix="/admin")


class ReconfigPayload(BaseModel):
    config: Dict[str, Any]
    persist: bool = False


def get_service() -> Any:
    # This gets overridden by the server setup in server.py
    raise NotImplementedError


@router.post("/start")  # type: ignore[misc]
async def admin_start(service: Any = Depends(get_service)) -> Dict[str, Any]:
    return {"message": service.start()}


@router.post("/stop")  # type: ignore[misc]
async def admin_stop(service: Any = Depends(get_service)) -> Dict[str, Any]:
    return {"message": service.stop()}


@router.get("/status")  # type: ignore[misc]
async def admin_status(service: Any = Depends(get_service)) -> Any:
    return service._create_status_report(getattr(service, "_running", False))


@router.post("/reconfigure")  # type: ignore[misc]
async def admin_reconfigure(payload: ReconfigPayload, service: Any = Depends(get_service)) -> Dict[str, Any]:
    # format the string to match what internal reconfigure() expects
    result = service.reconfigure(
        config_data=payload.config,
        persist=payload.persist
    )
    return {"message": result}


@router.post("/shutdown")  # type: ignore[misc]
async def admin_shutdown(service: Any = Depends(get_service)) -> Dict[str, Any]:
    # Kills the entire process
    return {"message": service.shutdown()}


def _get_saver(service: Any) -> Any:
    """Return the PersistencySaver from the service's library component.

    Raises HTTPException 404 if the component is missing or persistency
    is not configured.
    """
    component = getattr(service, "library_component", None)
    if component is None:
        raise HTTPException(status_code=404, detail="No library component loaded")
    saver = getattr(component, "saver", None)
    if saver is None:
        raise HTTPException(status_code=404, detail="Persistency not configured for this component")
    return saver


@router.post("/persistency/save")  # type: ignore[misc]
async def admin_persistency_save(service: Any = Depends(get_service)) -> Dict[str, Any]:
    """Force an immediate flush of in-memory state to storage."""
    saver = _get_saver(service)
    saver.save()
    return {"message": "state saved"}


@router.post("/persistency/load")  # type: ignore[misc]
async def admin_persistency_load(service: Any = Depends(get_service)) -> Dict[str, Any]:
    """Restore state from storage, replacing current in-memory state."""
    saver = _get_saver(service)
    try:
        saver.load()
    except PersistencyLoadError as e:
        raise HTTPException(status_code=404, detail=str(e))
    return {"message": "state loaded"}


@router.get("/persistency/status")  # type: ignore[misc]
async def admin_persistency_status(service: Any = Depends(get_service)) -> Dict[str, Any]:
    """Return current persistency state: config, in-memory counters, and last
    save timestamp (read from metadata.json if present)."""
    saver = _get_saver(service)
    ep = saver._persistency

    last_saved_at: Optional[str] = None
    try:
        meta_path = f"{saver._root}/metadata.json"
        if saver._fs.exists(meta_path):
            with saver._fs.open(meta_path, "r") as f:
                meta = json.load(f)
            last_saved_at = meta.get("saved_at")
    except Exception as e:
        _log.warning("persistency/status: could not read metadata.json — %s", e)

    return {
        "path": saver._config.path,
        "save_interval_seconds": saver._config.save_interval_seconds,
        "events_until_save": saver._config.events_until_save,
        "auto_load": saver._config.auto_load,
        "events_seen_count": len(ep.get_events_seen()),
        "events_with_data_count": len(ep.get_events_data()),
        "events_since_save": ep._events_since_save,
        "last_saved_at": last_saved_at,
    }
