import requests
import os

FIREBASE_URL = os.environ.get("FIREBASE_URL")"

def save_data(slug, data):
    url = f"{FIREBASE_URL}/{slug}.json"
    requests.put(url, json=data)

def get_data(slug):
    url = f"{FIREBASE_URL}/{slug}.json"
    res = requests.get(url)
    return res.json()
