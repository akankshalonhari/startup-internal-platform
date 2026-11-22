"""Lab scheduler: a Pub/Sub consumer.

Run with:  python -m app.scheduler

For every newly registered tissue sample it queues a genotyping job.
Pub/Sub delivers at least once, so the insert is keyed on event_id
(UNIQUE in the table): a duplicate delivery becomes a no-op.
"""

import json
import logging

from google.cloud import pubsub_v1

from .db import pool, transaction
from .events import ensure_topic_and_subscription, subscription_path

logging.basicConfig(level=logging.INFO, format="%(asctime)s scheduler %(message)s")
log = logging.getLogger("scheduler")


def handle(message: pubsub_v1.subscriber.message.Message) -> None:
    event_id = message.attributes.get("event_id")
    event_type = message.attributes.get("event_type")
    try:
        payload = json.loads(message.data)
        if event_type == "entity.registered" and payload.get("kind") == "tissue_sample":
            with transaction() as conn:
                inserted = conn.execute(
                    """
                    INSERT INTO lab_job (event_id, entity_id, assay)
                    VALUES (%s, %s, 'genotyping')
                    ON CONFLICT (event_id) DO NOTHING
                    RETURNING id
                    """,
                    (event_id, payload["entity_id"]),
                ).fetchone()
            if inserted:
                log.info("queued genotyping job %s for %s", inserted["id"], payload["barcode"])
            else:
                log.info("duplicate delivery of %s ignored", event_id)
        message.ack()
    except Exception:
        # nack -> Pub/Sub redelivers. In production, attach a dead-letter topic
        # so a message that always fails stops retrying and gets an alert.
        log.exception("failed to handle %s", event_id)
        message.nack()


def main() -> None:
    pool.open(wait=True)
    ensure_topic_and_subscription()
    subscriber = pubsub_v1.SubscriberClient()
    log.info("listening on %s", subscription_path())
    streaming_pull = subscriber.subscribe(subscription_path(), callback=handle)
    with subscriber:
        streaming_pull.result()  # blocks forever


if __name__ == "__main__":
    main()
