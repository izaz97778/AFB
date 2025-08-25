# 📤 Telegram Auto Forward Bot

A powerful Telegram bot that auto-forwards messages from multiple source channels to a target channel.  
Built using [Pyrogram](https://github.com/pyrogram/pyrogram), supports per-channel message tracking using MongoDB and handles `FloodWait` automatically.

---

## 🚀 Features

- Forward messages from multiple **source channels**
- Copy messages to the **target channel**
- **Avoid duplicate forwarding** (tracks last message per source)
- Handles **FloodWait** automatically
- **Asynchronous** and fast
- MongoDB-based **resume support**
- Can be hosted on **Koyeb**, **Heroku**, or **any VPS**

---

## 🧠 How It Works

- Listens for messages in all channels listed in `SOURCE_CHANNELS`
- For each message:
  - Checks if already forwarded using MongoDB
  - If new, forwards it to `TARGET_CHANNEL`
  - Updates the last forwarded message ID in MongoDB
  - Waits out `FloodWait` if hit

---

## 📁 Project Structure

📦 project/ ├── bot.py                # Main bot file ├── requirements.txt      # All Python dependencies ├── app.py                # Optional Flask healthcheck server ├── utils.py              # Utility functions (MongoDB operations) └── README.md             # This file

---

## ⚙️ Configuration

Edit the following variables in `bot.py`:

```python
API_ID=
API_HASH=
BOT_TOKEN=
MONGO_URI=
SOURCE_CHANNELS=
TARGET_CHANNEL=


---

🏁 Deployment

🐍 Install Dependencies

pip install -r requirements.txt

▶️ Run Bot

python3 bot.py

🐳 Docker (Optional)

docker build -t tg-forward-bot .
docker run -e API_ID=... -e API_HASH=... -e BOT_TOKEN=... -e MONGO_URI=... tg-forward-bot


---

📦 Requirements

Python 3.9+

MongoDB (local or cloud like MongoDB Atlas)


requirements.txt:

pyrofork
tgcrypto
uvloop
Flask==1.1.2
gunicorn==20.1.0
Jinja2==3.0.3
werkzeug==2.0.2
itsdangerous==2.0.1
pymongo


---

🧪 Sample Log Output

✅ Forwarded message 456 from -1001234567890 to -1001122334455
⏳ FloodWait: Waiting 27s for message 457 from -1001234567890
❌ Error forwarding message 458 from -1001234567890: MessageIdInvalid


---

❤️ Credits

Pyrogram

MongoDB

You, the deployer!



---

🔐 License

MIT License

---

Let me know if you'd like this tailored for **Koyeb**, **Heroku**, or **Docker Compose** deployment.

