"""
Send notifications via Twilio (SMS) and SendGrid (email).
"""

import logging
from twilio.rest import Client as TwilioClient
from sendgrid import SendGridAPIClient
from sendgrid.helpers.mail import Mail, To, From, Subject, HtmlContent, PlainTextContent
import config

logger = logging.getLogger(__name__)

_twilio_client: TwilioClient | None = None
_sendgrid_client: SendGridAPIClient | None = None


def _twilio() -> TwilioClient:
    global _twilio_client
    if _twilio_client is None:
        _twilio_client = TwilioClient(config.TWILIO_ACCOUNT_SID, config.TWILIO_AUTH_TOKEN)
    return _twilio_client


def _sendgrid() -> SendGridAPIClient:
    global _sendgrid_client
    if _sendgrid_client is None:
        _sendgrid_client = SendGridAPIClient(config.SENDGRID_API_KEY)
    return _sendgrid_client


# --- Formatters ---------------------------------------------------------------

def _sms_body(jobs: list[dict]) -> str:
    lines = ["JobPulse Alert — new job(s) found!\n"]
    for i, job in enumerate(jobs[:5], 1):  # cap SMS at 5 jobs
        lines.append(f"{i}. {job['title']}")
        if job.get("company"):
            lines.append(f"   {job['company']}")
        lines.append(f"   {job['link']}")
    if len(jobs) > 5:
        lines.append(f"\n...and {len(jobs) - 5} more. Check your email for the full list.")
    return "\n".join(lines)


def _email_html(jobs: list[dict]) -> str:
    rows = ""
    for job in jobs:
        company_cell = f"<td style='padding:4px 12px;color:#555'>{job.get('company','')}</td>"
        rows += f"""
        <tr>
          <td style='padding:4px 12px;font-weight:bold'>
            <a href='{job["link"]}' style='color:#0073b1;text-decoration:none'>{job["title"]}</a>
          </td>
          {company_cell}
          <td style='padding:4px 12px'>
            <a href='{job["link"]}' style='background:#0073b1;color:#fff;padding:4px 10px;
               border-radius:4px;text-decoration:none;font-size:13px'>Apply</a>
          </td>
        </tr>"""

    return f"""
    <html><body style='font-family:Arial,sans-serif;max-width:700px;margin:auto'>
      <h2 style='color:#0073b1'>JobPulse — {len(jobs)} New Job Alert(s)</h2>
      <table cellspacing='0' cellpadding='0' width='100%'
             style='border-collapse:collapse;border:1px solid #e0e0e0'>
        <thead>
          <tr style='background:#f3f3f3'>
            <th style='padding:8px 12px;text-align:left'>Title</th>
            <th style='padding:8px 12px;text-align:left'>Company</th>
            <th style='padding:8px 12px;text-align:left'></th>
          </tr>
        </thead>
        <tbody>{rows}</tbody>
      </table>
      <p style='color:#999;font-size:12px;margin-top:24px'>
        Sent by JobPulse &mdash; your real-time job alert aggregator.
      </p>
    </body></html>"""


def _email_text(jobs: list[dict]) -> str:
    lines = [f"JobPulse — {len(jobs)} New Job Alert(s)\n"]
    for i, job in enumerate(jobs, 1):
        lines.append(f"{i}. {job['title']}")
        if job.get("company"):
            lines.append(f"   Company: {job['company']}")
        lines.append(f"   Link: {job['link']}\n")
    return "\n".join(lines)


# --- Senders ------------------------------------------------------------------

def send_sms(jobs: list[dict]) -> None:
    if not jobs:
        return
    body = _sms_body(jobs)
    try:
        msg = _twilio().messages.create(
            body=body,
            from_=config.TWILIO_FROM_NUMBER,
            to=config.TWILIO_TO_NUMBER,
        )
        logger.info("SMS sent: SID=%s", msg.sid)
    except Exception:
        logger.exception("Failed to send SMS")
        raise


def send_email(jobs: list[dict]) -> None:
    if not jobs:
        return
    subject_text = f"JobPulse: {len(jobs)} new job alert{'s' if len(jobs) != 1 else ''}"
    message = Mail(
        from_email=From(config.SENDGRID_FROM_EMAIL, "JobPulse"),
        to_emails=To(config.SENDGRID_TO_EMAIL),
        subject=Subject(subject_text),
        html_content=HtmlContent(_email_html(jobs)),
        plain_text_content=PlainTextContent(_email_text(jobs)),
    )
    try:
        resp = _sendgrid().send(message)
        logger.info("Email sent: status=%s", resp.status_code)
    except Exception:
        logger.exception("Failed to send email")
        raise


def notify(jobs: list[dict]) -> None:
    """Send both SMS and email for a list of job dicts."""
    if not jobs:
        logger.info("notify() called with empty job list — nothing to send")
        return
    send_sms(jobs)
    send_email(jobs)
