import pickle
import uuid

import ibis
import redis
from pydantic_ai import ModelRetry, RunContext

from deps import Deps

PREFIX = "expr"

def _prefix(ctx: RunContext[Deps]) -> str:
    if ctx.conversation_id is None:
        raise RuntimeError("conversation_id mancante: il tool non è in una run dell'agent")
    return f"{PREFIX}:{ctx.conversation_id}:"

def save_expr(ctx: RunContext[Deps], expr: ibis.Expr) -> str:
    key = f"{_prefix(ctx)}{uuid.uuid4().hex[:12]}"
    payload = pickle.dumps(expr.unbind())
    try:
        ctx.deps.valkey.set(key, payload, ex=ctx.deps.expr_ttl)
    except redis.ConnectionError as e:
        raise RuntimeError("Valkey non raggiungibile") from e
    return key


def load_expr(ctx: RunContext[Deps], key: str) -> ibis.Table:
    if not key.startswith(_prefix(ctx)):
        raise ModelRetry(
            f"Chiave non valida: {key!r}. Usa la chiave restituita da get_table o filter_table."
        )
    data = ctx.deps.valkey.get(key)
    if data is None:
        raise ModelRetry(
            f"Espressione {key} non trovata o scaduta. Richiama get_table."
        )
    assert isinstance(data, bytes)
    return pickle.loads(data)

def check_key(ctx: RunContext[Deps], key: str) -> bool:
    data: bytes | str | None = ctx.deps.valkey.get(name=key)
    return data is not None

