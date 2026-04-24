from flask import Flask, render_template, request, redirect, jsonify, session, url_for
from HelperFunctions.firebase import get_user, save_user
import secrets
import os
import requests
from authlib.integrations.flask_client import OAuth
import razorpay
import time
from apscheduler.schedulers.background import BackgroundScheduler
import atexit
atexit.register(lambda: scheduler.shutdown())


razorclient = razorpay.Client(auth=(os.getenv("RAZORPAY_KEY"), os.getenv("RAZORPAY_SECRET")))


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


def is_bot_active(bot):
    now = int(time.time())
    return bot.get("expires_at") and now < bot["expires_at"]

def check_expired_bots():
    all_users = requests.get(f"{FIREBASE_URL}/users.json").json() or {}
    now = int(time.time())

    for email, user in all_users.items():
        chatbots = user.get("chatbots", {})

        for slug, bot in chatbots.items():

            if bot.get("expires_at") and now > bot["expires_at"]:

                if not bot.get("expiry_email_sent"):
                    send_renewal_email(email, slug)
                    bot["expiry_email_sent"] = True

                bot["is_live"] = False
                bot["is_paid"] = False


                requests.put(
                    f"{FIREBASE_URL}/users/{email}.json",
                    json=user
                )

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

@app.route("/delete-account", methods=["POST"])
def delete_account():
    user = session.get("user")

    if not user:
        return redirect("/login")

    email = user["email"]
    if not email:
        return redirect("/login")

    email_key = safe_email_key(email)

    requests.delete(f"{FIREBASE_URL}/users/{email_key}.json")

    session.clear()
    return redirect("/")



@app.route("/auth/google/callback")
def google_callback():
    token = google.authorize_access_token()
    user_info = token.get("userinfo")

    if not user_info:
        return "Auth failed"

    email = user_info.get("email")
    picture = user_info.get("picture")

    session["user"] = {
        "email": email,
        "name": user_info.get("name"),
        "picture": picture
    }

    email_key = safe_email_key(email)
    user = get_user(email_key)

    if not user:
        user = {
            "email": email,
            "name": user_info.get("name"),
            "picture": picture,
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

    user = session.get("user")
    if not user:
        return redirect("/login")

    email = user.get("email")
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

    return redirect("/dashboard")

@app.route("/edit/<slug>", methods=["GET", "POST"])
def edit_chatbot(slug):
    user = session.get("user")
    if not user:
        return redirect("/login")

    email = user.get("email")

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

        return redirect("/dashboard")

    return render_template(
        "edit.html",
        email=email,
        slug=slug,
        data=bot
    )


@app.route("/terms")
def terms():
    return render_template("terms.html")


@app.route("/create", methods=["GET", "POST"])
def create():
    user = session.get("user")
    if not user:
        return redirect("/login")
        
    email = user["email"]
     

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
            # FIX: ensure chatbots always exists
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
            "is_live": False,
            "created_at": int(time.time()),
            "expires_at": None
        }

        save_user(email_key, user)

        print("USER SAVED SUCCESSFULLY")

        send_email(email, slug, user["chatbots"][slug]["secret"])
        return render_template("success.html", slug=slug)
        
    user_session = session.get("user") or {}

    return render_template("index.html",user=user,email=email,name=user_session.get("name"),picture=user_session.get("picture"))

# ---------------- DASHBOARD ----------------

