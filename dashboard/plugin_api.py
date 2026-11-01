"""Authenticated Hermes plugin API; no standalone server or credential store."""
import importlib.util
from pathlib import Path

from fastapi import APIRouter
from pydantic import BaseModel, ConfigDict, Field

_spec = importlib.util.spec_from_file_location(
    "hermes_github_projects_backend", Path(__file__).resolve().parents[1] / "github_projects.py"
)
if _spec is None or _spec.loader is None:
    raise ImportError("Cannot load GitHub Projects service")
_service = importlib.util.module_from_spec(_spec)
_spec.loader.exec_module(_service)
router = APIRouter()


class Call(BaseModel):
    model_config = ConfigDict(extra="forbid")
    operation: str = Field(min_length=1, max_length=40)
    arguments: dict = Field(default_factory=dict)


@router.post("/call")
def call(request: Call):
    # Sync route runs blocking gh work in FastAPI's thread pool, not the event loop.
    try:
        return {"ok": True, "data": _service.execute(request.operation, request.arguments)}
    except _service.GitHubError as exc:
        return {"ok": False, "error": str(exc)}
    except Exception:
        return {"ok": False, "error": "Unexpected plugin failure. Refresh GitHub before retrying any write."}
