

import ibis

from ai_universal_sql_adapter.config import DatabaseSettings, Settings, get_settings
from ai_universal_sql_adapter.backends.registry import build_dsn, select_columns, apply
import pendulum



def main() -> None:
    settings: Settings = get_settings()
    database_config: DatabaseSettings = settings.database["example_clickhouse"]

    # define connection
    connection: ibis.BaseBackend = ibis.connect(build_dsn(database_config))

    # define available tables
    connection.list_tables()

    #ActorsTable: ibis.Table = connection.table("actors")
    #ActorsTableSchema: ibis.Schema = ActorsTable.schema()
    #query: ibis.Expr = (
    #    ActorsTable
    #    .filter(
    #        ActorsTable.location.isin(ibis.literal(["Munich", "Rome"])),
    #        ActorsTable.created_at <= ibis.date(2012, 12, 30)
    #    )
    #)
    target_table: ibis.Table = connection.table('actors')
    query_1: ibis.Expr = apply('select', target_table, columns=['login', 'name'])
    query_2: ibis.Expr = apply('limit', query_1, n=10)

    print(query_2.execute())


if __name__ == "__main__":
    main()
    x=1