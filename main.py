from flask import Flask, render_template, request, redirect, jsonify, session, url_for
from HelperFunctions.firebase import get_user, save_user
import secrets
import os
import requests
from authlib.integrations.flask_client import OAuth

app = Flask(__name__)
app.secret_key = os.getenv("SECRET_KEY")
oauth = OAuth(app)

google = oauth.register(
    name='google',
    client_id=os.getenv("GOOGLE_CLIENT_ID"),
    client_secret=os.getenv("GOOGLE_CLIENT_SECRET"),
    server_metadata_url='https://accounts.google.com/.well-known/openid-configuration',
    client_kwargs={
        'scope': 'openid email profile'
    }
)



RESEND_API_KEY = os.getenv("RESEND_API_KEY")
FIREBASE_URL = os.getenv("FIREBASE_URL")
GROQ_API_KEY = os.getenv("GROQ_API_KEY")
instructions ="""You are a helpful AI assistant for a business.

Rules you must always follow:
- Give very short answers (maximum 2–3 lines).
- Do NOT use markdown, bullets, headings, or formatting of any kind.
- Respond in plain simple text only.
- Do NOT explain external concepts like APIs, CPUs, servers, frameworks, or technical internals unless the user explicitly asks "explain in detail".
- If the user asks general questions, answer only the direct point without extra information.
- Avoid long explanations, background details, or examples unless requested.
- Keep responses natural, direct, and minimal.
- Answer correctly from the given information
\n
"""


# ---------------- SAFE HELPERS ----------------

def safe_email_key(email):
    if not email:
        print("❌ email is None")
        return None
    return email.replace(".", "_")


# ---------------- EMAIL ----------------
@app.route("/logout")
def logout():
    session.clear()
    return redirect("/login")

@app.route("/login")
def login():
    return google.authorize_redirect(
        redirect_uri=url_for("google_callback", _external=True)
    )

@app.route("/auth/google/callback")
def google_callback():
    token = google.authorize_access_token()
    user_info = token.get("userinfo")

    email = user_info["email"]

    # store in session 🔐
    session["email"] = email

    # create user if not exists
    email_key = safe_email_key(email)
    user = get_user(email_key)

    if not user:
        user = {
            "email": email,
            "name": user_info.get("name", ""),
            "picture": user_info.get("picture", ""), 
            "chatbots": {}
        }
        save_user(email_key, user)

    return redirect("/dashboard")

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
    dashboard_url = "https://ai-faq-chatbot-for-businesses.onrender.com/dashboard"

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

@app.route("/delete/<slug>", methods=["POST"])
def delete_chatbot(slug):

    email = session.get("email")
    if not email:
        return redirect("/login")

    email_key = safe_email_key(email)
    user = get_user(email_key)

    if not user:
        return "❌ User not found"

    chatbots = user.get("chatbots", {})

    if slug not in chatbots:
        return "❌ Chatbot not found"

    print("🗑️ DELETING:", slug)

    del chatbots[slug]

    save_user(email_key, user)

    return redirect(f"/dashboard?email={email}")

@app.route("/edit/<slug>", methods=["GET", "POST"])
def edit_chatbot(slug):

    email = session.get("email")
    if not email:
        return redirect("/login")

    email_key = safe_email_key(email)
    user = get_user(email_key)

    if not user:
        return "❌ User not found"

    bot = user.get("chatbots", {}).get(slug)

    if not bot:
        return "❌ Chatbot not found"

    if request.method == "POST":

        name = request.form.get("name")
        content = request.form.get("content")

        if not name or not content:
            return "❌ Fields cannot be empty"

        bot["name"] = name
        bot["content"] = content

        save_user(email_key, user)

        print("✅ UPDATED BOT:", slug)

        return redirect(f"/dashboard")

    return render_template(
        "edit.html",
        email=email,
        slug=slug,
        data=bot
    )


@app.route("/create", methods=["GET", "POST"])
def create():
    email = session.get("email")

    if not email:
        return redirect("/login")
        
    if request.method == "POST":

        name = request.form.get("name")
        slug = (request.form.get("slug") or "").lower().replace(" ", "-")
        content = request.form.get("content")

        print("CREATE REQUEST:", email, name, slug)

        if not email or not name or not content or not slug:
            return "❌ Missing fields"

        email_key = safe_email_key(email)
        if not email_key:
            return "❌ Invalid email"

        user = get_user(email_key)

        if not user:
            user = {
                "name": name,
                "email": email,
                "chatbots": {}
            }
            # 🔥 FIX: ensure chatbots always exists
        if "chatbots" not in user:
            user["chatbots"] = {}
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
        return render_template("success.html", slug=slug)
        
    return render_template("index.html")


# ---------------- DASHBOARD ----------------

@app.route("/dashboard")
def dashboard():
    email = session.get("email")
    if not email:
        return redirect("/login")

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
    user=user,
    data=None,
    slug=None
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

@app.route("/launch/<slug>", methods=["GET", "POST"])
def launch(slug):
    email = session.get("email")
    if not email:
        return redirect("/login")

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


# ---------------- API CHAT ----------------

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

    if not data.get("is_live"):
        return jsonify({"reply": "Chatbot not active"})

    msg = request.json.get("message")

    if not msg:
        return jsonify({"reply": "Empty message"})

    info = data.get("content", "")
    system_prompt = instructions + info
    reply = ask_groq(system_prompt, msg)

    return jsonify({"reply": reply})

@app.route("/check-slug/<slug>")
def check_slug(slug):

    all_users = requests.get(f"{FIREBASE_URL}/users.json").json() or {}

    for user in all_users.values():
        for s in (user.get("chatbots") or {}).keys():
            if s == slug:
                return jsonify({"available": False})

    return jsonify({"available": True})
    

# ---------------- RUN ----------------

if __name__ == "__main__":
    print("🚀 Server starting...")
    app.run()
