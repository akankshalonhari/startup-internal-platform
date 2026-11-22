"""Outbox relay: moves events from Postgres to Pub/Sub.

Run with:  python -m app.relay

Each loop locks a batch of unpublished outbox rows, publishes them, and marks
them published in the same transaction. If the process crashes after publishing
but before committing, the rows are sent again on restart. That is
at-least-once delivery, which is why consumers must be idempotent.
"""

import json
import logging
import time

from google.cloud import pubsub_v1

from .db import pool, transaction
from .events import ensure_topic_and_subscription, topic_path

logging.basicConfig(level=logging.INFO, format="%(asctime)s relay %(message)s")
log = logging.getLogger("relay")

BATCH_SIZE = 100
POLL_SECONDS = 1.0


def publish_batch(publisher: pubsub_v1.PublisherClient) -> int:
    with transaction() as conn:
        rows = conn.execute(
            """
            SELECT event_id, event_type, payload
            FROM outbox
            WHERE published_at IS NULL
            ORDER BY created_at
            LIMIT %s
            FOR UPDATE SKIP LOCKED      -- safe to run several relays at once
            """,
            (BATCH_SIZE,),
        ).fetchall()

        for row in rows:
            future = publisher.publish(
                topic_path(),
                data=json.dumps(row["payload"]).encode(),
                event_id=str(row["event_id"]),      # attributes travel with the message
                event_type=row["event_type"],
            )
            future.result(timeout=10)               # wait for the broker to accept it
            conn.execute(
                "UPDATE outbox SET published_at = now() WHERE event_id = %s",
                (row["event_id"],),
            )
            log.info("published %s %s", row["event_type"], row["event_id"])
    return len(rows)


def main() -> None:
    pool.open(wait=True)
    ensure_topic_and_subscription()
    publisher = pubsub_v1.PublisherClient()
    log.info("relay started, publishing to %s", topic_path())
    while True:
        try:
            if publish_batch(publisher) == 0:
                time.sleep(POLL_SECONDS)
        except Exception:
            log.exception("publish failed; will retry")
            time.sleep(POLL_SECONDS * 5)


if __name__ == "__main__":
    main()
