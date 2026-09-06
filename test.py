import pickle
import uuid
import ibis
import redis

from settings import Settings, get_settings

settings: Settings = get_settings()

settings: Settings = get_settings()

secrets = settings.database['example']
connection: ibis.BaseBackend = ibis.connect(f"{secrets.dialect}://{secrets.username.get_secret_value()}:{secrets.password.get_secret_value()}@{secrets.host}:{secrets.port}?secure={secrets.secure}")

query: ibis.Expr = (
   connection.table('actors')
   .group_by(["locations"])
   .agg()
)

#compiled_query = connection.compile(query)
#decompiled = ibis.decompile(compiled_query)

#print(decompiled)
x = 1
