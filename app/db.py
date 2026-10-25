"""Every query runs inside a transaction that knows which company is asking."""
from contextlib import contextmanager
import psycopg
from pgvector.psycopg import register_vector
from .config import DATABASE_URL


@contextmanager
def tenant_tx(tenant_id: int):
    """Open a transaction where row level security only lets this company's rows through."""
    with psycopg.connect(DATABASE_URL) as conn:
        register_vector(conn)
        with conn.transaction():
            conn.execute("SELECT set_config('app.tenant', %s, true)", (str(tenant_id),))
            yield conn
