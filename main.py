from flask import Flask, render_template, request, redirect
from HelperFunctions.firebase import save_data, get_data

app = Flask(__name__)

@app.route("/", methods=["GET", "POST"])
def home():
    if request.method == "POST":
        name = request.form.get("name")
        slug = request.form.get("slug").lower().replace(" ", "-")
        content = request.form.get("content")

        save_data(slug, {
            "name": name,
            "content": content
        })

        return redirect(f"/{slug}")

    return render_template("index.html")

@app.route("/<slug>")
def chatbot(slug):
    data = get_data(slug)

    if not data:
        return "Not found"

    return render_template("chatbot.html", data=data)

if __name__ == "__main__":
    app.run(debug=True)
