import os

DATABASE_URL = os.getenv("DATABASE_URL", "postgresql://startup:startup@localhost:5432/startup")

# When PUBSUB_EMULATOR_HOST is set (e.g. "localhost:8085"), the google-cloud-pubsub
# client talks to the local emulator instead of real GCP. No credentials needed.
PUBSUB_PROJECT_ID = os.getenv("PUBSUB_PROJECT_ID", "startup-local")
TOPIC_ID = os.getenv("PUBSUB_TOPIC", "sample-events")
SUBSCRIPTION_ID = os.getenv("PUBSUB_SUBSCRIPTION", "lab-scheduler")

CORS_ORIGINS = os.getenv("CORS_ORIGINS", "http://localhost:5173").split(",")
