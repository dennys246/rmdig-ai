from flask import Flask, request, redirect, url_for, flash, render_template
import os
import json

app = Flask(__name__)

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

@app.route("/avai")
def avai():
    return render_template("avai.html")

@app.route("/snowgan")
def snowgan():
    return render_template("snowgan.html")

@app.route("/corediff")
def corediff():
    return render_template("corediff.html")

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

if __name__ == "__main__":
    port = int(os.environ.get("PORT", 8000))
    app.run(host="0.0.0.0", port=port)