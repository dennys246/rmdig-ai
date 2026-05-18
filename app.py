from flask import Flask, request, redirect, url_for, flash, render_template, jsonify
from flask_limiter import Limiter
from flask_limiter.util import get_remote_address
from werkzeug.utils import secure_filename
import os, json, random, smtplib, re, uuid, hmac
import requests
from email.message import EmailMessage
from datetime import datetime, timezone
from pathlib import Path
from typing import List, Dict

app = Flask(__name__)
app.config['MAX_CONTENT_LENGTH'] = 5 * 1024 * 1024
app.secret_key = os.environ.get("SECRET_KEY")

TIMESTAMP_SUFFIX_FORMAT = "%Y-%m-%d_%H-%M-%S"
SITE_BASE_URL = os.environ.get("SITE_BASE_URL")

API_KEY = os.environ.get("RMDIG_API_KEY")
TURNSTILE_VERIFY_URL = "https://challenges.cloudflare.com/turnstile/v0/siteverify"
SPAM_PROTECTED_FIELDS = {"website", "cf-turnstile-response"}
EMAIL_FORMAT_RE = re.compile(r"^[^@\s]+@[^@\s]+\.[^@\s]+$")
SIGNUP_STORAGE_DIR = "/mnt/public/rmdig/signups/snowpack_digger/"


def _client_ip():
    forwarded = request.headers.get("X-Forwarded-For", "")
    if forwarded:
        return forwarded.split(",")[0].strip()
    return get_remote_address()


limiter = Limiter(
    key_func=_client_ip,
    app=app,
    storage_uri="memory://",
)


def verify_turnstile(token, remote_ip=None):
    """Verify a Cloudflare Turnstile token. Returns True if verified, or if not configured.

    Fails open on network errors (honeypot is the cheap layer; Turnstile is defense in depth).
    Fails closed on a missing token when a secret is configured.
    """
    secret = os.environ.get("TURNSTILE_SECRET_KEY")
    if not secret:
        return True
    if not token:
        return False
    try:
        payload = {"secret": secret, "response": token}
        if remote_ip:
            payload["remoteip"] = remote_ip
        resp = requests.post(TURNSTILE_VERIFY_URL, data=payload, timeout=5)
        resp.raise_for_status()
        return bool(resp.json().get("success"))
    except Exception:
        app.logger.exception("Turnstile verification network error; allowing submission.")
        return True


@app.context_processor
def inject_seo_defaults():
    """Expose SEO-friendly defaults for templates without altering visible content."""
    base_url = SITE_BASE_URL or request.url_root.rstrip("/")
    canonical_url = f"{base_url}{request.path}"
    default_description = (
        "Rocky Mountain Digerati builds AI models for avalanche risk prediction, "
        "snowpack data collection, and mountain safety research."
    )
    keywords = [
        "avalanche risk prediction",
        "AI avalanche forecasting",
        "snowpack data",
        "avalanche datasets",
        "avalanche safety research",
        "mountain machine learning",
        "computer vision snow analysis",
        "AvAI",
        "RMDig",
    ]
    return {
        "canonical_url": canonical_url,
        "default_description": default_description,
        "default_keywords": ", ".join(keywords),
        "site_base_url": base_url,
        "turnstile_site_key": os.environ.get("TURNSTILE_SITE_KEY"),
    }

def send_confirmation_email(recipient, submission_metadata):
    """Send a confirmation email acknowledging receipt of the HRF submission."""
    if not recipient:
        return
    if not EMAIL_FORMAT_RE.match(recipient):
        app.logger.info("Skipping confirmation email: recipient failed format validation.")
        return

    smtp_host = os.environ.get("SMTP_HOST")
    smtp_port = int(os.environ.get("SMTP_PORT", "587"))
    smtp_user = os.environ.get("SMTP_USER")
    smtp_password = os.environ.get("SMTP_PASSWORD")
    from_email = os.environ.get("SMTP_FROM_EMAIL")

    if not smtp_host or not from_email:
        app.logger.warning("Skipping confirmation email, SMTP configuration incomplete.")
        return

    msg = EmailMessage()
    msg["Subject"] = "RMDigger Signup Confirmation"
    msg["From"] = from_email
    msg["To"] = recipient

    body = (
        f"Hello {submission_metadata.get('name')},\n\n"
        "Thank you for signing up to collect snowpack data for avalanche risk detection!"
        " We greatly appreciate your interest in joining us for data collection this season."
        " Through collecting more data we'll be able to train a high accuracy AI for predicting"
        " avalanche risk and with your help we're on step closer to helping protect lives in the"
        " backcountry!\n\nWe are limited in the resources we have available to us to collect this" 
        " this data and unfortunately can only accept so many people to join this season. We" 
        " will reach out in the next few weeks with whether you have been selected to join."
        " Even if you aren't able to join this season for data collection we anticipate releasing"
        " the AvAI app for anyone to collect data and analyze avalanche risk next season so stay tuned!\n\n"
        "Best,\n"
        "RMDig Team"
    )
    msg.set_content(body)

    try:
        with smtplib.SMTP(smtp_host, smtp_port, timeout=30) as server:
            if smtp_user and smtp_password:
                server.starttls()
                server.login(smtp_user, smtp_password)
            server.send_message(msg)
    except OSError:
        app.logger.exception("Unable to send confirmation email.")


