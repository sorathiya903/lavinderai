from flask import Flask, render_template, request, redirect, jsonify 
from HelperFunctions.firebase import save_data, get_data
import secrets 
import os
import requests

GROQ_API_KEY = os.getenv("GROQ_API_KEY")

if not GROQ_API_KEY:
    raise Exception("GROQ_API_KEY not set")


def ask_groq(system_prompt, user_msg):
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

    res = requests.post(url, headers=headers, json=data)
    result = res.json()

    try:
        return result["choices"][0]["message"]["content"]
    except:
        return "⚠️ AI error. Please try again."


app = Flask(__name__)

@app.route("/favicon.ico")
def favicon():
    return "", 204

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



@app.route("/", methods=["GET", "POST"])
def home():
    if request.method == "POST":
        email = request.form.get("email")
        name = request.form.get("name")
        slug = (request.form.get("slug") or "").lower().replace(" ", "-")
        content = request.form.get("content")
        secret_key = secrets.token_hex(8)
        if not name or not content or email:
            return "<h3>❌ All fields are required</h3>"

        if not slug:
            return "<h3>❌ Please enter a valid endpoint name</h3>"
        if get_data(slug):
            return "<h3>❌ This chatbot link is already in use. Please choose a unique name.</h3>"
        save_data(slug, {
        "name": name,
        "content": content,
        "secret": secret_key
        })

        return f"""
        <h3>✅ Chatbot Created!</h3>
        <p><b>Public URL:</b> <a href="/{slug}" target="_blank">/{slug}</a></p>
        <p><b>Dashboard:</b>
        <a href="/dashboard/{slug}?key={secret_key}" target="_blank">/dashboard/{slug}?key={secret_key}</a></p>
        <p style="color:red;">⚠️ Save this link!</p>
        """

    return render_template("index.html")

@app.route("/<slug>")
def chatbot(slug):
    data = get_data(slug)

    if not data:
        return "Not found"

    return render_template("chatbot.html", data=data or {}, slug=slug)


@app.route("/dashboard/<slug>", methods=["GET", "POST"])
def dashboard(slug):
    data = get_data(slug)

    if not data:
        return "Not found"

    user_key = request.args.get("key")

    #  Check key
    if user_key != data.get("secret"):
        return "<h3>❌ Unauthorized</h3>"

    if request.method == "POST":
        name = request.form.get("name")
        content = request.form.get("content")

        save_data(slug, {
            "name": name,
            "content": content,
            "secret": data.get("secret")
        })

        return redirect(f"/dashboard/{slug}?key={user_key}")

    return render_template("dashboard.html", data=data, slug=slug)


if __name__ == "__main__":
    app.run()
