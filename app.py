"""
JobPulse — Flask webhook server.

Endpoints:
  POST /webhook/pubsub   Receives Pub/Sub push notifications from Google Cloud
  POST /admin/watch      (Re-)register Gmail watch (call this on deploy + daily)
  GET  /health           Health check
"""

import base64
import json
import logging
import sys

from flask import Flask, request, jsonify, abort

import config
import database
import gmail_handler
import parser as job_parser
import notifier

# ---------------------------------------------------------------------------
# Logging
# ---------------------------------------------------------------------------
logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s %(levelname)s %(name)s — %(message)s",
    stream=sys.stdout,
)
logger = logging.getLogger(__name__)

# ---------------------------------------------------------------------------
# App init
# ---------------------------------------------------------------------------
app = Flask(__name__)
app.secret_key = config.FLASK_SECRET_KEY

database.init_db()


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _is_job_alert_message(message_payload: dict) -> bool:
    """Return True if the message looks like a job-alert email."""
    headers = {h["name"].lower(): h["value"] for h in message_payload.get("headers", [])}
    sender: str = headers.get("from", "").lower()
    subject: str = headers.get("subject", "").lower()

    sender_match = any(s in sender for s in config.JOB_ALERT_SENDERS)
    subject_match = any(kw in subject for kw in config.JOB_ALERT_SUBJECT_KEYWORDS)
    return sender_match or subject_match


def _process_gmail_message(message_id: str) -> int:
    """
    Fetch, parse, deduplicate, and notify for a single Gmail message.
    Returns the number of new (non-duplicate) jobs sent.
    """
    full_msg = gmail_handler.get_message(message_id)
    payload = full_msg.get("payload", {})

    if not _is_job_alert_message(payload):
        logger.debug("Message %s is not a job alert — skipping", message_id)
        return 0

    jobs = job_parser.extract_jobs(payload)
    if not jobs:
        logger.info("No jobs extracted from message %s", message_id)
        return 0

    new_jobs = []
    for job in jobs:
        saved = database.save_job(
            title=job["title"],
            company=job.get("company", ""),
            link=job["link"],
            gmail_id=message_id,
        )
        if saved:
            new_jobs.append(job)
        else:
            logger.info("Duplicate skipped: %s @ %s", job["title"], job.get("company"))

    if new_jobs:
        logger.info("Sending notifications for %d new job(s)", len(new_jobs))
        notifier.notify(new_jobs)

    return len(new_jobs)


# ---------------------------------------------------------------------------
# Routes
# ---------------------------------------------------------------------------

@app.get("/health")
def health():
    return jsonify({"status": "ok"})


@app.post("/admin/watch")
def admin_watch():
    """
    (Re-)register the Gmail watch with Pub/Sub.
    Call this endpoint on every deploy and once a day to keep it fresh.
    Protect this with a secret header in production.
    """
    secret = request.headers.get("X-Admin-Secret", "")
    if secret != config.FLASK_SECRET_KEY:
        abort(403)

    result = gmail_handler.setup_gmail_watch()
    return jsonify(result)


@app.post("/webhook/pubsub")
def pubsub_webhook():
    """
    Receives Pub/Sub push notifications (HTTP POST).

    Pub/Sub delivers a JSON body like:
    {
      "message": {
        "data": "<base64-encoded JSON>",
        "messageId": "...",
        "publishTime": "..."
      },
      "subscription": "projects/.../subscriptions/..."
    }

    The decoded `data` field contains:
    {
      "emailAddress": "user@example.com",
      "historyId": "12345"
    }
    """
    envelope = request.get_json(silent=True)
    if not envelope:
        logger.warning("Pub/Sub webhook received non-JSON body")
        return jsonify({"error": "bad request"}), 400

    pubsub_message = envelope.get("message", {})
    encoded_data = pubsub_message.get("data", "")
    if not encoded_data:
        # Acknowledge empty messages so Pub/Sub doesn't retry forever
        return jsonify({"status": "ignored"}), 200

    try:
        notification = json.loads(base64.b64decode(encoded_data).decode("utf-8"))
    except Exception:
        logger.exception("Could not decode Pub/Sub message data")
        return jsonify({"error": "decode error"}), 400

    history_id: str = str(notification.get("historyId", ""))
    logger.info("Pub/Sub notification received: historyId=%s", history_id)

    if not history_id:
        return jsonify({"status": "ignored"}), 200

    # Use History API to get new messages since this historyId
    # We start from historyId - 1 to ensure we catch the triggering message
    start_id = str(max(1, int(history_id) - 1))
    new_messages = gmail_handler.get_history(start_id)

    total_new = 0
    for msg_stub in new_messages:
        try:
            total_new += _process_gmail_message(msg_stub["id"])
        except Exception:
            logger.exception("Error processing message %s", msg_stub.get("id"))

    logger.info("Pub/Sub processing complete: %d new job(s) sent", total_new)
    # Always return 200 to acknowledge the Pub/Sub message
    return jsonify({"status": "ok", "new_jobs": total_new}), 200


# ---------------------------------------------------------------------------
# Entry point
# ---------------------------------------------------------------------------

if __name__ == "__main__":
    app.run(host="0.0.0.0", port=config.PORT, debug=False)
