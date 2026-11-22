"""Pub/Sub helpers shared by the relay (publisher) and the scheduler (subscriber)."""

import logging

from google.api_core.exceptions import AlreadyExists
from google.cloud import pubsub_v1

from .config import PUBSUB_PROJECT_ID, SUBSCRIPTION_ID, TOPIC_ID

log = logging.getLogger(__name__)


def topic_path() -> str:
    return pubsub_v1.PublisherClient.topic_path(PUBSUB_PROJECT_ID, TOPIC_ID)


def subscription_path() -> str:
    return pubsub_v1.SubscriberClient.subscription_path(PUBSUB_PROJECT_ID, SUBSCRIPTION_ID)


def ensure_topic_and_subscription() -> None:
    """Create the topic and subscription if missing.

    In real GCP these would be created by Terraform, not by application code.
    The emulator starts empty, so we create them on startup for local dev.
    """
    publisher = pubsub_v1.PublisherClient()
    subscriber = pubsub_v1.SubscriberClient()
    try:
        publisher.create_topic(request={"name": topic_path()})
        log.info("created topic %s", topic_path())
    except AlreadyExists:
        pass
    try:
        subscriber.create_subscription(
            request={
                "name": subscription_path(),
                "topic": topic_path(),
                "ack_deadline_seconds": 30,
            }
        )
        log.info("created subscription %s", subscription_path())
    except AlreadyExists:
        pass
    finally:
        subscriber.close()
