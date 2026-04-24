"""
Gmail API + Google Cloud Pub/Sub integration.

Responsibilities:
  - Build an authenticated Gmail API service object
  - Set up (or refresh) a Gmail push-notification watch on the inbox
  - Fetch and decode a full Gmail message by ID
"""

import json
import logging
import os
from google.oauth2 import service_account
from googleapiclient.discovery import build
from googleapiclient.errors import HttpError
import config

logger = logging.getLogger(__name__)

SCOPES = ["https://www.googleapis.com/auth/gmail.readonly"]


def _get_credentials():
    """
    Load service-account credentials from either:
      - GOOGLE_CREDENTIALS_JSON env var containing the raw JSON string, or
      - A file path stored in GOOGLE_CREDENTIALS_JSON.
    """
    raw = config.GOOGLE_CREDENTIALS_JSON
    if not raw:
        raise RuntimeError("GOOGLE_CREDENTIALS_JSON env var is not set")

    # Detect whether the value is a JSON string or a file path
    if raw.strip().startswith("{"):
        info = json.loads(raw)
    else:
        with open(raw) as f:
            info = json.load(f)

    creds = service_account.Credentials.from_service_account_info(
        info,
        scopes=SCOPES,
        subject=config.GMAIL_USER_EMAIL,  # domain-wide delegation
    )
    return creds


def get_gmail_service():
    """Return an authenticated Gmail API resource."""
    creds = _get_credentials()
    return build("gmail", "v1", credentials=creds, cache_discovery=False)


def setup_gmail_watch(service=None) -> dict:
    """
    Call Gmail users.watch() to subscribe to Pub/Sub push notifications.

    Google requires this to be renewed every 7 days. Call this on startup
    and via a scheduled job (e.g. daily cron on Render).

    Returns the watch response dict with fields: historyId, expiration.
    """
    if service is None:
        service = get_gmail_service()

    topic_name = f"projects/{config.GOOGLE_CLOUD_PROJECT_ID}/topics/{config.PUBSUB_TOPIC_NAME}"

    body = {
        "labelIds": ["INBOX"],
        "topicName": topic_name,
    }
    try:
        response = service.users().watch(userId="me", body=body).execute()
        logger.info("Gmail watch set up: %s", response)
        return response
    except HttpError as e:
        logger.error("Failed to set up Gmail watch: %s", e)
        raise


def get_message(message_id: str, service=None) -> dict:
    """
    Fetch a full Gmail message payload by message ID.
    Returns the message resource dict (with 'payload' key).
    """
    if service is None:
        service = get_gmail_service()
    try:
        msg = (
            service.users()
            .messages()
            .get(userId="me", id=message_id, format="full")
            .execute()
        )
        return msg
    except HttpError as e:
        logger.error("Failed to fetch message %s: %s", message_id, e)
        raise


def get_history(start_history_id: str, service=None) -> list[dict]:
    """
    Return new messages since start_history_id using the History API.
    Each item in the returned list is a Gmail message resource stub.
    """
    if service is None:
        service = get_gmail_service()

    messages: list[dict] = []
    page_token = None

    while True:
        kwargs = {
            "userId": "me",
            "startHistoryId": start_history_id,
            "historyTypes": ["messageAdded"],
            "labelId": "INBOX",
        }
        if page_token:
            kwargs["pageToken"] = page_token

        try:
            resp = service.users().history().list(**kwargs).execute()
        except HttpError as e:
            if e.resp.status == 404:
                # History ID expired — caller should re-watch and re-sync
                logger.warning("History ID %s not found (expired?)", start_history_id)
                return []
            raise

        for record in resp.get("history", []):
            for added in record.get("messagesAdded", []):
                messages.append(added["message"])

        page_token = resp.get("nextPageToken")
        if not page_token:
            break

    return messages
