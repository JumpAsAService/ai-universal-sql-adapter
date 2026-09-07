import operator
from operator import methodcaller
from typing import Any

import ibis
import numpy as np
import pandas as pd
import pendulum
from ibis.expr.types.numeric import IntegerScalar
from pydantic_ai import ModelRetry, RunContext, Tool

import clickhouse_connect.driver.exceptions as ch_exc
from ibis.common.exceptions import IbisError

import utils
from deps import Deps
from schemas import (
    FilterSchema,
    GetKeySchema,
    GetTableSchema,
    GroupBySchema,
    LimitSchema,
    MeanSchema,
    QueryOutput,
    SelectSchema,
    SortSchema,
)


class Mean(Tool):
    def __init__(self) -> None:
        super().__init__(self._run, name="mean")

    def _run(self, ctx: RunContext[Deps], numbers: MeanSchema) -> float:
        """Compute the arithmetic mean of the given numbers.

        Args:
            numbers: the numbers to average, at least one
        """
        arr = np.asarray(numbers.numbers, dtype=np.float64)
        return round(float(arr.mean()), ctx.deps.decimals)


class GetCurrentDatetime(Tool):
    def __init__(self) -> None:
        super().__init__(self._run, name="get_current_datetime")

    def _run(self) -> str:
        """Get the current datetime"""
        return pendulum.now().to_iso8601_string()


class GetTable(Tool):
    """Load a table as an ibis expression and store it in Valkey."""

    def __init__(self) -> None:
        super().__init__(self._run, name="get_table")

    def _run(self, ctx: RunContext[Deps], args: GetTableSchema) -> str:
        """Load a database table and store it for the next steps.

        Args:
            args: the table to load, must be one of the allowed tables

        Returns:
            The key of the stored expression. Pass it to the other tools.
        """
        name = args.table_name
        if name not in ctx.deps.allowed_tables:
            raise ModelRetry(
                f"Tabella {name!r} non consentita. Disponibili: {', '.join(ctx.deps.allowed_tables)}"
            )
        table = ctx.deps.con.table(name)
        return utils.save_expr(ctx, table)


class GetTableList(Tool):
    """Get the table list for a given database connection. This is used to get the list of tables available in the database."""

    def __init__(self) -> None:
        super().__init__(self._run, name="get_table_list")

    def _run(self, ctx: RunContext[Deps]) -> list[str]:
        """Load a database table and store it for the next steps.

        Returns:
            List of tables
        """
        try:
            ls_tables: list[str] = ctx.deps.con.list_tables()
        except Exception as e:  # noqa: BLE001 - qualsiasi errore del backend va riportato al modello
            raise ModelRetry(f"Error in loading tables: {e}")

        return ls_tables


class GetTableDefinition(Tool):
    """Get the Table schema for a give table"""

    def __init__(self) -> None:
        super().__init__(self._run, name="get_table_schema")

    def _run(self, ctx: RunContext[Deps], args: GetTableSchema) -> str:
        """Get the schema of a table from the database connection.

        Args:
            args: the table to lread the schema

        Returns:
            The key of the stored expression. Pass it to the other tools.
        """
        name = args.table_name
        if name not in ctx.deps.allowed_tables:
            raise ModelRetry(
                f"Tabella {name!r} non consentita. Disponibili: {', '.join(ctx.deps.allowed_tables)}"
            )
        schema = ctx.deps.con.table(name).schema
        return str(schema)


_OPS = {
    "eq": operator.eq,
    "ne": operator.ne,
    "lt": operator.lt,
    "le": operator.le,
    "gt": operator.gt,
    "ge": operator.ge,
}


