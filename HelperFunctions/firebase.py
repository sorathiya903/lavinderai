import requests
import os

FIREBASE_URL = os.environ.get("FIREBASE_URL")

def save_data(slug, data):
    url = f"{FIREBASE_URL}/{slug}.json"
    requests.put(url, json=data)

def get_data(slug):
    url = f"{FIREBASE_URL}/{slug}.json"
    res = requests.get(url)
    return res.json()


def get_user(email):
    url = f"{FIREBASE_URL}/users/{email.replace('.', '_')}.json"
    return requests.get(url).json()

def save_user(email, data):
    url = f"{FIREBASE_URL}/users/{email.replace('.', '_')}.json"
    requests.put(url, json=data)
