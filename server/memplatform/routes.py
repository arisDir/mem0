import logging
from typing import Any, Dict, List, Optional

import server_state
from auth import require_admin, verify_auth
from errors import upstream_error
from fastapi import APIRouter, Body, Depends, HTTPException, Path
from pydantic import BaseModel

from .filters import platform_filters_to_oss
from .links import ping_payload, wrap_results

logger = logging.getLogger("memplatform.routes")

router = APIRouter(tags=["platform-compat"])


def _client_error(message: str) -> HTTPException:
    return HTTPException(status_code=400, detail=message)


class Message(BaseModel):
    role: str
    content: str


class MemoryAddRequest(BaseModel):
    messages: List[Message]
    user_id: Optional[str] = None
    agent_id: Optional[str] = None
    run_id: Optional[str] = None
    metadata: Optional[Dict[str, Any]] = None
    expiration_date: Optional[str] = None
    infer: Optional[bool] = None
    memory_type: Optional[str] = None
    prompt: Optional[str] = None

    model_config = {"extra": "allow"}


class MemorySearchRequest(BaseModel):
    query: str
    filters: Optional[Dict[str, Any]] = None
    top_k: Optional[int] = None
    limit: Optional[int] = None
    threshold: Optional[float] = None
    rerank: Optional[bool] = None
    reranker: Optional[Dict[str, Any]] = None

    model_config = {"extra": "allow"}


class MemoryListRequest(BaseModel):
    filters: Optional[Dict[str, Any]] = None
    user_id: Optional[str] = None
    agent_id: Optional[str] = None
    run_id: Optional[str] = None
    top_k: Optional[int] = None
    show_expired: Optional[bool] = None

    model_config = {"extra": "allow"}


class MemoryUpdateRequest(BaseModel):
    text: Optional[str] = None
    metadata: Optional[Dict[str, Any]] = None
    expiration_date: Optional[str] = None

    model_config = {"extra": "allow"}


class MemoryDeleteAllRequest(BaseModel):
    user_id: Optional[str] = None
    agent_id: Optional[str] = None
    run_id: Optional[str] = None

    model_config = {"extra": "allow"}


@router.get("/v1/ping/", summary="Platform ping (compat)")
def ping(_auth=Depends(verify_auth)):
    try:
        return ping_payload(_auth)
    except Exception as e:
        raise upstream_error(e)


@router.post("/v3/memories/add/", summary="Add memory (platform compat)")
def add_memory(
    req: MemoryAddRequest,
    _auth=Depends(verify_auth),
):
    try:
        params = req.model_dump(exclude_unset=True)
        return server_state.get_memory_instance().add(**params)
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e))
    except Exception as e:
        raise upstream_error(e)


@router.post("/v3/memories/search/", summary="Search memories (platform compat)")
def search_memories(
    req: MemorySearchRequest,
    _auth=Depends(verify_auth),
):
    try:
        filters = platform_filters_to_oss(req.filters)
        params = req.model_dump(exclude_unset=True)
        params["filters"] = filters
        return server_state.get_memory_instance().search(
            query=params.pop("query"),
            **params,
        )
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e))
    except Exception as e:
        raise upstream_error(e)


@router.post("/v3/memories/", summary="List memories (platform compat)")
def list_memories(
    req: MemoryListRequest = Body(default_factory=MemoryListRequest),
    _auth=Depends(verify_auth),
):
    try:
        filters = platform_filters_to_oss(req.filters)
        params = req.model_dump(exclude_unset=True)
        params["filters"] = filters
        results = server_state.get_memory_instance().get_all(**params)
        if isinstance(results, dict) and "results" in results:
            return wrap_results(results["results"])
        if isinstance(results, list):
            return wrap_results(results)
        try:
            return wrap_results(list(results))
        except Exception:
            return results
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e))
    except Exception as e:
        raise upstream_error(e)


@router.get("/v1/memories/{memory_id}/", summary="Get memory (platform compat)")
def get_memory(
    memory_id: str = Path(...),
    _auth=Depends(verify_auth),
):
    try:
        return server_state.get_memory_instance().get(memory_id)
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e))
    except Exception as e:
        raise upstream_error(e)


@router.put("/v1/memories/{memory_id}/", summary="Update memory (platform compat)")
def update_memory(
    memory_id: str = Path(...),
    req: MemoryUpdateRequest = Body(...),
    _auth=Depends(verify_auth),
):
    try:
        params = req.model_dump(exclude_unset=True)
        params["memory_id"] = memory_id
        return server_state.get_memory_instance().update(**params)
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e))
    except Exception as e:
        raise upstream_error(e)


@router.delete("/v1/memories/{memory_id}/", summary="Delete memory (platform compat)")
def delete_memory(
    memory_id: str = Path(...),
    _auth=Depends(verify_auth),
):
    try:
        return server_state.get_memory_instance().delete(memory_id=memory_id)
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e))
    except Exception as e:
        raise upstream_error(e)


@router.delete("/v1/memories/", summary="Delete all memories (platform compat)")
def delete_all_memories(
    req: MemoryDeleteAllRequest = Body(default_factory=MemoryDeleteAllRequest),
    _auth=Depends(require_admin),
):
    try:
        params = req.model_dump(exclude_unset=True)
        return server_state.get_memory_instance().delete_all(**params)
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e))
    except Exception as e:
        raise upstream_error(e)


@router.get("/v1/memories/{memory_id}/history/", summary="Get memory history (platform compat)")
def get_memory_history(
    memory_id: str = Path(...),
    _auth=Depends(verify_auth),
):
    try:
        return server_state.get_memory_instance().history(memory_id=memory_id)
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e))
    except Exception as e:
        raise upstream_error(e)


@router.get("/v1/entities/", summary="List entities (platform compat)")
def list_entities(
    _auth=Depends(verify_auth),
):
    try:
        results = server_state.get_memory_instance().get_all()
    except Exception as e:
        raise upstream_error(e)

    if isinstance(results, dict) and "results" in results:
        return wrap_results(results["results"])
    if isinstance(results, list):
        return wrap_results(results)
    try:
        return wrap_results(list(results))
    except Exception:
        return wrap_results([])
