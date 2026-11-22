"""Sample & Pedigree API (FastAPI).

Registers seeds, plants and tissue samples, links them into a pedigree, and
writes an outbox event in the same transaction so downstream services
(the lab scheduler) hear about every new entity exactly once in effect.
"""

import uuid
from contextlib import asynccontextmanager

import psycopg
from fastapi import FastAPI, Header, HTTPException, Query
from fastapi.middleware.cors import CORSMiddleware
from psycopg.types.json import Jsonb
from ulid import ULID

from .config import CORS_ORIGINS
from .db import pool, transaction
from .schemas import BatchCreate, Entity, EntityCreate, LabJob, PedigreeNode


@asynccontextmanager
async def lifespan(app: FastAPI):
    pool.open(wait=True)
    yield
    pool.close()


app = FastAPI(title="Sample & Pedigree API", version="0.1.0", lifespan=lifespan)
app.add_middleware(
    CORSMiddleware,
    allow_origins=CORS_ORIGINS,
    allow_methods=["*"],
    allow_headers=["*"],
)


@app.get("/health")
def health() -> dict:
    with pool.connection() as conn:
        conn.execute("SELECT 1")
    return {"status": "ok"}


# ---------------------------------------------------------------- writes


def _insert_entity(conn: psycopg.Connection, item: EntityCreate) -> dict:
    """Insert one entity, its parent links and its outbox event. Caller owns the transaction."""
    entity_id = str(ULID())
    row = conn.execute(
        """
        INSERT INTO entity (id, barcode, kind, species)
        VALUES (%s, %s, %s, %s)
        RETURNING id, barcode, kind, species, created_at
        """,
        (entity_id, item.barcode, item.kind, item.species),
    ).fetchone()

    for parent in item.parents:
        conn.execute(
            "INSERT INTO lineage_edge (parent_id, child_id, relation) VALUES (%s, %s, %s)",
            (parent.parent_id, entity_id, parent.relation),
        )

    # The outbox row commits or rolls back together with the entity:
    # no event without a saved entity, and no saved entity without its event.
    conn.execute(
        "INSERT INTO outbox (event_id, event_type, payload) VALUES (%s, %s, %s)",
        (
            uuid.uuid4(),
            "entity.registered",
            Jsonb({"entity_id": entity_id, "barcode": item.barcode, "kind": item.kind}),
        ),
    )
    return row


@app.post("/entities/batch", response_model=list[Entity], status_code=201)
def create_entities(
    body: BatchCreate,
    idempotency_key: str | None = Header(default=None, alias="Idempotency-Key"),
) -> list[dict]:
    """Register a whole plate (or several) in ONE transaction: all rows or none.

    Send the same Idempotency-Key on a retry and you get the original response
    back instead of duplicate samples.
    """
    if idempotency_key:
        with pool.connection() as conn:
            stored = conn.execute(
                "SELECT response FROM idempotency_key WHERE key = %s", (idempotency_key,)
            ).fetchone()
            if stored:
                return stored["response"]

    try:
        with transaction() as conn:
            rows = [_insert_entity(conn, item) for item in body.items]
            response = [Entity(**r).model_dump(mode="json") for r in rows]
            if idempotency_key:
                conn.execute(
                    "INSERT INTO idempotency_key (key, response) VALUES (%s, %s)",
                    (idempotency_key, Jsonb(response)),
                )
            return response
    except psycopg.errors.UniqueViolation as exc:
        # Either a barcode already exists, or a concurrent retry beat us to the key.
        if idempotency_key and "idempotency_key" in str(exc):
            with pool.connection() as conn:
                return conn.execute(
                    "SELECT response FROM idempotency_key WHERE key = %s", (idempotency_key,)
                ).fetchone()["response"]
        raise HTTPException(409, "A barcode in this batch is already registered") from exc
    except psycopg.errors.ForeignKeyViolation as exc:
        raise HTTPException(422, "A parent_id does not exist") from exc


@app.post("/entities", response_model=Entity, status_code=201)
def create_entity(
    body: EntityCreate,
    idempotency_key: str | None = Header(default=None, alias="Idempotency-Key"),
) -> dict:
    return create_entities(BatchCreate(items=[body]), idempotency_key)[0]


# ---------------------------------------------------------------- reads


@app.get("/entities", response_model=list[Entity])
def list_entities(limit: int = Query(50, le=500)) -> list[dict]:
    with pool.connection() as conn:
        return conn.execute(
            """
            SELECT e.id, e.barcode, e.kind, e.species, e.created_at,
                   j.status AS lab_job_status
            FROM entity e
            LEFT JOIN lab_job j ON j.entity_id = e.id
            ORDER BY e.created_at DESC
            LIMIT %s
            """,
            (limit,),
        ).fetchall()


@app.get("/entities/by-barcode/{barcode}", response_model=Entity)
def get_by_barcode(barcode: str) -> dict:
    with pool.connection() as conn:
        row = conn.execute(
            "SELECT id, barcode, kind, species, created_at FROM entity WHERE barcode = %s",
            (barcode,),
        ).fetchone()
    if not row:
        raise HTTPException(404, "Unknown barcode")
    return row


@app.get("/entities/{entity_id}/pedigree", response_model=list[PedigreeNode])
def get_pedigree(entity_id: str, depth: int = Query(5, ge=1, le=20)) -> list[dict]:
    """All ancestors up to `depth` generations, using a recursive CTE.

    Each step joins lineage_edge to the previous generation's parents.
    If this gets slow on deep pedigrees, add a closure table (ancestor, descendant, depth).
    """
    with pool.connection() as conn:
        return conn.execute(
            """
            WITH RECURSIVE ancestors AS (
                SELECT parent_id, child_id, relation, 1 AS depth
                FROM lineage_edge
                WHERE child_id = %(id)s
              UNION ALL
                SELECT e.parent_id, e.child_id, e.relation, a.depth + 1
                FROM lineage_edge e
                JOIN ancestors a ON e.child_id = a.parent_id
                WHERE a.depth < %(depth)s
            )
            SELECT ent.id, ent.barcode, ent.kind, a.child_id, a.relation, a.depth
            FROM ancestors a
            JOIN entity ent ON ent.id = a.parent_id
            ORDER BY a.depth, a.relation
            """,
            {"id": entity_id, "depth": depth},
        ).fetchall()


@app.get("/lab-jobs", response_model=list[LabJob])
def list_lab_jobs(limit: int = Query(50, le=500)) -> list[dict]:
    with pool.connection() as conn:
        return conn.execute(
            """
            SELECT j.id, j.entity_id, e.barcode, j.assay, j.status, j.created_at
            FROM lab_job j JOIN entity e ON e.id = j.entity_id
            ORDER BY j.created_at DESC
            LIMIT %s
            """,
            (limit,),
        ).fetchall()


@app.get("/outbox/pending")
def pending_outbox() -> dict:
    """Handy for demos: how many events are still waiting for the relay."""
    with pool.connection() as conn:
        return conn.execute(
            "SELECT count(*) AS pending FROM outbox WHERE published_at IS NULL"
        ).fetchone()
