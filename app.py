from flask import Flask, render_template

app = Flask(__name__)

@app.route("/")
def home():
    return render_template("index.html")

@app.route("/about")
def about():
    return render_template("about.html")

@app.route("/mission")
def mission():
    return render_template("mission.html")

@app.route("/ramblings")
def ramblings():
    return render_template("ramblings.html")

@app.route("/boldnet")
def boldnet():
    return render_template("boldnet.html")

@app.route("/contact")
def contact():
    return render_template("contact.html")

@app.route("/datasets")
def datasets():
    return render_template("datasets.html")

@app.route("/hrfunc")
def hrfunc():
    return render_template("hrfunc.html")

@app.route("/hrf_upload")
def hrf_upload():
    return render_template("hrf_upload.html")

@app.route("/snowgan")
def snowgan():
    return render_template("snowgan.html")

@app.route("/snowpack_dataset")
def snowpack_dataset():
    return render_template("snowpack_dataset.html")

@app.route("/tools")
def tools():
    return render_template("tools.html")


if __name__ == "__main__":
    app.run(debug=True)