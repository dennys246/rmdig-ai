from flask import Flask, request, redirect, url_for, flash, render_template, jsonify
import os, json, requests, random, smtplib
from email.message import EmailMessage
from datetime import datetime, timezone

app = Flask(__name__)
app.config['MAX_CONTENT_LENGTH'] = 5 * 1024 * 1024
app.secret_key = os.environ.get("SECRET_KEY")

TIMESTAMP_SUFFIX_FORMAT = "%Y-%m-%d_%H-%M-%S"

API_KEY = os.environ.get("RMDIG_API_KEY")

def send_confirmation_email(recipient, submission_metadata):
    """Send a confirmation email acknowledging receipt of the HRF submission."""
    if not recipient:
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
        " backcountry! We are limited in the resources we have available to us to collect this" 
        " this data and unfortunately can only accept so many people to join this season. We" 
        " will reach out in the next few weeks with whether you have been selected to join!\n\n"
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
def upload_signup():
    
    submission = {key: (value.strip() if isinstance(value, str) else value) for key, value in request.form.items()}
    uploaded_at = datetime.now(timezone.utc)
    timestamp_suffix = uploaded_at.strftime(TIMESTAMP_SUFFIX_FORMAT)
    filename = f"collection_signup_{timestamp_suffix}_{random.randint(1, 10000)}.json"
    payload = {
        "_collection_signup": {
            **{key: value for key, value in submission.items() if value},
            "submitted_at": uploaded_at.isoformat(),
        }
    }
    augmented_bytes = json.dumps(payload, separators=(",", ":")).encode("utf-8")

    # ---- Forward to API ----
    try:
        if not API_KEY:
            raise RuntimeError("RMDIG_API_KEY not set")

        resp = requests.post(
            "https://flask.jib-jab.org/rmdig/receive_signup",
            files={"jsonFile": (filename, augmented_bytes)},
            headers={"x-api-key": API_KEY},
            timeout=30,
        )
    except Exception as e:
        flash(f"Error contacting API: {e}", "error")
        return redirect(url_for("collection_signup"))

    # ---- Handle response ----
    if resp.status_code == 200:
        flash("Thanks for signing up! We'll reach out soon.", "success")
    else:
        flash(f"Signup failed: {resp.text}", "error")

    return redirect(url_for("collection_signup"))

@app.route("/receive_signup", methods=["POST"])
def receive_signup():
    # Check API key
    key = request.headers.get("x-api-key")
    if key != API_KEY:
        return jsonify({"error": "Unauthorized"}), 401

    # Handle file
    file = request.files.get("jsonFile")
    if not file:
        return jsonify({"error": "No file uploaded"}), 400

    filename = file.filename
    content = file.read()
    try:
        data = json.loads(content.decode("utf-8"))
    except Exception as e:
        return jsonify({"error": f"Invalid JSON: {e}"}), 400

    # Save file locally
    uploaded_at = datetime.now(timezone.utc)
    timestamp_suffix = uploaded_at.strftime(TIMESTAMP_SUFFIX_FORMAT)
    stored_filename = f"/mnt/public/rmdig/signups/snowpack_digger/{timestamp_suffix}_{random.randint(1,10000)}_{filename}"
    with open(stored_filename, "wb") as f:
        f.write(content)

    app.logger.info(f"Received file: {stored_filename}")
    return jsonify({"status": "success", "stored_filename": stored_filename}), 200

if __name__ == "__main__":
    port = int(os.environ.get("PORT", 8000))
    app.run(host="0.0.0.0", port=port)
