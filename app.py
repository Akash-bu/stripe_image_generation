import os, base64, uuid, time 
from flask import Flask, request, redirect, render_template, session, abort, url_for, send_file
from dotenv import load_dotenv
import stripe 
from openai import OpenAI

load_dotenv()

stripe.api_key = os.environ['STRIPE_SECRET_KEY']
OPENAI_API_KEY = os.environ['OPENAI_API_KEY']
DOMAIN = os.environ.get("DOMAIN", "http://localhost:5000")
PRICE_EUR_CENTS = 70
MODEL = "gpt-image-1"

app = Flask(__name__, static_folder="static", template_folder="templates")
app.secret_key = os.environ.get("FLASK_SECRET", "dev_secret")
client = OpenAI(api_key=OPENAI_API_KEY)

REDEEMED = set()

@app.route("/", methods=["GET"])
def index():
    return render_template("index.html")

@app.route("/pay", methods = ["POST"])
def pay():
    prompt = (request.form.get("prompt") or "").strip()
    if not prompt:
        return render_template("index.html", error = "Prompt required"), 400 
    session["prompt"] = prompt 
    checkout = stripe.checkout.Session.create(
        mode="payment",
        line_items=[{
            "price_data":{
                "currency":"eur",
                "unit_amount": PRICE_EUR_CENTS,
                "product_data":{
                    "name":"1 image generation"
                }
            },
            "quantity":1
        }],
        success_url=f"{DOMAIN}{url_for('index')}?sesion_id= {{CHECKOUT_SESSION_ID)}}&PAID=1",
        cancel_url=f"{DOMAIN}{url_for('index')}"
    )
    return redirect(checkout.url, code = 303)

@app.route("/generate", methods = ["POST"])
def generate():
    sid = request.form.get("session_id")
    if not sid:
        abort(400, "Missing session id")
    if sid in REDEEMED:
        abort(409, "This payment has already been used")
    sess = stripe.checkout.Session.retrieve(sid)
    if (sess.get("payment_status") != "paid") or (sess.get("amount_total", 0)) < PRICE_EUR_CENTS:
        abort(402, "payment not found or completed")
    REDEEMED.add(sid)
    prompt = (session.pop("prompt", "") or "").strip()
    if not prompt:
        abort(400, "prompt missing from session , please start again!")
    response = client.responses.create(
        model=MODEL,
        prompt=prompt,
        size = "1024x1024", 
        n=1
    )
    b64 = response.data[0].b64_json 
    image_bytes = base64.b64decode(b64)
    os.mkdir("static/generated", exist_ok = True)
    fname = f"static/generated/{int(time.time())}_{uuid.uuid4().hex}.png"
    with open(fname, "wb") as f:
        f.write(image_bytes)
    rel = "/" + fname 
    name = os.path.basename(fname)
    download_url = url_for('download_image', name = name)
    return render_template("index.html", image_url  = rel, download_url=download_url)

@app.route("/download/<name>", methods=["GET"])
def download_image(name):
    # basic sanitization - ensure we only serve files from static/generated
    if ".." in name or "/" in name or not name.endswith(".png"):
        abort(400, "Invalid filename")
    path = os.path.join("static", "generated", name)
    if not os.path.exists(path):
        abort(404)
    return send_file(path, as_attachment=True, download_name=name, mimetype="image/png")

if __name__ == "__main__":
    app.run(debug=True) 
