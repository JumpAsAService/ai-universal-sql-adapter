from collections.abc import Iterable
from typing import Any

import ibis
import redis
from pydantic_ai import Agent, RunContext, Tool
from pydantic_ai.capabilities import WebSearch

from agents import get_model, get_provider
from capabilities import make_search_site
from deps import Deps
from prompts import ORCHESTRATOR_PROMPT, SQL_AGENT_PROMPT, SQL_CHECKER_PROMPT
from schemas import QueryOutput, ValidationOutput, GetKeySchema
from settings import DatabaseSettings, get_settings
from tools import (
    AggregateTable,
    CountRows,
    CountUniqueRows,
    FilterTable,
    GetCurrentDatetime,
    GetTable,
    GetTableDefinition,
    GetTableList,
    LimitTable,
    Mean,
    RunQuery,
    SelectTable,
    SortTable,
    ExpressionToSql,
    DryRunValidator,
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
    LimitTable(),
    ExpressionToSql()
]

tools_query_agent = [
    t for t in tools if not isinstance(t, (RunQuery, GetCurrentDatetime))
]
# agent = get_agent(
#    model, deps_type=Deps, capabilities=capabilities, tools=tools, retries=3
# )

query_agent = Agent(
    model,
    deps_type=Deps,
    output_type=QueryOutput,
    tools=tools_query_agent,
    retries=3,
    instructions=SQL_AGENT_PROMPT,
)
# Dry run della query prima di restituire la chiave: se ClickHouse la rifiuta,
# il query agent riceve un ModelRetry e la ricostruisce.
query_agent.output_validator(DryRunValidator())

validator_agent = Agent(
    model,
    deps_type=Deps,
    output_type=ValidationOutput,
    tools=[ExpressionToSql()],
    retries=3,
    instructions=SQL_CHECKER_PROMPT,
)


class BuildQuerySubAgent(Tool):
    def __init__(self, agent: Agent[Deps, QueryOutput]) -> None:
        self.agent = agent
        super().__init__(self._run, name="build_query")

    async def _run(self, ctx: RunContext[Deps], request: str) -> QueryOutput:
        """Build a database query from a natural-language request.

        Args:
            request: what data to extract, in plain language

        Returns:
            The key of the stored expression and a summary of what it computes.
            Pass the key to run_query to get the rows or pass it to the validator agent.
        """
        result = await self.agent.run(
            request,
            conversation_id=ctx.conversation_id,
            deps=ctx.deps,
            usage=ctx.usage,
        )
        return result.output

class ValidationSubAgent(Tool):
    def __init__(self, agent: Agent[Deps, ValidationOutput]) -> None:
        self.agent = agent
        super().__init__(self._run, name="validate_sql_query")

    async def _run(self, ctx: RunContext[Deps], args: GetKeySchema) -> ValidationOutput:
        """Validate a query give a key object stored

        Args:
            args: key of the object stored in the cache

        Returns:
            The key of the stored expression and a summary of what it computes and if the sql query is valid.
            Pass the key to run_query to get the rows.
        """
        result = await self.agent.run(
            user_prompt=f"Validate the sql query stored in the key {args.key}. If it's not valid, explain why. If it's valid, summarize what it computes",
            conversation_id=ctx.conversation_id,
            deps=ctx.deps,
            usage=ctx.usage,
        )
        return result.output


orchestrator = Agent(
    model,
    deps_type=Deps,
    tools=[RunQuery(),CountRows(),
    CountUniqueRows(),GetCurrentDatetime(), BuildQuerySubAgent(agent=query_agent),# ValidationSubAgent(agent=validator_agent)
    ],
    capabilities=capabilities,
    instructions=ORCHESTRATOR_PROMPT,
)
