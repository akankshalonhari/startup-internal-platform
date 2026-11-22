-- Schema for the Sample & Pedigree service.
-- Postgres is the source of truth for identity and lineage.

CREATE TABLE entity (
    id          TEXT PRIMARY KEY,                      -- server-issued ULID
    barcode     TEXT NOT NULL UNIQUE,                  -- what crews scan
    kind        TEXT NOT NULL CHECK (kind IN ('seed', 'plant', 'tissue_sample')),
    species     TEXT NOT NULL,
    created_at  TIMESTAMPTZ NOT NULL DEFAULT now()
);

-- One row per parent -> child link. Pedigree is a graph stored as an adjacency list.
CREATE TABLE lineage_edge (
    parent_id   TEXT NOT NULL REFERENCES entity(id),
    child_id    TEXT NOT NULL REFERENCES entity(id),
    relation    TEXT NOT NULL CHECK (relation IN ('female_parent', 'male_parent', 'derived_from')),
    PRIMARY KEY (parent_id, child_id, relation)
);
CREATE INDEX lineage_edge_child_idx ON lineage_edge (child_id);

-- Transactional outbox: written in the SAME transaction as the entity.
-- The relay process publishes unpublished rows to Pub/Sub.
CREATE TABLE outbox (
    event_id      UUID PRIMARY KEY,
    event_type    TEXT NOT NULL,
    payload       JSONB NOT NULL,
    created_at    TIMESTAMPTZ NOT NULL DEFAULT now(),
    published_at  TIMESTAMPTZ
);
CREATE INDEX outbox_unpublished_idx ON outbox (created_at) WHERE published_at IS NULL;

-- Stored responses for Idempotency-Key headers, so a retried batch never duplicates.
CREATE TABLE idempotency_key (
    key         TEXT PRIMARY KEY,
    response    JSONB NOT NULL,
    created_at  TIMESTAMPTZ NOT NULL DEFAULT now()
);

-- Written by the lab scheduler when it consumes an event.
-- UNIQUE(event_id) makes the consumer idempotent: Pub/Sub may deliver twice.
CREATE TABLE lab_job (
    id          BIGSERIAL PRIMARY KEY,
    event_id    UUID NOT NULL UNIQUE,
    entity_id   TEXT NOT NULL REFERENCES entity(id),
    assay       TEXT NOT NULL,
    status      TEXT NOT NULL DEFAULT 'queued',
    created_at  TIMESTAMPTZ NOT NULL DEFAULT now()
);

-- Seed data: a small potato pedigree so the pedigree view has something to show.
INSERT INTO entity (id, barcode, kind, species) VALUES
    ('01SEEDGRANDMA0000000000000', 'PT-GM-001', 'plant', 'Solanum tuberosum'),
    ('01SEEDGRANDPA0000000000000', 'PT-GP-001', 'plant', 'Solanum tuberosum'),
    ('01SEEDMOTHER00000000000000', 'PT-MO-001', 'plant', 'Solanum tuberosum'),
    ('01SEEDFATHER00000000000000', 'PT-FA-001', 'plant', 'Solanum tuberosum'),
    ('01SEEDCROSSSEED00000000000', 'PT-SD-001', 'seed',  'Solanum tuberosum'),
    ('01SEEDCHILD000000000000000', 'PT-CH-001', 'plant', 'Solanum tuberosum');

INSERT INTO lineage_edge (parent_id, child_id, relation) VALUES
    ('01SEEDGRANDMA0000000000000', '01SEEDMOTHER00000000000000', 'female_parent'),
    ('01SEEDGRANDPA0000000000000', '01SEEDMOTHER00000000000000', 'male_parent'),
    ('01SEEDMOTHER00000000000000', '01SEEDCROSSSEED00000000000', 'female_parent'),
    ('01SEEDFATHER00000000000000', '01SEEDCROSSSEED00000000000', 'male_parent'),
    ('01SEEDCROSSSEED00000000000', '01SEEDCHILD000000000000000', 'derived_from');
