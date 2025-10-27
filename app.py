from flask import Flask, request, redirect, url_for, flash, render_template, jsonify
import os, json, requests, random, smtplib
from email.message import EmailMessage
from datetime import datetime, timezone

app = Flask(__name__)
app.config['MAX_CONTENT_LENGTH'] = 5 * 1024 * 1024
API_KEY = os.environ.get("HRFUNC_API_KEY")
app.secret_key = os.environ.get("SECRET_KEY")
UPLOAD_FOLDER = "/mnt/public/hrfunc/uploads"
TIMESTAMP_SUFFIX_FORMAT = "%Y-%m-%d_%H-%M-%S"


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
    msg["Subject"] = "HRF Submission Received"
    msg["From"] = from_email
    msg["To"] = recipient

    subset_value = (submission_metadata.get("dataset_subset") or "").strip().lower()
    if subset_value == "no":
        extra_note = (
            "We noticed this upload represents your full dataset. "
            "If you have the time, we encourage estimating HRFs from meaningful subsets "
            "(e.g., by demographic or condition) and sharing these estimated as well. These "
            "HRFs estimated from subsets help improve their representaiton in science through "
            "higher accuracy neural activity representation and improve downstream analyses."
        )
    elif subset_value == "yes":
        extra_note = (
            "Thank you for going the extra mile to estimate HRFs from a subset of your data. "
            "These nuanced contributions deepen our shared understanding of variability and improves "
            "representation in science of subjects estimated from through enhanced neural activity "
            "estimation."
        )
    else:
        extra_note = ""

    extra_note_block = f"{extra_note}\n\n" if extra_note else ""

    body = (
        f"Hello {submission_metadata.get('name', 'researcher')},\n\n"
        "Thank you for submitting your HRF estimates to HRfunc. We truly appreciate your "
        "contributions to the HRtree! Each HRF you share helps us understand hemodynamic "
        "response variability and supports more accurate neural activity estimation.\n\n"
        f"We successfully received your file '{submission_metadata.get('stored_filename')}'. "
        "At your earliest convenience, please review the details below and let us know at "
        "help@hrfunc.org if anything needs correction.\n\n"
        "Submission details:\n"
        f"  Study: {submission_metadata.get('study', 'N/A')}\n"
        f"  Area Codes: {submission_metadata.get('area_codes', 'N/A')}\n"
        f"  DOI: {submission_metadata.get('doi', 'N/A')}\n"
        f"  Email: {submission_metadata.get('email', 'N/A')}\n"
        f"  Phone Number: {submission_metadata.get('phone', 'N/A')}\n"
        f"  Dataset Ownership: {submission_metadata.get('dataset_ownership', 'N/A')}\n"
        f"  Dataset Permission: {submission_metadata.get('dataset_permission', 'N/A')}\n"
        f"  Dataset Owner: {submission_metadata.get('dataset_owner', 'N/A')}\n"
        f"  Dataset Owner Email: {submission_metadata.get('dataset_contact', 'N/A')}\n"
        f"  Used Unaltered HRfunc: {submission_metadata.get('hrfunc_standard', 'N/A')}\n"
        f"  Dataset Subset: {submission_metadata.get('dataset_subset', 'N/A')}\n"
        f"  HRfunc Modifications: {submission_metadata.get('hrfunc_modifications', 'N/A') or 'N/A'}\n"
        f"  Uploaded at (UTC): {submission_metadata.get('uploaded_at', 'N/A')}\n\n"
        "HRF experimental context:\n"
        f"  Task: {submission_metadata.get('task', 'N/A')}\n"
        f"  Condition(s): {submission_metadata.get('conditions', 'N/A')}\n"
        f"  Stimuli: {submission_metadata.get('stimuli', 'N/A')}\n"
        f"  Stimuli Medium: {submission_metadata.get('medium', 'N/A')}\n"
        f"  Stimuli Intensity: {submission_metadata.get('intensity', 'N/A')}\n"
        f"  Protocol: {submission_metadata.get('protocol', 'N/A')}\n"
        f"  Age: {submission_metadata.get('age', 'N/A')}\n"
        f"  Demographics: {submission_metadata.get('demographics', 'N/A')}\n"
        f"  Health Status: {submission_metadata.get('health-status', 'N/A')}\n"
        f"  Additional Comment: {submission_metadata.get('comment', 'N/A') or 'N/A'}\n\n"
        f"{extra_note_block}"
        "We greatly appreciate your contribution to the HRfunc community and "
        "cannot wait to hear about the insights you uncover!\n\n"
        "Best,\n"
        "The HRfunc Team"
    )
    msg.set_content(body)

    try:
        with smtplib.SMTP(smtp_host, smtp_port, timeout=10) as server:
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
        resp = requests.post(
            "https://flask.jib-jab.org/rmdig/upload_signup",
            files={"jsonFile": (filename, augmented_bytes)},
            headers={"x-api-key": API_KEY},
            timeout=10,
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

if __name__ == "__main__":
    port = int(os.environ.get("PORT", 8000))
    app.run(host="0.0.0.0", port=port)