def send_signup_email(filename, payload, augmented_bytes):
    """Email the signup submission details to the project team."""
    smtp_host = os.environ.get("SMTP_HOST")
    smtp_port = int(os.environ.get("SMTP_PORT", "587"))
    smtp_user = os.environ.get("SMTP_USER")
    smtp_password = os.environ.get("SMTP_PASSWORD")
    from_email = os.environ.get("SMTP_FROM_EMAIL")

    if not smtp_host or not from_email:
        raise RuntimeError("SMTP configuration incomplete")

    recipient = "dennys@rmdig.ai"
    submission = payload.get("_collection_signup", {})

    body_lines = [
        "New collection signup received:",
        "",
        *(f"{key}: {value}" for key, value in submission.items()),
    ]

    msg = EmailMessage()
    msg["Subject"] = f"Collection Signup from {submission.get('name', 'Unknown applicant')}"
    msg["From"] = from_email
    msg["To"] = recipient
    msg.set_content("\n".join(body_lines))
    msg.add_attachment(
        augmented_bytes,
        maintype="application",
        subtype="json",
        filename=filename,
    )

    with smtplib.SMTP(smtp_host, smtp_port, timeout=30) as server:
        if smtp_user and smtp_password:
            server.starttls()
            server.login(smtp_user, smtp_password)
        server.send_message(msg)

@app.route("/")
def home():
    return render_template("index.html")

@app.route("/about")
def about():
    return render_template("about.html")

@app.route("/contact")
def contact():
    return render_template("contact.html")

@app.route("/mission")
def mission():
    return render_template("mission.html")

@app.route("/models")
def models():
    return render_template("models.html")

@app.route("/guides")
def guides():
    return render_template("guides.html")

@app.route("/avai")
def avai():
    return render_template("avai.html")

@app.route("/snowgan")
def snowgan():
    return render_template("snowgan.html")

@app.route("/gan_finetuning")
def gan_finetuning():
    return render_template("gan_finetuning.html")

@app.route("/corediff")
def corediff():
    return render_template("corediff.html")

@app.route("/diffusion_finetuning")
def diffusion_finetuning():
    return render_template("diffusion_finetuning.html")

@app.route("/datasets")
def datasets():
    return render_template("datasets.html")

@app.route("/snowpack_dataset")
def snowpack_dataset():
    return render_template("snowpack_dataset.html")

@app.route("/events")
def events():
    return render_template("events.html")

@app.route("/ramblings")
def ramblings():
    return render_template("ramblings.html")

@app.route("/collection_signup")
def collection_signup():
    return render_template("collection_signup.html")

@app.route("/rmdig/upload_signup", methods=["POST"])
@limiter.limit("5 per hour")
def upload_signup():
    # Honeypot: real users never see the `website` field. Bots fill everything.
    # Silently flash success so the bot doesn't learn to bypass.
    if request.form.get("website", "").strip():
        app.logger.info("Signup blocked by honeypot.")
        flash("🎉 Thanks for signing up! We'll be in touch soon.", "success")
        return redirect(url_for("collection_signup"))

    if not verify_turnstile(
        request.form.get("cf-turnstile-response", ""),
        remote_ip=request.headers.get("CF-Connecting-IP") or request.remote_addr,
    ):
        flash("⚠️ Couldn't verify the captcha challenge. Please try again.", "error")
        return redirect(url_for("collection_signup"))

    submission = {
        key: (value.strip() if isinstance(value, str) else value)
        for key, value in request.form.items()
        if key not in SPAM_PROTECTED_FIELDS
    }
    uploaded_at = datetime.now(timezone.utc)
    timestamp_suffix = uploaded_at.strftime(TIMESTAMP_SUFFIX_FORMAT)
    filename = f"collection_signup_{timestamp_suffix}_{random.randint(1, 10000)}.json"
    payload = {
        "_collection_signup": {
            **{key: value for key, value in submission.items() if value},
            "submitted_at": uploaded_at.isoformat(),
        }
    }
    submission_metadata = payload["_collection_signup"]
    augmented_bytes = json.dumps(payload, separators=(",", ":")).encode("utf-8")

    # ---- Email submission ----
    try:
        send_signup_email(filename, payload, augmented_bytes)
    except Exception as e:
        app.logger.exception("Failed to send signup email.")
        flash("⚠️ We hit a snag sending your signup. Please try again shortly.", "error")
        return redirect(url_for("collection_signup"))

    recipient_email = submission_metadata.get("email")
    try:
        send_confirmation_email(recipient_email, submission_metadata)
    except Exception:
        app.logger.exception("Failed to send confirmation email.")

    flash("🎉 Thanks for signing up! We'll be in touch soon.", "success")
    return redirect(url_for("collection_signup"))

