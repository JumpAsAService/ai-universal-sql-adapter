# agentic-sql-adapter

An agentic layer that turns natural-language questions into database queries.
A small team of [pydantic-ai](https://ai.pydantic.dev) agents builds an
[ibis](https://ibis-project.org) expression step by step, dry-runs it against
the database, and only then executes it. Users never see or write SQL.

Two front ends share the same agent:

- a web chat UI served with uvicorn (`main.py`);
- a Telegram bot (`bot.py`).

## How it works

```
user question
     │
     ▼
orchestrator ──► build_query ──► query agent ──► ibis tools ──► Valkey (expression store)
     │                                │
     │                                └─► DryRunValidator (ClickHouse dry run)
     ├──► validate_sql_query ──► validator agent ──► expression_to_sql
     ├──► run_query ──► rows (limited to `expr_limit`)
     └──► answer
```

- **Orchestrator** (`orchestrator.py`): the only agent that talks to the user.
  It delegates query construction to a sub-agent, validates the result, runs
  the query and writes the answer. It can also search the web, restricted to
  the domains listed in `Deps.allowed_domains`.
- **Query agent**: composes an ibis expression one tool call at a time
  (`get_table`, `filter_table`, `select_table`, `aggregate_table`,
  `sort_table`, `limit_table`, ...). Each tool stores the intermediate
  expression in Valkey and returns a key; the next tool loads it by key. The
  model never handles raw SQL or data at this stage.
- **Validator agent**: renders the stored expression to SQL and checks it.
- **Expression store** (`utils.py`): expressions are pickled into Valkey under
  `expr:<conversation_id>:<uuid>` with a TTL, so a conversation can reuse and
  refine a query across turns while keys stay isolated per conversation.
- **Guardrails**: a table allowlist per user (`allowance.mapping`), a hard row
  limit on `run_query`, a dry run before any key is returned, and
  `ModelRetry` feedback so the model can correct itself.

## Requirements

- Python 3.12+
- [uv](https://docs.astral.sh/uv/)
- Docker (for the local Valkey instance)
- An OpenAI-compatible LLM endpoint (the default config uses Scaleway)
- A ClickHouse database (the example config points to the public ClickHouse
  playground)

## Setup

```bash
uv sync
docker compose up -d          # starts Valkey on localhost:6379
cp config.toml.example config.toml
```

Edit `config.toml` with your credentials. The file is git-ignored; never
commit it.

## Running

Web chat UI:

```bash
uv run uvicorn main:app --reload
```

Telegram bot (requires the `[telegram]` section in `config.toml`):

```bash
uv run python bot.py
```

Send `/start` to reset the conversation, then ask questions in plain
language. Each Telegram chat is a separate conversation with its own
expression namespace and message history. History is kept in memory and is
lost on restart.

## Configuration

Settings are loaded with pydantic-settings (`settings.py`). The source depends
on `APP_ENV`:

| `APP_ENV`               | Sources                                   |
|-------------------------|-------------------------------------------|
| `development` (default) | init args, environment, then `config.toml` |
| `production`            | init args and environment only            |

### `config.toml`

```toml
[openai.<provider-name>]      # one section per OpenAI-compatible provider
base_url = "https://api.scaleway.ai/v1"
secret_key = "..."

[database.<connection-name>]  # one section per database
host = "..."
username = "..."
password = "..."
port = 443
secure = true
dialect = "clickhouse"        # only clickhouse is supported today

[telegram]                    # optional
token = "..."

[redis]
host = "localhost"
port = 6379
db = 0
password = "..."

[allowance]                   # JSON string: per-user table allowlist
mapping = '''
{ "user": { "id": 1, "username": "...", "password": "...", "tables": ["actors"] } }
'''
```

`orchestrator.py` currently picks `providers["scaleway"]`,
`settings.database["example"]` and `allowance.mapping["user"]`; change those
names there if you use different section names.

### Environment variables

In production, set the same values as environment variables using `__` as the
nesting delimiter:

```bash
APP_ENV=production
OPENAI__SCALEWAY__BASE_URL=https://api.scaleway.ai/v1
OPENAI__SCALEWAY__SECRET_KEY=...
DATABASE__EXAMPLE__HOST=...
DATABASE__EXAMPLE__USERNAME=...
DATABASE__EXAMPLE__PASSWORD=...
DATABASE__EXAMPLE__PORT=443
DATABASE__EXAMPLE__DIALECT=clickhouse
REDIS__PASSWORD=...
TELEGRAM__TOKEN=...
ALLOWANCE__MAPPING='{"user": {"id": 1, "username": "...", "password": "...", "tables": ["actors"]}}'
```

### Runtime knobs (`deps.py`)

| Field             | Default | Meaning                                         |
|-------------------|---------|-------------------------------------------------|
| `allowed_tables`  | —       | Tables the agent may touch                      |
| `allowed_domains` | —       | Domains the web search is restricted to         |
| `expr_limit`      | 10      | Max rows returned by `run_query`                |
| `expr_ttl`        | 3600    | Seconds a stored expression lives in Valkey     |
| `decimals`        | 2       | Rounding applied to numeric results             |

## Project layout

| File                  | Purpose                                              |
|-----------------------|------------------------------------------------------|
| `orchestrator.py`     | Builds connections, deps, tools and the three agents |
| `main.py`             | Web UI entry point (`orchestrator.to_web`)           |
| `bot.py`              | Telegram entry point                                 |
| `agents.py`           | Provider and model factories                         |
| `tools.py`            | ibis tools exposed to the agents, dry-run validator  |
| `schemas.py`          | Pydantic schemas for tool arguments and outputs      |
| `prompts.py`          | Agent instructions                                   |
| `utils.py`            | Valkey expression store                              |
| `deps.py`             | Per-run dependencies injected into tools             |
| `capabilities.py`     | Domain-restricted DuckDuckGo search                  |
| `settings.py`         | Configuration model and sources                      |
| `docker-compose.yml`  | Local Valkey                                         |

## Security notes

- All credentials live in `config.toml` (git-ignored) or environment
  variables. Secrets are typed as `SecretStr` so they are masked in reprs.
- The `httpx` logger is silenced to `WARNING` in `bot.py`: at `INFO` it would
  print every Telegram API URL, which embeds the bot token.
- The Valkey password in `docker-compose.yml` is a development-only default.
  Change it, together with `[redis].password`, before exposing the service.
- If a bot token or API key is ever pasted into logs, chat, or a commit,
  rotate it.
