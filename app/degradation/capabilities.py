from pathlib import Path
from typing import Annotated, Literal

from pydantic import BaseModel, ConfigDict, Field, StringConstraints, field_validator
import yaml

from app.degradation.layers import OnionLayer


Identifier = Annotated[str, StringConstraints(strict=True, pattern=r'^[a-z][a-z0-9_.-]*$')]
Message = Annotated[str, StringConstraints(strict=True, strip_whitespace=True, min_length=1)]
CAPABILITIES_DIR = Path(__file__).resolve().parents[2] / 'capabilities'


class CapabilityContract(BaseModel):
    model_config = ConfigDict(extra='forbid', frozen=True)

    id: Identifier
    name: Message
    layer: OnionLayer
    implementation_status: Literal['implemented', 'planned']
    requires: list[Identifier]
    enhances: list[Identifier]
    fallbacks: list[Identifier] = Field(min_length=1)
    minimum_viable_mode: list[Identifier] = Field(min_length=1)
    operator_messages: dict[Identifier, Message] = Field(min_length=1)

    @field_validator('requires', 'enhances', 'fallbacks', 'minimum_viable_mode')
    @classmethod
    def unique_references(cls, value: list[str]) -> list[str]:
        if len(value) != len(set(value)):
            raise ValueError('capability references must be unique')
        return value


def load_capabilities(directory: Path = CAPABILITIES_DIR) -> tuple[CapabilityContract, ...]:
    paths = sorted(set(directory.glob('*.yaml')) | set(directory.glob('*.yml')))
    if not paths:
        raise ValueError(f'No capability contracts found in {directory}')
    contracts: list[CapabilityContract] = []
    ids: set[str] = set()
    for path in paths:
        try:
            contract = CapabilityContract.model_validate(yaml.safe_load(path.read_text(encoding='utf-8')))
            if contract.id in ids:
                raise ValueError(f'Duplicate capability ID: {contract.id}')
        except (OSError, ValueError, yaml.YAMLError) as exc:
            raise ValueError(f'Invalid capability contract {path.name}: {exc}') from exc
        ids.add(contract.id)
        contracts.append(contract)
    return tuple(contracts)