@app.route("/dashboard")
def dashboard():
    user_session = session.get("user")

    if not user_session:
        return redirect("/login")

    email = user_session.get("email")

    if not email:
        return redirect("/login")

    email_key = safe_email_key(email)
    user = get_user(email_key)

    if not user:
        return "User not found"

    return render_template(
        "dashboard.html",
        email=email,
        user=user,
        picture=user_session.get("picture")
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

                now = int(time.time())

                if not bot.get("is_live") or (bot.get("expires_at") and now > bot["expires_at"]):
                    return "Not available or expired"
  
                return render_template("chatbot.html", data=bot, slug=slug)

    print("BOT NOT FOUND")
    return "Chatbot not found"


# ---------------- LAUNCH ----------------

@app.route("/launch/<slug>", methods=["GET", "POST"])
def launch(slug):
    user = session.get("user")
    if not user:
        return redirect("/login")
        
    email = user.get("email")

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
        
        bot["expires_at"] = int(time.time()) + (30 * 24 * 60 * 60)
        

        save_user(email_key, user)

        return redirect(f"/{slug}")

    return f"""
    <h2>Launch {bot['name']}</h2>
    <form method="POST">
        <button>Pay & Launch</button>
    </form>
    """

@app.route("/preview/<slug>")
def preview(slug):
    user = session.get("user")
    if not user:
        return redirect("/login")

    email = user.get("email")
    email_key = safe_email_key(email)
    user_data = get_user(email_key)

    bot = user_data.get("chatbots", {}).get(slug)

    if not bot:
        return "Bot not found"

    return render_template("preview.html", data=bot, slug=slug)

# ---------------- API CHAT ----------------

@app.route("/api/chat/<slug>", methods=["POST"])
def chat_api(slug):

    all_users = requests.get(f"{FIREBASE_URL}/users.json").json() or {}
    now = int(time.time())

    bot = None

    for user in all_users.values():
        for s, b in (user.get("chatbots") or {}).items():
            if s == slug:
                bot = b
                break

    if not bot:
        return jsonify({"reply": "Chatbot not found"})

    #  NOT ACTIVE IF NOT PAID
    if not bot.get("is_paid"):
        return jsonify({"reply": "This chatbot is not activated yet."})

    #  EXPIRED CHECK (MOST IMPORTANT)
    if bot.get("expires_at") and now > bot["expires_at"]:
        return jsonify({"reply": "This chatbot has expired. Please renew."})

    msg = request.json.get("message")

    if not msg:
        return jsonify({"reply": "Empty message"})

    system_prompt = instructions + bot.get("content", "")
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




@app.route("/create-order/<slug>", methods=["POST"])
def create_order(slug):
    data = {
        "amount": 100,  # ₹1 = 100 paise (change as needed)
        "currency": "INR",
        "payment_capture": 1
    }

    order = razorclient.order.create(data)

    return jsonify({
        "order_id": order["id"],
        "amount": 100,
        "key": os.getenv("RAZORPAY_KEY")
    })



@app.route("/verify-payment/<slug>", methods=["POST"])
def verify_payment(slug):
    data = request.json

    try:
        params = {
            "razorpay_order_id": data["razorpay_order_id"],
            "razorpay_payment_id": data["razorpay_payment_id"],
            "razorpay_signature": data["razorpay_signature"]
        }

        # verify signature
        razorclient.utility.verify_payment_signature(params)

        # get all users
        all_users = requests.get(f"{FIREBASE_URL}/users.json").json() or {}

        now = int(time.time())

        for email, user in all_users.items():
            chatbots = user.get("chatbots") or {}

            if slug in chatbots:
                bot = chatbots[slug]

                bot["is_paid"] = True
                bot["is_live"] = True
                bot["created_at"] = now
                bot["expires_at"] = now + (30 * 24 * 60 * 60)

                # DO NOT permanently trust is_live
                

                # update firebase
                email_key = email.replace(".", "_")
                requests.put(
                    f"{FIREBASE_URL}/users/{email_key}.json",json=user)

        return jsonify({"status": "success"})

    except Exception as e:
        return jsonify({"status": "failed", "error": str(e)})

#debugging 

@app.route("/debug/session")
def debug_session():
    return dict(session)

#chatbot expiry
def send_renewal_email(email, slug):

    url = "https://api.resend.com/emails"

    headers = {
        "Authorization": f"Bearer {RESEND_API_KEY}",
        "Content-Type": "application/json"
    }

    data = {
        "from": "onboarding@resend.dev",
        "to": [email],
        "subject": "Your chatbot has expired ⚠️",
        "html": f"""
        <h2>Renew Your Chatbot</h2>
        <p>Your chatbot <b>{slug}</b> has expired.</p>
        <p>Pay ₹50 to reactivate it again.</p>
        <a href='https://ai-faq-chatbot-for-businesses.onrender.com/dashboard'>
        Go to Dashboard
        </a>
        """
    }

    requests.post(url, headers=headers, json=data)
# ---------------- RUN ----------------
scheduler = BackgroundScheduler()
scheduler.add_job(check_expired_bots, 'interval', minutes=1)
scheduler.start()

if __name__ == "__main__":
    print("🚀 Server starting...")
    app.run()
