"""GET /policies — list all available policies for the UI selector."""
from fastapi import APIRouter
from pydantic import BaseModel

from app.policies.registry import policy_specs

router = APIRouter()


class PolicyInfo(BaseModel):
    id: str
    label: str
    description: str
    is_default: bool = False


@router.get("/policies", response_model=list[PolicyInfo])
def list_policies() -> list[PolicyInfo]:
    return [
        PolicyInfo(
            id=spec.id,
            label=spec.label,
            description=spec.description,
            is_default=spec.is_default,
        )
        for spec in policy_specs(include_hidden=False)
    ]
