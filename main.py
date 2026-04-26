from flask import Flask, render_template, request, redirect, jsonify, session, url_for, send_from_directory
from HelperFunctions.firebase import get_user, save_user
import secrets
import os
import requests
from authlib.integrations.flask_client import OAuth
import razorpay
import time


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
        real_email = user.get("email")  

        for slug, bot in chatbots.items():

            if bot.get("expires_at") and now >= bot["expires_at"]:

                if not bot.get("expiry_email_sent"):
                    success = send_renewal_email(real_email, slug)  #  FIX

                    if success:
                        bot["expiry_email_sent"] = True

                bot["is_live"] = False
                bot["is_paid"] = False

                email_key = safe_email_key(email)

                requests.put(
                    f"{FIREBASE_URL}/users/{email_key}.json",
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

    public_url = f"https://lavinderai.onrender.com/{slug}"
    dashboard_url = "https://lavinderai.onrender.com/dashboard"

    data = {
        "from": "onboarding@resend.dev",
        "to": [to_email],
        "subject": "Chatbot Ready 🚀",
        "html": f""" <div style="font-family: Arial, sans-serif; background:#f4f6fb; padding:20px;">      <div style="max-width:600px; margin:auto; background:white; border-radius:12px; padding:30px; box-shadow:0 4px 12px rgba(0,0,0,0.08);">          <h2 style="color:#7c4dff; margin-bottom:10px;">🚀 Your Chatbot is Ready!</h2>          <p style="color:#555; font-size:15px;">       Your AI chatbot has been successfully created. You can now start using and managing it.     </p>      <div style="margin:25px 0;">              <p style="margin-bottom:8px; font-weight:bold;">🌐 Public Link</p>       <a href="{public_url}"           style="display:block; background:#edeaff; padding:12px; border-radius:8px; text-decoration:none; color:#333; font-size:14px;">          {public_url}       </a>      </div>      <div style="margin:25px 0;">              <p style="margin-bottom:8px; font-weight:bold;">⚙️ Dashboard Link</p>       <a href="{dashboard_url}"           style="display:block; background:#edeaff; padding:12px; border-radius:8px; text-decoration:none; color:#333; font-size:14px;">          {dashboard_url}       </a>      </div>  <p style="font-size:13px; color:#b26a00; background:#fff3cd; padding:10px; border-radius:8px;"> 🔐 You are signed in with Google. Do not share your account access with others.   Anyone with your account access can manage this chatbot. </p>      <hr style="margin:25px 0; border:none; border-top:1px solid #eee;">      <p style="font-size:13px; color:#888; text-align:center;">       Powered by <b>LavinderAI</b><br>       AI FAQ Chatbot for Businesses     </p>    </div>  </div>"""
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

@app.route('/pricing')
def price():
    return render_template("price.html")

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
            "expires_at": None,
            "stats": {"visitors": 0,"questions": 0}}

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
        chatbots = user.get("chatbots", {})

        if slug in chatbots:
            bot = chatbots[slug]

            print("FOUND BOT:", bot)

            now = int(time.time())

            # expiry check
            if not bot.get("is_live") or (bot.get("expires_at") and now > bot["expires_at"]):
                return "Not available or expired"

            # -----------------------------
            # FIXED STATS LOGIC
            # -----------------------------
            stats = bot.get("stats", {})

            stats["visitors"] = stats.get("visitors", 0) + 1

            bot["stats"] = stats  # update bot

            # save back to Firebase user
            email_key = email.replace(".", "_")

            requests.put(
                f"{FIREBASE_URL}/users/{email_key}.json",
                json=user
            )

            return render_template("chatbot.html", data=bot, slug=slug)

    print("BOT NOT FOUND")
    return "Chatbot not found", 404


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
    user_ref = None

    # ---------------- FIND BOT ----------------
    for email, user in all_users.items():
        chatbots = user.get("chatbots", {})

        if slug in chatbots:
            bot = chatbots[slug]
            user_ref = email
            break

    if not bot:
        return jsonify({"reply": "Chatbot not found"})

    # ---------------- CHECK STATUS ----------------
    if not bot.get("is_paid"):
        return jsonify({"reply": "This chatbot is not activated yet."})

    if bot.get("expires_at") and now > bot["expires_at"]:
        return jsonify({"reply": "This chatbot has expired. Please renew."})

    msg = request.json.get("message")

    if not msg:
        return jsonify({"reply": "Empty message"})

    # ---------------- UPDATE STATS ----------------
    stats = bot.get("stats", {})

    stats["questions"] = stats.get("questions", 0) + 1

    bot["stats"] = stats

    # save back to firebase
    email_key = user_ref.replace(".", "_")

    requests.put(
        f"{FIREBASE_URL}/users/{email_key}.json",
        json=all_users[user_ref]
    )

    # ---------------- AI RESPONSE ----------------
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

                # update firebase
                email_key = email.replace(".", "_")
                requests.put(
                    f"{FIREBASE_URL}/users/{email_key}.json",json=user)

                real_email = user.get("email")  
                send_activation_email(real_email, slug)

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
        "html": f"""<table width="100%" cellpadding="0" cellspacing="0" style="padding:20px;">     <tr>       <td align="center">          <!-- Card -->         <table width="500" cellpadding="0" cellspacing="0" style="background:#ffffff; border-radius:12px; padding:30px; box-shadow:0 4px 10px rgba(0,0,0,0.05);">                      <!-- Title -->           <tr>             <td align="center">               <h2 style="margin:0; color:#ff4d4d;">⚠️ Chatbot Expired</h2>               <p style="color:#555; font-size:14px;">Your LavinderAI chatbot is no longer active</p>             </td>           </tr>            <!-- Divider -->           <tr>             <td style="padding:20px 0;">               <hr style="border:none; border-top:1px solid #eee;">             </td>           </tr>            <!-- Message -->           <tr>             <td>               <p style="font-size:14px; color:#333;">                 Your chatbot <b> {slug} </b> has expired and is currently not responding to users.              ...isplay:inline-block; color:white; background:#ff4d4d; padding:12px 18px; border-radius:8px; text-decoration:none; font-size:14px;">                  Renew / Reactivate Chatbot               </a>             </td>           </tr>            <!-- Info -->           <tr>             <td style="padding-top:20px;">               <p style="font-size:13px; color:#666;">                 Reactivate your chatbot to continue answering customer queries with AI.               </p>             </td>           </tr>            <!-- Warning -->           <tr>             <td style="padding-top:15px;">               <p style="font-size:12px; color:#999;">                 ⏳ If not renewed, your chatbot data may be removed after a certain period.               </p>             </td>           </tr>          </table>          <!-- Footer -->         <p style="font-size:12px; color:#aaa; margin-top:15px;">           &copy; LavinderAI — AI FAQ Chatbot Service         </p>        </td>     </tr>   </table>  """
    }

    try:
        r = requests.post(url, headers=headers, json=data)

        print("STATUS:", r.status_code)
        print("RESPONSE:", r.text)

        return r.status_code == 200

    except Exception as e:
        print("ERROR:", e)
        return False

