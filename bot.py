import uvloop
import asyncio
from pyrogram import Client, filters
from pyrogram.errors import FloodWait
from pymongo import MongoClient
import re
from os import environ

print("Starting...")
uvloop.install()

# Regex for checking numeric IDs (e.g. -100...)
id_pattern = re.compile(r'^.\d+$')

# Load from environment
SESSION = environ.get("SESSION", "")
API_ID = int(environ.get("API_ID", ""))
API_HASH = environ.get("API_HASH", "")
TARGET_CHANNEL = int(environ.get("TARGET_CHANNEL", ""))
SOURCE_CHANNELS = [int(ch) if id_pattern.search(ch) else ch for ch in environ.get("SOURCE_CHANNELS", "").split()]
MONGO_URI = environ.get("MONGO_URI", "mongodb://localhost:27017")

# Setup MongoDB
mongo = MongoClient(MONGO_URI)
db = mongo["forwarding_bot"]
state_collection = db["forward_state"]

# --- MongoDB Helpers ---
def get_last_forwarded(chat_id):
    doc = state_collection.find_one({"_id": str(chat_id)})
    return doc["last_message_id"] if doc else 0

def save_last_forwarded(chat_id, message_id):
    state_collection.update_one(
        {"_id": str(chat_id)},
        {"$set": {"last_message_id": message_id}},
        upsert=True
    )

# --- Pyrogram client setup ---
app = Client(
    name=SESSION,
    session_string=SESSION,
    api_id=API_ID,
    api_hash=API_HASH
)

# --- Sync missed messages on startup ---
async def sync_missed_messages():
    for channel in SOURCE_CHANNELS:
        chat_id = str(channel)
        last_id = get_last_forwarded(chat_id)
        print(f"🔁 Syncing missed messages from {chat_id} (last forwarded ID: {last_id})")

        try:
            async for message in app.get_chat_history(channel, offset_id=0):
                if message.id <= last_id:
                    break
                try:
                    await message.copy(TARGET_CHANNEL)
                    print(f"✅ Synced & forwarded message {message.id} from {chat_id}")
                    save_last_forwarded(chat_id, message.id)
                except FloodWait as e:
                    print(f"⏳ FloodWait while syncing: Waiting {e.value}s")
                    await asyncio.sleep(e.value)
                except Exception as e:
                    print(f"❌ Error syncing message {message.id} from {chat_id}: {e}")
        except Exception as e:
            print(f"❌ Error accessing chat history for {chat_id}: {e}")

# --- Real-time forward handler ---
@app.on_message(filters.channel)
async def forward_messages(client, message):
    if message.chat.id in SOURCE_CHANNELS:
        chat_id = str(message.chat.id)
        last_id = get_last_forwarded(chat_id)

        if message.id <= last_id:
            return  # Already forwarded

        while True:
            try:
                await message.copy(TARGET_CHANNEL)
                print(f"✅ Forwarded message {message.id} from {chat_id} to {TARGET_CHANNEL}")
                save_last_forwarded(chat_id, message.id)
                break
            except FloodWait as e:
                print(f"⏳ FloodWait: Waiting {e.value}s for message {message.id} from {chat_id}")
                await asyncio.sleep(e.value)
            except Exception as e:
                print(f"❌ Error forwarding message {message.id} from {chat_id}: {e}")
                break

# --- Start the bot ---
async def start_bot():
    await app.start()
    user = await app.get_me()
    print(f"✅ Logged in as: {user.first_name} (@{user.username}) [{user.id}]")

    await sync_missed_messages()  # 🔁 Sync old messages

    await asyncio.Event().wait()

# --- Run the app ---
app.run(start_bot())
