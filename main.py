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

@app.route("/api/chat/<slug>", methods=["POST"])
def chat_api(slug):
    data = get_data(slug)

    if not data:
        return {"reply": "Chatbot not found"}

    user_msg = request.json.get("message")
    system_prompt = data.get("content", "") + """
    Rules:
        - Always give short and concise answers (max 2-3 lines)
        - Do NOT use markdown, no bullet points, no formatting
        - Use plain simple text only
        - Only give long answers if the user explicitly asks for "explain" or "details"
        """
    # 🤖 Get AI reply
    reply = ask_groq(system_prompt, user_msg)

    return jsonify({"reply": reply})

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
            return "Slug already exists"

        user["chatbots"][slug] = {
            "name": name,
            "content": content,
            "secret": secret_key,
            "is_paid": False,
            "is_live": False
        }

        save_user(email_key, user)

        return f"""
        <h2>Chatbot Created</h2>
        <p>Dashboard: /dashboard?email={email}</p>
        <p>Public: /{slug}</p>
        <p>Launch: /launch/{email}/{slug}</p>
        """

    return render_template("index.html")


# ---------------- DASHBOARD (MAIN CONTROL PANEL) ----------------
@app.route("/dashboard")
def dashboard():

    email = request.args.get("email")
    email_key = email.replace(".", "_")

    user = get_user(email_key)

    if not user:
        return "User not found"

    return render_template(
        "dashboard.html",
        email=email,
        chatbots=user.get("chatbots", {})
    )


# ---------------- PUBLIC CHATBOT ----------------
@app.route("/<slug>")
def chatbot(slug):

    from HelperFunctions.firebase import FIREBASE_URL
    import requests

    all_users = requests.get(f"{FIREBASE_URL}/users.json").json() or {}

    for user in all_users.values():
        for s, bot in user.get("chatbots", {}).items():

            if s == slug:

                if not bot.get("is_live"):
                    return "Not published yet"

                return render_template("chatbot.html", data=bot, slug=slug)

    return "Not found"


# ---------------- LAUNCH (PAY ₹50) ----------------
@app.route("/launch/<email>/<slug>", methods=["GET", "POST"])
def launch(email, slug):

    email_key = email.replace(".", "_")
    user = get_user(email_key)

    if not user or slug not in user.get("chatbots", {}):
        return "Not found"

    bot = user["chatbots"][slug]

    if request.method == "POST":

        # payment success (mock)
        bot["is_paid"] = True
        bot["is_live"] = True

        save_user(email_key, user)

        return redirect(f"/{slug}")

    return f"""
    <h2>Launch {bot['name']}</h2>
    <p>Pay ₹50 to make chatbot live</p>

    <form method="POST">
        <button>Pay & Launch</button>
    </form>
    """
# ---------------- RUN ----------------

if __name__ == "__main__":
    app.run()