def send_activation_email(email, slug):

    url = "https://api.resend.com/emails"

    headers = {
        "Authorization": f"Bearer {RESEND_API_KEY}",
        "Content-Type": "application/json"
    }

    data = {
        "from": "onboarding@resend.dev",
        "to": [email],
        "subject": "Your chatbot has activated",
        "html": f"""<table width="100%" cellpadding="0" cellspacing="0" style="padding:20px;">     <tr>       <td align="center">          <!-- Card -->         <table width="500" cellpadding="0" cellspacing="0" style="background:#ffffff; border-radius:12px; padding:30px; box-shadow:0 4px 10px rgba(0,0,0,0.05);">                      <!-- Title -->           <tr>             <td align="center">               <h2 style="margin:0; color:#7c4dff;">🚀 Your Chatbot is Live!</h2>               <p style="color:#555; font-size:14px;">LavinderAI Activation Successful</p>             </td>           </tr>            <!-- Divider -->           <tr>             <td style="padding:20px 0;">               <hr style="border:none; border-top:1px solid #eee;">             </td>           </tr>            <!-- Public URL -->           <tr>             <td>               <p style="margin:0; font-size:14px;"><b>Public Chat Link:</b></p>               <a href="https://lavinderai.onrender.com/{slug}"                   style="...display:inline-block; margin-top:8px; color:#7c4dff; text-decoration:none; font-size:14px;">                  Go to Dashboard →               </a>             </td>           </tr>            <!-- Info -->           <tr>             <td style="padding-top:25px;">               <p style="font-size:13px; color:#666;">                 You can now start using your AI-powered FAQ chatbot.                   Customize responses anytime from your dashboard.               </p>             </td>           </tr>            <!-- Warning -->           <tr>             <td style="padding-top:15px;">               <p style="font-size:12px; color:#999;">                 🔒 This chatbot is linked to your account. Do not share your login access.               </p>             </td>           </tr>          </table>          <!-- Footer -->         <p style="font-size:12px; color:#aaa; margin-top:15px;">           &copy; LavinderAI — AI FAQ Chatbot Service         </p>        </td>     </tr>   </table> """
    }

    try:
        r = requests.post(url, headers=headers, json=data)
        print("RENEW EMAIL:", r.status_code, r.text)

        return r.status_code == 200  # return success
    except Exception as e:
        print("EMAIL ERROR:", e)
        return False

