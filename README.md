# 🚀 LavinderAI

<p align="center">
  <b>AI FAQ Chatbot for Businesses</b><br>
  Create, deploy, and manage smart AI chatbots in minutes.
</p>

<p align="center">
  <img src="https://img.shields.io/badge/Status-Live-success?style=for-the-badge">
  <img src="https://img.shields.io/badge/Plan-Free%20%7C%20Pro-purple?style=for-the-badge">
  <img src="https://img.shields.io/badge/Built%20With-Flask-blue?style=for-the-badge">
  <img src="https://img.shields.io/badge/AI-Groq-orange?style=for-the-badge">
</p>

---

## 🌐 Live Demo
👉 https://lavinderai-yp7v.onrender.com (Login required)
   https://lavinderai-yp7v.onrender.com/demo (No login required)

---

## 📌 About
LavinderAI is a SaaS platform that allows users to:

- 🤖 Create AI-powered chatbots  
- 🔗 Share them using a public link  
- 📊 Track usage (visitors & questions)  
- 💳 Upgrade to Pro for advanced features  

Built with simplicity and performance in mind.

---

## ⚙️ Features

| Feature | Free Plan | Pro Plan |
|--------|----------|----------|
| Create Chatbot | ✅ 1 bot | ✅ Unlimited |
| AI Responses | ✅ Limited (5 preview) | ✅ Unlimited |
| Public Access | ❌ | ✅ |
| Stats Dashboard | ❌ | ✅ |
| QR Code | ✅ | ✅ |
| Custom Content | ✅ | ✅ |

---

## 🧠 How It Works

1. User logs in with Google  
2. Creates chatbot with custom content  
3. Tests chatbot (Free plan)  
4. Upgrades to Pro  
5. Launches chatbot publicly  
6. Tracks stats via dashboard  

---

## 🏗️ Tech Stack

| Category | Technology |
|----------|-----------|
| Backend | Flask (Python) |
| Database | Firebase Realtime DB |
| Authentication | Google OAuth |
| Payments | Razorpay |
| AI Engine | Groq API |
| Hosting | Render |

---

## 🔐 Security

- 🔑 Google OAuth authentication (no passwords stored)
- 🔒 Secure session handling
- 🧾 Payment verification via Razorpay signature
- 🚫 Protected API routes for Pro users
- 🛡️ Slug validation to prevent conflicts

---

## 📊 Stats Tracking

LavinderAI tracks:
- 👥 Visitors
- 💬 Questions asked
- 📈 Engagement ratio

All data is securely stored per chatbot.

---

## 💳 Pricing Strategy

- 🆓 Free Plan → Limited usage for testing  
- 💎 Pro Plan → Full access & public bots  

> Designed to help users try before they buy.

---


🔗 API Example (Detailed)

## 🧪 API Usage

### Chat with Bot

**Endpoint:**

POST /api/chat/<slug>

**Example Request:**
```bash
curl -X POST https://lavinderai-yp7v.onrender.com/api/chat/demo-bot \
-H "Content-Type: application/json" \
-d '{"message":"Hello"}'
```

Request Body:

```
{
  "message": "Hello"
}
```

Success Response:
```
{
  "reply": "Hi! How can I help?",
  "remaining": 3
}
```
When Free Limit Ends:
```
{
  "reply": "Free preview limit reached. Upgrade to Pro."
}
```
Errors:
```
{
  "reply": "Chatbot not found"
}
```

---

Stats API (Pro Only)
```
GET /api/stats/<slug>
```
Response:
```
{
  "slug": "demo-bot",
  "exists": true,
  "visitors": 120,
  "questions": 340
}
```
---

## Git (Installation & Setup)

### 1. Clone Repository
```bash
git clone https://github.com/your-username/lavinderai.git
cd lavinderai
```
2. Create Virtual Environment

```
python -m venv venv

```

-  Mac/Linux
  ```For Linux/Mac
source venv/bin/activate
```   
- Windows 
```For Windows
venv\Scripts\activate
```

3. Install Dependencies
```
pip install -r requirements.txt

```
4. Setup Environment Variables

Create a .env file:
```
SECRET_KEY=your_secret_key
FIREBASE_URL=your_firebase_url
GOOGLE_CLIENT_ID=your_google_client_id
GOOGLE_CLIENT_SECRET=your_google_client_secret
RAZORPAY_KEY=your_key
RAZORPAY_SECRET=your_secret
GROQ_API_KEY=your_groq_key

```
5. Run Server
```
python app.py
```
Server will start at:
```
http://127.0.0.1:5000
```
---
