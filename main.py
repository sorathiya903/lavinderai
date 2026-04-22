from flask import Flask, render_template, request, redirect, jsonify
from HelperFunctions.firebase import get_user, save_user
import secrets
import os
import requests

app = Flask(__name__)

RESEND_API_KEY = os.getenv("RESEND_API_KEY")
FIREBASE_URL = os.getenv("FIREBASE_URL")
GROQ_API_KEY = os.getenv("GROQ_API_KEY")


# ---------------- SAFE HELPERS ----------------

def safe_email_key(email):
    if not email:
        print("❌ email is None")
        return None
    return email.replace(".", "_")


# ---------------- EMAIL ----------------

def send_email(to_email, slug, secret_key):
    if not to_email:
        print("❌ send_email: missing email")
        return

    url = "https://api.resend.com/emails"

    headers = {
        "Authorization": f"Bearer {RESEND_API_KEY}",
        "Content-Type": "application/json"
    }

    public_url = f"https://ai-faq-chatbot-for-businesses.onrender.com/{slug}"
    dashboard_url = f"https://ai-faq-chatbot-for-businesses.onrender.com/dashboard?email={to_email}"

    data = {
        "from": "onboarding@resend.dev",
        "to": [to_email],
        "subject": "Chatbot Ready 🚀",
        "html": f"""
        <h2>Chatbot Ready</h2>
        <p>Public: {public_url}</p>
        <p>Dashboard: {dashboard_url}</p>
        """
    }

    try:
        r = requests.post(url, headers=headers, json=data)
        print("EMAIL STATUS:", r.status_code, r.text)
    except Exception as e:
        print("EMAIL ERROR:", e)


# ---------------- AI ----------------

def ask_groq(system_prompt, user_msg):
    if not user_msg:
        return "Empty message received"

    url = "https://api.groq.com/openai/v1/chat/completions"

    headers = {
        "Authorization": f"Bearer {GROQ_API_KEY}",
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

    try:
        res = requests.post(url, headers=headers, json=data)
        print("GROQ STATUS:", res.status_code)
        result = res.json()
        return result["choices"][0]["message"]["content"]
    except Exception as e:
        print("GROQ ERROR:", e)
        return "AI error"


# ---------------- ROUTES ----------------

@app.route("/")
def landing():
    return render_template("landing.html")


@app.route("/create", methods=["GET", "POST"])
def create():
    if request.method == "POST":

        email = request.form.get("email")
        name = request.form.get("name")
        slug = (request.form.get("slug") or "").lower().replace(" ", "-")
        content = request.form.get("content")

        print("CREATE REQUEST:", email, name, slug)

        if not email or not name or not content or not slug:
            return "❌ Missing fields"

        email_key = safe_email_key(email)
        if not email_key:
            return "❌ Invalid email"

        user = get_user(email_key) or {
            "name": name,
            "email": email,
            "chatbots": {}
        }

        print("USER BEFORE:", user)

        if slug in user.get("chatbots", {}):
            return "❌ Slug already exists"

        user["chatbots"][slug] = {
            "name": name,
            "content": content,
            "secret": secrets.token_hex(8),
            "is_paid": False,
            "is_live": False
        }

        save_user(email_key, user)

        print("USER SAVED SUCCESSFULLY")

        send_email(email, slug, user["chatbots"][slug]["secret"])

        return f"Created {slug}"

    return render_template("index.html")


# ---------------- DASHBOARD ----------------

@app.route("/dashboard")
def dashboard():

    email = request.args.get("email")
    print("DASHBOARD EMAIL:", email)

    email_key = safe_email_key(email)
    if not email_key:
        return "❌ Invalid email"

    user = get_user(email_key)

    print("DASHBOARD USER:", user)

    if not user:
        return "User not found"

    return render_template(
        "dashboard.html",
        email=email,
        chatbots=user.get("chatbots", {})
    )


# ---------------- CHATBOT FETCH (FIXED) ----------------

@app.route("/<slug>")
def chatbot(slug):

    print("LOOKUP SLUG:", slug)

    all_users = requests.get(f"{FIREBASE_URL}/users.json").json() or {}

    for email, user in all_users.items():
        for s, bot in (user.get("chatbots") or {}).items():

            if s == slug:
                print("FOUND BOT:", bot)

                if not bot.get("is_live"):
                    return "Not published yet"

                return render_template("chatbot.html", data=bot, slug=slug)

    print("BOT NOT FOUND")
    return "Chatbot not found"


# ---------------- LAUNCH ----------------

@app.route("/launch/<email>/<slug>", methods=["GET", "POST"])
def launch(email, slug):

    email_key = safe_email_key(email)
    user = get_user(email_key)

    if not user:
        return "User not found"

    bot = user.get("chatbots", {}).get(slug)

    if not bot:
        return "Bot not found"

    if request.method == "POST":
        print("LAUNCHING BOT:", slug)

        bot["is_paid"] = True
        bot["is_live"] = True

        save_user(email_key, user)

        return redirect(f"/{slug}")

    return f"""
    <h2>Launch {bot['name']}</h2>
    <form method="POST">
        <button>Pay & Launch</button>
    </form>
    """


# ---------------- API CHAT (FIXED) ----------------

@app.route("/api/chat/<slug>", methods=["POST"])
def chat_api(slug):

    data = None

    all_users = requests.get(f"{FIREBASE_URL}/users.json").json() or {}

    for user in all_users.values():
        for s, bot in (user.get("chatbots") or {}).items():
            if s == slug:
                data = bot
                break

    if not data:
        return jsonify({"reply": "Chatbot not found"})

    msg = request.json.get("message")

    if not msg:
        return jsonify({"reply": "Empty message"})

    system_prompt = data.get("content", "")

    reply = ask_groq(system_prompt, msg)

    return jsonify({"reply": reply})


# ---------------- RUN ----------------

if __name__ == "__main__":
    print("🚀 Server starting...")
    app.run()