@app.route("/api/dashboard-data")
def dashboard_data():
    user_session = session.get("user")

    if not user_session:
        return jsonify({"error": "not logged in"})

    email = user_session.get("email")
    email_key = safe_email_key(email)
    user = get_user(email_key)

    return jsonify({
        "name": user.get("name"),
        "email": user.get("email"),
        "chatbots": user.get("chatbots", {})
    })
# ---------------- RUN ----------------
@app.before_request
def run_check():
    check_expired_bots()

@app.route("/cron-check")
def cron_check():
    check_expired_bots()
    return "OK"

    
#seo relates 
@app.route('/robots.txt')
def robots_txt():
    return send_from_directory('static', 'robots.txt')

@app.route('/sitemap.xml')
def sitemap_xml():
    return send_from_directory('static', 'sitemap.xml')

@app.route("/how-it-works")
def howItWorks():
    return render_template("how-it-works.html")

@app.route("/terms/")
def terms_slash():
    return render_template('terms.html')

@app.route("/how-it-works/")
def work_slash():
    return render_template("how-it-works.html")


@app.route("/create/")
def create_slash():
    return redirect("/create", code=301)


@app.route("/stats/<slug>")
def stats_page(slug):

    all_users = requests.get(f"{FIREBASE_URL}/users.json").json() or {}

    bot_data = None

    for user in all_users.values():
        chatbots = user.get("chatbots", {})

        if slug in chatbots:
            bot_data = chatbots[slug]
            break

    if not bot_data:
        return "Chatbot not found", 404

    return render_template("stats.html", slug=slug, data=bot_data)



@app.route("/about")
def about():
    return render_template("about.html")


@app.route("/api/stats/<slug>")
def stats_api(slug):

    all_users = requests.get(f"{FIREBASE_URL}/users.json").json()

    if not all_users:
        return jsonify({
            "error": "no_data",
            "visitors": 0,
            "questions": 0
        })

    for user in all_users.values():
        chatbots = user.get("chatbots", {})

        if slug in chatbots:
            bot = chatbots[slug]

            stats = bot.get("stats")

            if not stats:
                return jsonify({
                    "slug": slug,
                    "exists": True,
                    "visitors": 0,
                    "questions": 0
                })

            return jsonify({
                "slug": slug,
                "exists": True,
                "visitors": stats.get("visitors", 0),
                "questions": stats.get("questions", 0)
            })

    return jsonify({
        "slug": slug,
        "exists": False,
        "visitors": 0,
        "questions": 0
    })



if __name__ == "__main__":
    print("🚀 Server starting...")
    app.run()