class FilterTable(Tool):
    """Apply a filter to an ibis expression already saved in Valkey."""

    def __init__(self) -> None:
        super().__init__(self._run, name="filter_table")

    def _run(self, ctx: RunContext[Deps], args: FilterSchema) -> str:
        """Filter a stored expression on one column and store the result.

        Args:
            args: the stored expression key, the column, the comparison and the value

        Returns:
            The key of the new filtered expression. Pass it to the other tools.
        """
        expr = utils.load_expr(ctx, args.key)

        if args.field not in expr.columns:
            raise ModelRetry(
                f"Column {args.field!r} not found. Available: {', '.join(expr.columns)}"
            )
        column = expr[args.field]

        if args.filter_type == "in":
            condition = column.isin(args.value)
        else:
            condition = _OPS[args.filter_type](column, args.value)

        return utils.save_expr(ctx, expr.filter(condition))


class SelectTable(Tool):
    """Keep only some columns of an ibis expression already saved in Valkey."""

    def __init__(self) -> None:
        super().__init__(self._run, name="select_columns")

    def _run(self, ctx: RunContext[Deps], args: SelectSchema) -> str:
        """Keep only the given columns of a stored expression and store the result.

        Args:
            args: the stored expression key and the columns to keep

        Returns:
            The key of the new expression. Pass it to the other tools.
        """
        expr = utils.load_expr(ctx, args.key)

        missing = [c for c in args.columns if c not in expr.columns]
        if missing:
            raise ModelRetry(
                f"Columns not found: {', '.join(missing)}. "
                f"Available: {', '.join(expr.columns)}"
            )

        return utils.save_expr(ctx, expr.select(args.columns))


_AGGREGATION_OPS = {
    "count": methodcaller("count"),
    "sum": methodcaller("sum"),
    "mean": methodcaller("mean"),
    "unique": methodcaller("nunique"),  # numero di valori distinti
    "max": methodcaller("max"),
    "min": methodcaller("min"),
}


class AggregateTable(Tool):
    """Group an ibis expression already saved in Valkey and aggregate its columns."""

    def __init__(self) -> None:
        super().__init__(self._run, name="group_by")

    def _run(self, ctx: RunContext[Deps], args: GroupBySchema) -> str:
        """Group a stored expression by some columns, aggregate others, and store the resulting table.

        Args:
            args: the stored expression key, the columns to group by and, for each column to
                aggregate, the aggregation to apply

        Returns:
            The key of the new table. Its columns are the group-by columns plus one
            column named <aggregation>_<column> for each aggregation.
        """
        expr = utils.load_expr(ctx, args.key)

        requested = [*args.group_by_columns, *args.aggregations]
        missing = [c for c in requested if c not in expr.columns]
        if missing:
            raise ModelRetry(
                f"Columns not found: {', '.join(missing)}. Available: {', '.join(expr.columns)}"
            )
        # clash = [c for c in args.aggregations if c in args.group_by_columns]
        # if clash:
        #    raise ModelRetry(
        #        f"Columns {', '.join(clash)} cannot be both aggregated and grouped by"
        #    )

        metrics = {}
        for field, aggregation in args.aggregations.items():
            column = expr[field]
            try:
                metrics[f"{aggregation}_{field}"] = _AGGREGATION_OPS[aggregation](
                    column
                )
            except AttributeError:
                raise ModelRetry(
                    f"{aggregation!r} not supported on column {field!r} of type {column.type()}"
                )

        result = expr.group_by(args.group_by_columns).aggregate(**metrics)
        return utils.save_expr(ctx, result)


class CountRows(Tool):
    """Count the number of rows from a stored expression executing it and returning a list of dicts"""

    def __init__(self):
        super().__init__(self._run, name="count_rows")

    def _run(
        self, ctx: RunContext[Deps], args: GetKeySchema
    ) -> pd.DataFrame | pd.Series | Any:
        expr: IntegerScalar = utils.load_expr(ctx, args.key).count()
        return ctx.deps.con.execute(expr)


class CountUniqueRows(Tool):
    """Count distinct/unique the number of rows from a stored expression executing it and returning a list of dicts"""

    def __init__(self):
        super().__init__(self._run, name="count_unique_rows")

    def _run(
        self, ctx: RunContext[Deps], args: GetKeySchema
    ) -> pd.DataFrame | pd.Series | Any:
        expr: IntegerScalar = utils.load_expr(ctx, args.key).distinct().count()

        return ctx.deps.con.execute(expr)


