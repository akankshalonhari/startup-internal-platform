from contextlib import contextmanager

from psycopg.rows import dict_row
from psycopg_pool import ConnectionPool

from .config import DATABASE_URL

# One pool per process. Rows come back as dicts so they map straight onto Pydantic models.
pool = ConnectionPool(
    DATABASE_URL,
    min_size=1,
    max_size=10,
    kwargs={"row_factory": dict_row},
    open=False,
)


@contextmanager
def transaction():
    """Yield a connection inside a transaction: commit on success, roll back on error."""
    with pool.connection() as conn:
        with conn.transaction():
            yield conn
