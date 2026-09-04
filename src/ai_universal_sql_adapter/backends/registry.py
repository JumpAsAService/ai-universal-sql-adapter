from typing import Callable
from urllib.parse import quote

import ibis

from ai_universal_sql_adapter.config import DatabaseSettings

Operation = Callable[..., ibis.Table]



def build_dsn(config: DatabaseSettings) -> str:
    """Build an ibis connection URL, e.g.
    clickhouse://play:clickhouse@play.clickhouse.com:443?secure=True
    """
    user = quote(config.username.get_secret_value(), safe="")
    password = quote(config.password.get_secret_value(), safe="")
    return (
        f"{config.dialect}://{user}:{password}"
        f"@{config.host}:{config.port}?secure={config.secure}"
    )


def select_columns(table: ibis.Table, *, columns: list[str]) -> ibis.Table:
    """ Select a subset of columns between any available column. 
    It's like Select statement in sql"""
    missing = [c for c in columns if c not in table.columns]
    if missing:
        raise ValueError(
            f"Missing columns: {', '.join(missing)}. Available: {', '.join(table.columns)}"
        )
    return table.select(columns)

def limit_rows(table: ibis.Table, *, n: int) -> ibis.Table:
    """ Limit the number of rows returned from a query.
    It's like limit statement in sql """
    return table.limit(n)

def apply(name: str, table: ibis.Table, **kwargs) -> ibis.Table:
    try:
        operation = OPERATIONS[name]
    except KeyError:
        raise ValueError(
            f"unknown operation {name!r}; available: {', '.join(sorted(OPERATIONS))}"
        ) from None
    return operation(table, **kwargs)


OPERATIONS: dict[str, Operation] = {
    'select' : select_columns,
    'limit' : limit_rows
}
