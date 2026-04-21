import requests

FIREBASE_URL = "https://chatting-e3bb2-default-rtdb.firebaseio.com/chatbotsFGH"

def save_data(slug, data):
    url = f"{FIREBASE_URL}/{slug}.json"
    requests.put(url, json=data)

def get_data(slug):
    url = f"{FIREBASE_URL}/{slug}.json"
    res = requests.get(url)
    return res.json()
