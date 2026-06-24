import io
import zipfile

from fastapi import APIRouter, Depends, File, HTTPException, UploadFile
from fastapi.responses import StreamingResponse
from typing import Any, Dict, Literal, cast
from pydantic import BaseModel

from detectmatelibrary.utils.persistency import PersistencyLoadError

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


class TrainingStatePayload(BaseModel):
    state: Literal[
        "keep_training", "stop_training", "keep_configuring", "stop_configuring"
    ]


def _get_component(service: Any) -> Any:
    """Return the library component, or raise HTTPException 404."""
    component = getattr(service, "library_component", None)
    if component is None:
        raise HTTPException(status_code=404, detail="No library component loaded")
    return component


def _get_saver(service: Any) -> Any:
    """Return the PersistencySaver from the service's library component.

    Raises HTTPException 404 if the component is missing or persistency
    is not configured.
    """
    component = _get_component(service)
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
    if getattr(service, "_running", False):
        raise HTTPException(
            status_code=409,
            detail="Stop the engine before loading state (/admin/stop)",
        )
    saver = _get_saver(service)
    try:
        saver.load()
    except PersistencyLoadError as e:
        raise HTTPException(status_code=404, detail=str(e))
    return {"message": "state loaded"}


@router.get("/persistency/status")  # type: ignore[misc]
async def admin_persistency_status(service: Any = Depends(get_service)) -> Dict[str, Any]:
    return cast(Dict[str, Any], _get_saver(service).get_status())


@router.get("/persistency/export")  # type: ignore[misc]
async def admin_persistency_export(service: Any = Depends(get_service)) -> StreamingResponse:
    """Stream the current learned state as a zip archive."""
    component = _get_component(service)
    data = component.export_state()
    if data is None:
        raise HTTPException(status_code=404, detail="Persistency not configured for this component")
    name = getattr(component, "name", "state")
    return StreamingResponse(
        io.BytesIO(data),
        media_type="application/zip",
        headers={"Content-Disposition": f'attachment; filename="{name}_state.zip"'},
    )


@router.post("/persistency/import")  # type: ignore[misc]
async def admin_persistency_import(
    service: Any = Depends(get_service),
    file: UploadFile = File(...),
) -> Dict[str, Any]:
    """Restore learned state from an uploaded zip archive."""
    if getattr(service, "_running", False):
        raise HTTPException(
            status_code=409,
            detail="Stop the engine before importing state (/admin/stop)",
        )
    component = _get_component(service)
    data = await file.read()
    if not zipfile.is_zipfile(io.BytesIO(data)):
        raise HTTPException(status_code=422, detail="Uploaded file is not a valid zip archive")
    with zipfile.ZipFile(io.BytesIO(data)) as zf:
        if "metadata.json" not in zf.namelist():
            raise HTTPException(status_code=422, detail="Invalid state archive: metadata.json not found")
    try:
        component.import_state(data)
    except PersistencyLoadError as e:
        raise HTTPException(status_code=422, detail=str(e))
    return {"message": "state imported"}


@router.post("/training/state")  # type: ignore[misc]
async def admin_training_set_state(
    payload: TrainingStatePayload, service: Any = Depends(get_service)
) -> Dict[str, Any]:
    """Override the fit logic training/configuration state on the library
    component."""
    component = _get_component(service)
    component.update_state(payload.state)
    return {"message": f"state updated to: {payload.state}"}


@router.get("/training/state")  # type: ignore[misc]
async def admin_training_get_state(service: Any = Depends(get_service)) -> Dict[str, Any]:
    """Return the fit logic state from the last processed message."""
    component = _get_component(service)
    return {"state": component.get_state()}