class SortTable(Tool):
    """Sort a table or a ibis expression by a column ascending or descending"""

    def __init__(self):
        super().__init__(self._run, name="sort")

    def _run(self, ctx: RunContext[Deps], args: SortSchema) -> str:
        """Sort a stored expression by one column and store the result.

        Args:
            args: the stored expression key, the column to sort by and the direction

        Returns:
            The key of the sorted expression. Pass it to the other tools.
        """
        expr = utils.load_expr(ctx, args.key)

        if args.column not in expr.columns:
            raise ModelRetry(
                f"Column {args.column!r} not found. Available: {', '.join(expr.columns)}"
            )

        order = args.column if args.ascending else ibis.desc(args.column)
        return utils.save_expr(ctx, expr.order_by(order))


class ExpressionToSql(Tool):
    def __init__(self):
        super().__init__(self._run, name="expression_to_sql")

    def _run(self, ctx: RunContext[Deps], args: GetKeySchema) -> str:
        """Show the SQL that a stored expression would run, without executing it.
        returning the sql expression for analysis and checks

        Args:
            args: the key of the stored expression
        """
        expr = utils.load_expr(ctx, args.key)
        return ctx.deps.con.compile(expr, pretty=True)


class LimitTable(Tool):
    """Apply a limit of results in a stored expression"""

    def __init__(self):
        super().__init__(self._run, name="limit")

    def _run(self, ctx: RunContext[Deps], args: LimitSchema) -> str:
        """limit a stored expression by the number of rows.

        Args:
            args: the stored expression key, the number of rows to retain

        Returns:
            The key of the limited expression. Pass it to the other tools
        """

        expr = utils.load_expr(ctx, args.key).limit(args.limit)

        return utils.save_expr(ctx, expr)


class RunQuery(Tool):
    """Execute a query expression to return data

    Args:
        args: the stored expression key

    Returns:
        the list of dictionary of query result, capped by row number by default by context
        to avoid wasting of tokens
    """

    def __init__(self):
        super().__init__(self._run, name="run_query")

    def _run(self, ctx: RunContext[Deps], args: GetKeySchema) -> list[dict]:
        """..."""
        expr = utils.load_expr(ctx, args.key)

        # apply limit if is a table:
        if isinstance(expr, ibis.Expr):
            expr = expr.limit(ctx.deps.expr_limit)

        df = ctx.deps.con.to_pandas(expr)
        if not isinstance(df, pd.DataFrame):
            raise TypeError(f"Expected a DataFrame, got {type(df).__name__}")
        return df.to_dict("records")

def dry_run(ctx: RunContext[Deps], key: str) -> str:
    """Compila ed esegue EXPLAIN sulla query. Ritorna l'SQL, alza ModelRetry se non valida."""
    expr = utils.load_expr(ctx, key)
    sql = ""
    try:
        sql = ctx.deps.con.compile(expr, pretty=True)
        ctx.deps.con.raw_sql(f"EXPLAIN {sql}")  # ty: ignore[unresolved-attribute]
    except (ch_exc.DatabaseError, IbisError) as e:
        raise ModelRetry(
            f"La query non è valida, correggila e ricostruiscila.\nSQL:\n{sql}\nErrore: {e}"
        ) from e
    return sql


class DryRunValidator:
    """Output validator per il query agent: esegue il dry run della query
    prima di restituire la chiave. Si registra con
    ``agent.output_validator(DryRunValidator())``.

    Se il dry run fallisce, ``dry_run`` alza ModelRetry e il modello
    ricostruisce la query.
    """

    def __call__(self, ctx: RunContext[Deps], output: QueryOutput) -> QueryOutput:
        dry_run(ctx, output.key)
        return output
