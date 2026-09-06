import ibis
import redis
from pydantic import ConfigDict, Field
from pydantic.dataclasses import dataclass


@dataclass(config=ConfigDict(arbitrary_types_allowed=True))
class Deps:
    """Per-run dependencies, injected into tools via RunContext[Deps]."""

    con: ibis.BaseBackend
    valkey: redis.Redis
    allowed_tables: list[str] = Field(..., min_length=1)
    allowed_domains: list[str] = Field(..., min_length=1)
    decimals: int = Field(2, ge=0)
    expr_limit: int = 10
    expr_ttl: int = Field(
        3600, gt=0, description="seconds before a stored expression expires"
    )
