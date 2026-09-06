from collections.abc import Iterable
from typing import Any

import ibis
import redis
from pydantic_ai.capabilities import WebSearch

from agents import get_agent, get_model, get_provider
from capabilities import make_search_site
from deps import Deps
from settings import DatabaseSettings, get_settings
from tools import (
    AggregateTable,
    FilterTable,
    GetCurrentDatetime,
    GetTable,
    GetTableDefinition,
    GetTableList,
    Mean,
    SelectTable,
    AggregateTable,
    RunQuery,
    CountRows,
    CountUniqueRows, SortTable, LimitTable
)

settings = get_settings()
providers = get_provider(settings)
model = get_model(model_name="qwen3.5-397b-a17b", provider=providers["scaleway"])


db: DatabaseSettings = settings.database["example"]
con = ibis.connect(
    f"{db.dialect}://{db.username.get_secret_value()}:{db.password.get_secret_value()}"
    f"@{db.host}:{db.port}?secure={db.secure}"
)
valkey = redis.Redis.from_url(settings.redis.url)  # hai già la property url

deps = Deps(
    con=con,
    valkey=valkey,
    allowed_tables=settings.allowance.mapping["user"].tables,
    allowed_domains=["mondomobileweb.it", "wikipedia.org"],
)
capabilities: Iterable[Any] = [
    # Scaleway non offre ricerca nativa: usiamo DuckDuckGo come tool locale.
    WebSearch(
        native=False,
        local=make_search_site(deps.allowed_domains),
        defer_loading=False,
        description=f"Capability used to search information on internet, allowed domains: {', '.join(deps.allowed_domains)}",
    )
]

tools = [
    GetCurrentDatetime(),
    Mean(),
    GetTable(),
    GetTableList(),
    GetTableDefinition(),
    FilterTable(),
    SelectTable(),
    AggregateTable(),
    RunQuery(),
    CountRows(),
    CountUniqueRows(),
    SortTable(),
    LimitTable()
]

agent = get_agent(
    model, deps_type=Deps, capabilities=capabilities, tools=tools, retries=3
)

app = agent.to_web(deps=deps)