@app.route("/receive_signup", methods=["POST"])
@limiter.limit("100 per minute")
def receive_signup():
    if API_KEY is None:
        app.logger.error("/receive_signup invoked but RMDIG_API_KEY is not set")
        return jsonify({"error": "Server misconfigured"}), 503

    key = request.headers.get("x-api-key", "")
    if not hmac.compare_digest(key, API_KEY):
        return jsonify({"error": "Unauthorized"}), 401

    file = request.files.get("jsonFile")
    if not file:
        return jsonify({"error": "No file uploaded"}), 400

    client_filename = secure_filename(file.filename or "upload.json")
    content = file.read()
    try:
        json.loads(content.decode("utf-8"))
    except Exception as e:
        return jsonify({"error": f"Invalid JSON: {e}"}), 400

    uploaded_at = datetime.now(timezone.utc)
    timestamp_suffix = uploaded_at.strftime(TIMESTAMP_SUFFIX_FORMAT)
    stored_basename = f"{timestamp_suffix}_{uuid.uuid4().hex}.json"
    stored_filename = os.path.join(SIGNUP_STORAGE_DIR, stored_basename)
    with open(stored_filename, "wb") as f:
        f.write(content)

    app.logger.info(f"Received file (client_name={client_filename}): {stored_filename}")
    return jsonify({"status": "success", "stored_filename": stored_filename}), 200


def _get_page_last_modified(path: Path) -> str:
    """Return ISO8601 date for last modified timestamp of a template/static file."""
    try:
        mtime = path.stat().st_mtime
        return datetime.fromtimestamp(mtime, tz=timezone.utc).date().isoformat()
    except FileNotFoundError:
        return datetime.now(timezone.utc).date().isoformat()


def _sitemap_entries() -> List[Dict[str, str]]:
    """Define crawlable routes for the sitemap with metadata."""
    template_dir = Path(__file__).parent / "templates"
    url_specs = [
        ("/", "index.html", "1.0", "daily"),
        ("/mission", "mission.html", "0.9", "weekly"),
        ("/avai", "avai.html", "0.9", "weekly"),
        ("/models", "models.html", "0.8", "monthly"),
        ("/guides", "guides.html", "0.7", "weekly"),
        ("/snowpack_dataset", "snowpack_dataset.html", "0.9", "weekly"),
        ("/datasets", "datasets.html", "0.7", "monthly"),
        ("/snowgan", "snowgan.html", "0.7", "monthly"),
        ("/gan_finetuning", "gan_finetuning.html", "0.6", "monthly"),
        ("/corediff", "corediff.html", "0.6", "monthly"),
        ("/diffusion_finetuning", "diffusion_finetuning.html", "0.6", "monthly"),
        ("/events", "events.html", "0.5", "monthly"),
        ("/ramblings", "ramblings.html", "0.5", "monthly"),
        ("/collection_signup", "collection_signup.html", "0.6", "weekly"),
        ("/contact", "contact.html", "0.4", "yearly"),
        ("/about", "about.html", "0.4", "yearly"),
    ]

    entries = []
    for path, template, priority, freq in url_specs:
        lastmod = _get_page_last_modified(template_dir / template)
        entries.append(
            {
                "loc": path,
                "lastmod": lastmod,
                "changefreq": freq,
                "priority": priority,
            }
        )
    return entries


@app.route("/sitemap.xml", methods=["GET"])
def sitemap():
    base_url = request.url_root.rstrip("/")
    urls = _sitemap_entries()
    xml_parts = [
        '<?xml version="1.0" encoding="UTF-8"?>',
        '<urlset xmlns="http://www.sitemaps.org/schemas/sitemap/0.9">',
    ]
    for url in urls:
        xml_parts.append("  <url>")
        xml_parts.append(f"    <loc>{base_url}{url['loc']}</loc>")
        xml_parts.append(f"    <lastmod>{url['lastmod']}</lastmod>")
        xml_parts.append(f"    <changefreq>{url['changefreq']}</changefreq>")
        xml_parts.append(f"    <priority>{url['priority']}</priority>")
        xml_parts.append("  </url>")
    xml_parts.append("</urlset>")
    xml_response = "\n".join(xml_parts)
    return app.response_class(xml_response, mimetype="application/xml")


@app.route("/robots.txt", methods=["GET"])
def robots_txt():
    base_url = request.url_root.rstrip("/")
    lines = [
        "User-agent: *",
        "Allow: /",
        f"Sitemap: {base_url}/sitemap.xml",
    ]
    return app.response_class("\n".join(lines), mimetype="text/plain")

if __name__ == "__main__":
    port = int(os.environ.get("PORT", 8000))
    app.run(host="0.0.0.0", port=port)
