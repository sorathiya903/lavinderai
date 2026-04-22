from flask import Flask, render_template, request, redirect, jsonify, render_template_string
from HelperFunctions.firebase import save_data, get_data, get_user, save_user
import secrets
import os
import requests

app = Flask(__name__)

RESEND_API_KEY = os.getenv("RESEND_API_KEY")
FIREBASE_URL = os.environ.get("FIREBASE_URL")

# ---------------- EMAIL ----------------

def send_email(to_email, slug, secret_key):
    url = "https://api.resend.com/emails"

    headers = {
        "Authorization": f"Bearer {RESEND_API_KEY}",
        "Content-Type": "application/json"
    }

    public_url = f"https://ai-faq-chatbot-for-businesses.onrender.com/{slug}"
    dashboard_url = f"https://ai-faq-chatbot-for-businesses.onrender.com/dashboard/{slug}?key={secret_key}"

    data = {
        "from": "onboarding@resend.dev",
        "to": [to_email],
        "subject": "Your Chatbot is Ready 🚀",
        "html": f"""
        <h2>Your chatbot is ready!</h2>
        <p><b>Public URL:</b> {public_url}</p>
        <p><b>Dashboard:</b> {dashboard_url}</p>
        <p style="color:red;">Save this link safely.</p>
        """
    }

    try:
        requests.post(url, headers=headers, json=data)
    except:
        pass


# ---------------- AI (optional) ----------------

def ask_groq(system_prompt, user_msg):
    url = "https://api.groq.com/openai/v1/chat/completions"

    headers = {
        "Authorization": f"Bearer {os.getenv('GROQ_API_KEY')}",
        "Content-Type": "application/json"
    }

    data = {
        "model": "groq/compound-mini",
        "messages": [
            {"role": "system", "content": system_prompt},
            {"role": "user", "content": user_msg}
        ],
        "temperature": 0.3,
        "max_tokens": 90
    }

    res = requests.post(url, headers=headers, json=data)
    result = res.json()

    try:
        return result["choices"][0]["message"]["content"]
    except:
        return "AI error"


# ---------------- ROUTES ----------------

@app.route("/")
def landing():
    return render_template("landing.html")


@app.route("/terms")
def terms():
    return render_template("terms.html")


# ---------------- CREATE CHATBOT ----------------

@app.route("/create", methods=["GET", "POST"])
def create():
    if request.method == "POST":

        email = request.form.get("email")
        name = request.form.get("name")
        slug = (request.form.get("slug") or "").lower().replace(" ", "-")
        content = request.form.get("content")
        secret_key = secrets.token_hex(8)

        if not email or not name or not content:
            return "All fields required"

        email_key = email.replace(".", "_")

        user = get_user(email_key) or {
            "name": name,
            "email": email,
            "chatbots": {}
        }

        if slug in user["chatbots"]:
            return "Chatbot already exists"

        user["chatbots"][slug] = {
            "name": name,
            "content": content,
            "secret": secret_key,
            "is_paid": False,
            "is_live": False
        }

        save_user(email_key, user)
        send_email(email, slug, secret_key)

        return f"""
        <h2>Chatbot Created</h2>
        <p>Public: <a href="/{slug}">/{slug}</a></p>
        <p>Dashboard: <a href="/dashboard/{slug}?key={secret_key}">Open</a></p>
        """

    return render_template("index.html")


# ---------------- PUBLIC CHATBOT ----------------

@app.route("/<slug>")
def chatbot(slug):

    all_users = requests.get(f"{FIREBASE_URL}/users.json").json() or {}

    for email, user in all_users.items():
        for s, bot in user.get("chatbots", {}).items():

            if s == slug:

                if not bot.get("is_live"):
                    return "Not published yet"

                return render_template("chatbot.html", data=bot, slug=slug)

    return "Not found"


# ---------------- DASHBOARD ----------------

@app.route("/dashboard", methods=["GET", "POST"])
def dashboard():

    email = request.args.get("email")
    email_key = email.replace(".", "_")

    user = get_user(email_key)

    if not user:
        return "User not found"

    edit_slug = request.args.get("edit")

    if request.method == "POST" and edit_slug:

        user["chatbots"][edit_slug]["name"] = request.form.get("name")
        user["chatbots"][edit_slug]["content"] = request.form.get("content")

        save_user(email_key, user)

        return redirect(f"/dashboard?email={email}")

    edit_bot = None
    if edit_slug:
        edit_bot = user["chatbots"].get(edit_slug)

    return render_template(
        "dashboard.html",
        user=user,
        chatbots=user.get("chatbots", {}),
        email=email,
        edit_bot=edit_bot,
        edit_slug=edit_slug
    )



# ---------------- LAUNCH (PAY ₹50) ----------------

@app.route("/launch/<email>/<slug>", methods=["GET", "POST"])
def launch(email, slug):

    email_key = email.replace(".", "_")
    user = get_user(email_key)

    if not user or slug not in user.get("chatbots", {}):
        return "Not found"

    bot = user["chatbots"][slug]

    if request.method == "POST":
        bot["is_paid"] = True
        bot["is_live"] = True

        save_user(email_key, user)

        return redirect(f"/{slug}")

    return f"""
    <h2>Launch {bot['name']}</h2>
    <p>Pay ₹50 to publish chatbot</p>
    <form method="POST">
        <button>Pay ₹50 & Launch</button>
    </form>
    """


# ---------------- RUN ----------------

if __name__ == "__main__":
    app.run()
