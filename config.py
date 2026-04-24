import os
from dotenv import load_dotenv

load_dotenv()

# Gmail / Google Cloud
GMAIL_USER_EMAIL = os.environ["GMAIL_USER_EMAIL"]
GOOGLE_CLOUD_PROJECT_ID = os.environ["GOOGLE_CLOUD_PROJECT_ID"]
PUBSUB_TOPIC_NAME = os.environ.get("PUBSUB_TOPIC_NAME", "gmail-job-alerts")
PUBSUB_SUBSCRIPTION_NAME = os.environ.get("PUBSUB_SUBSCRIPTION_NAME", "gmail-job-alerts-sub")
GOOGLE_CREDENTIALS_JSON = os.environ.get("GOOGLE_CREDENTIALS_JSON")  # path or inline JSON

# Twilio
TWILIO_ACCOUNT_SID = os.environ["TWILIO_ACCOUNT_SID"]
TWILIO_AUTH_TOKEN = os.environ["TWILIO_AUTH_TOKEN"]
TWILIO_FROM_NUMBER = os.environ["TWILIO_FROM_NUMBER"]  # e.g. +15005550006
TWILIO_TO_NUMBER = os.environ["TWILIO_TO_NUMBER"]      # your number

# SendGrid
SENDGRID_API_KEY = os.environ["SENDGRID_API_KEY"]
SENDGRID_FROM_EMAIL = os.environ["SENDGRID_FROM_EMAIL"]
SENDGRID_TO_EMAIL = os.environ["SENDGRID_TO_EMAIL"]

# App
FLASK_SECRET_KEY = os.environ.get("FLASK_SECRET_KEY", "change-me-in-production")
PORT = int(os.environ.get("PORT", 8080))
DATABASE_PATH = os.environ.get("DATABASE_PATH", "jobpulse.db")

# Labels / senders that indicate job alert emails
JOB_ALERT_SENDERS = [
    "jobalerts-noreply@linkedin.com",
    "jobs-listings@linkedin.com",
    "notifications@linkedin.com",
]
JOB_ALERT_SUBJECT_KEYWORDS = [
    "job alert",
    "new jobs",
    "jobs for you",
    "recommended jobs",
    "job recommendations",
]
