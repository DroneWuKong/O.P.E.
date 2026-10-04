from fastapi import APIRouter, Depends, Request
from pydantic import BaseModel

from app.auth import require_api_key
from app.degradation.capabilities import CapabilityContract


router = APIRouter(prefix='/system', tags=['system'], dependencies=[Depends(require_api_key)])


class CapabilitiesResponse(BaseModel):
    capabilities: list[CapabilityContract]


@router.get('/capabilities', response_model=CapabilitiesResponse)
def capabilities(request: Request) -> CapabilitiesResponse:
    # Contracts describe dependencies and intended fallback paths. They are not
    # observations of live availability or a claim that a fallback was executed.
    return CapabilitiesResponse(capabilities=list(request.app.state.capability_registry))

