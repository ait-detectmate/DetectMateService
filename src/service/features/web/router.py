from fastapi import APIRouter, Depends
from typing import Any, Dict
from pydantic import BaseModel

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
