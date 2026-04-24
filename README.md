# JobPulse

Real-time job alert aggregator. Watches your Gmail inbox for job-alert emails
(LinkedIn, company career pages), extracts job listings, deduplicates them, and
instantly notifies you via **SMS (Twilio)** and **email (SendGrid)**.

## How it works

```
Gmail Inbox
    │  new email arrives
    ▼
Google Cloud Pub/Sub  ──push──►  Flask /webhook/pubsub
                                       │
                                  Gmail History API
                                  (fetch full message)
                                       │
                                   parser.py
                                  (extract jobs)
                                       │
                                   database.py
                                  (deduplication)
                                       │
                                   notifier.py
                              ┌────────┴────────┐
                           Twilio SMS       SendGrid email
```

## Prerequisites

| Service | What you need |
|---|---|
| Google Cloud | Project with Pub/Sub API enabled + service account with domain-wide delegation |
| Gmail | The account to monitor (must grant the service account access) |
| Twilio | Account SID, Auth Token, phone number |
| SendGrid | API key, verified sender email |
| Render (or any host) | To run the Flask server publicly so Pub/Sub can reach it |

---

## Local setup

### 1. Clone & install

```bash
git clone https://github.com/youruser/jobpulse.git
cd jobpulse
python -m venv .venv && source .venv/bin/activate
pip install -r requirements.txt
```

### 2. Configure environment variables

```bash
cp .env.example .env
# Edit .env with your real credentials
```

### 3. Google Cloud setup

1. Create a GCP project and enable the **Gmail API** and **Cloud Pub/Sub API**.

2. Create a **Pub/Sub topic** named `gmail-job-alerts`:
   ```bash
   gcloud pubsub topics create gmail-job-alerts
   ```

3. Create a **push subscription** pointing to your server:
   ```bash
   gcloud pubsub subscriptions create gmail-job-alerts-sub \
     --topic=gmail-job-alerts \
     --push-endpoint=https://your-app.onrender.com/webhook/pubsub \
     --ack-deadline=30
   ```

4. Grant Gmail permission to publish to the topic:
   ```bash
   gcloud pubsub topics add-iam-policy-binding gmail-job-alerts \
     --member=serviceAccount:gmail-api-push@system.gserviceaccount.com \
     --role=roles/pubsub.publisher
   ```

5. Create a **service account** with the **Gmail API** scope, enable
   **domain-wide delegation** (for G Suite/Workspace) or use OAuth2 user
   credentials for a personal Gmail. Download the JSON key file.

6. Set `GOOGLE_CREDENTIALS_JSON` in `.env` to the path of the JSON key file
   (or paste the raw JSON string for cloud deployments).

### 4. Register the Gmail watch

After the server is running, call:

```bash
curl -X POST http://localhost:8080/admin/watch \
     -H "X-Admin-Secret: YOUR_FLASK_SECRET_KEY"
```

This registers the Pub/Sub watch on your inbox. **The watch expires every 7 days**
— re-call this endpoint daily (e.g. via a Render cron job or a scheduled curl).

### 5. Run locally

```bash
python app.py
# or with gunicorn:
gunicorn app:app --bind 0.0.0.0:8080
```

Use [ngrok](https://ngrok.com/) to expose your local server for Pub/Sub testing:

```bash
ngrok http 8080
# update the Pub/Sub subscription push endpoint to the ngrok HTTPS URL
```

---

## Deploy to Render

1. Push this repo to GitHub.
2. Create a new **Web Service** on [Render](https://render.com):
   - **Build command:** `pip install -r requirements.txt`
   - **Start command:** `gunicorn app:app --bind 0.0.0.0:$PORT`
3. Add all environment variables from `.env.example` in the Render dashboard.
   For `GOOGLE_CREDENTIALS_JSON`, paste the raw JSON content of your key file.
4. After the first deploy, hit the `/admin/watch` endpoint to register the Gmail watch.
5. Set up a **Render Cron Job** (or any daily scheduler) to call `/admin/watch`
   once a day to keep the Gmail watch fresh.

---

## API endpoints

| Method | Path | Description |
|---|---|---|
| `GET` | `/health` | Health check — returns `{"status": "ok"}` |
| `POST` | `/webhook/pubsub` | Pub/Sub push endpoint (called by Google) |
| `POST` | `/admin/watch` | (Re-)register Gmail watch. Requires `X-Admin-Secret` header. |

---

## Project structure

```
jobpulse/
├── app.py            # Flask server + Pub/Sub webhook handler
├── gmail_handler.py  # Gmail API + Pub/Sub watch setup + message fetching
├── parser.py         # Extract job title/company/link from email HTML
├── database.py       # SQLite deduplication
├── notifier.py       # Twilio SMS + SendGrid email
├── config.py         # Environment variable loading
├── requirements.txt
├── .env.example
├── .gitignore
└── README.md
```

---

## Adding more job alert senders

Edit `JOB_ALERT_SENDERS` and `JOB_ALERT_SUBJECT_KEYWORDS` in [config.py](config.py)
to match additional email senders or subject line patterns.

---

## License

MIT
