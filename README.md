# Startup-style platform sample

A small, runnable version of the "key flow" from the platform architecture diagram:

```
React web app ──► FastAPI (Sample & Pedigree API) ──► Postgres
                                                       │  entity + lineage + outbox row
                                                       ▼  (one transaction)
                                    relay ──► Pub/Sub topic "sample-events"
                                                       │
                                                       ▼
                                    lab scheduler (subscriber) ──► lab_job rows
```

Register a **tissue sample** in the UI and its genotyping job appears about a second later.
That delay is the async event flow at work.

It's for learning and interview prep, not production. Service names are illustrative, not any real company's code.

## Run it

Needs Docker Desktop.

```bash
docker compose up --build
```

- Web app: http://localhost:5173
- API docs (Swagger, try every endpoint): http://localhost:8000/docs
- Stop: `Ctrl+C`, then `docker compose down -v` to wipe the database

Seed data includes a 3-generation potato pedigree. Click **Pedigree** on `PT-CH-001`.

## Where to look (read in this order)

| File | What it shows | Interview concept |
|---|---|---|
| `db/init.sql` | Tables, constraints, outbox, `UNIQUE(event_id)` | Data modeling, integrity |
| `backend/app/main.py` | FastAPI endpoints, Pydantic validation, one transaction per batch, `Idempotency-Key`, recursive CTE | API design, idempotency, pedigree queries |
| `backend/app/relay.py` | Outbox → Pub/Sub with `FOR UPDATE SKIP LOCKED` | Transactional outbox, at-least-once delivery |
| `backend/app/scheduler.py` | Pub/Sub subscriber, `ON CONFLICT DO NOTHING`, ack / nack | Idempotent consumers, retries, dead letters |
| `backend/app/schemas.py` | Pydantic models | Request validation |
| `frontend/src/App.jsx` | React form, table, pedigree view, polling | Frontend calling the API |
| `docker-compose.yml` | Postgres, Pub/Sub emulator, 3 Python processes, React | Local stand-in for GCP |

## Try these

```bash
# Register a tissue sample (run it twice: same key, no duplicate)
curl -X POST localhost:8000/entities \
  -H 'Content-Type: application/json' -H 'Idempotency-Key: demo-1' \
  -d '{"barcode":"PT-TS-0100","kind":"tissue_sample"}'

# A whole plate in one transaction
curl -X POST localhost:8000/entities/batch -H 'Content-Type: application/json' \
  -d '{"items":[{"barcode":"PL1-A01","kind":"tissue_sample"},{"barcode":"PL1-A02","kind":"tissue_sample"}]}'

curl localhost:8000/lab-jobs            # jobs created by the Pub/Sub consumer
curl localhost:8000/outbox/pending      # events not yet relayed
```

To watch at-least-once delivery being safe: `docker compose restart relay` mid-flow. Any
re-sent events are ignored by the scheduler because `lab_job.event_id` is unique.

## Run without Docker

You'll need Postgres 16 and the Pub/Sub emulator: `gcloud components install pubsub-emulator`.

```bash
createdb startup && psql startup -f db/init.sql
gcloud beta emulators pubsub start --project=startup-local --host-port=localhost:8085   # separate terminal

cd backend && python -m venv .venv && source .venv/bin/activate && pip install -r requirements.txt
export DATABASE_URL=postgresql://localhost/startup PUBSUB_EMULATOR_HOST=localhost:8085
uvicorn app.main:app --reload    # terminal 1
python -m app.relay              # terminal 2
python -m app.scheduler          # terminal 3

cd frontend && npm install && npm run dev
```

## How this maps to real GCP

| Here | In production |
|---|---|
| Postgres container | Cloud SQL / AlloyDB |
| Pub/Sub emulator | Pub/Sub, with a dead-letter topic on the subscription |
| `ensure_topic_and_subscription()` | Terraform / Pulumi |
| 3 Python processes | Cloud Run services or GKE deployments |
| Polling relay | Same pattern, or Debezium change data capture (CDC) |
| `lab_job` table | Command queue the robots pull from |

### Swapping in Kafka

Only `events.py`, `relay.py` and `scheduler.py` touch the bus. With Kafka you'd:

- use `confluent-kafka`'s `Producer.produce(topic, key=entity_id, value=...)` in the relay;
- use a `Consumer` with manual offset commits in the scheduler;
- key messages by `entity_id` to keep per-entity ordering, the way Pub/Sub uses ordering keys.

The outbox and idempotent-consumer patterns stay exactly the same.

## Next steps if you want to extend it

1. **Closure table:** add `ancestry(ancestor_id, descendant_id, depth)`, fill it in `_insert_entity`, and compare query plans with the CTE.
2. **Instrument ingestion:** a `POST /runs/{id}/results` that parses a CSV, links rows to barcodes and rejects unknown ones.
3. **Robot simulator:** a worker that moves `lab_job` from `queued` → `running` → `done`.
4. **Tests:** pytest with a throwaway database, checking that duplicate deliveries create one job.
