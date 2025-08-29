import uvloop
import asyncio
import os
import re
from pyrogram import Client, filters
from pyrogram.errors import FloodWait, RPCError
from pymongo import MongoClient

print("Starting...")
uvloop.install()

# Regex for checking numeric IDs (e.g. -100...)
id_pattern = re.compile(r"^-?\d+$")

# Load from environment
SESSION = os.environ.get("SESSION", "")
API_ID = int(os.environ.get("API_ID", "0"))
API_HASH = os.environ.get("API_HASH", "")
TARGET_CHANNEL = int(os.environ.get("TARGET_CHANNEL", "0"))
SOURCE_CHANNELS = [
    int(ch) if id_pattern.search(ch) else ch
    for ch in os.environ.get("SOURCE_CHANNELS", "").split()
]
MONGO_URI = os.environ.get("MONGO_URI", "mongodb://localhost:27017")

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

# --- Forwarding helper ---
async def forward_one(chat_id, message):
    # Skip service/unsupported messages
    if getattr(message, "service", False):
        return

    # Dedup (double-check against Mongo in case of overlap)
    if message.id <= get_last_forwarded(chat_id):
        return

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

# --- Catch-up routine ---
async def catch_up():
    for src in SOURCE_CHANNELS:
        last_id = get_last_forwarded(src)
        print(f"📌 Catching up {src} from message_id > {last_id} ...")
        try:
            async for msg in app.get_chat_history(src, offset_id=last_id, reverse=True):
                # Skip service + ensure no duplicates even if restarted mid-batch
                if getattr(msg, "service", False) or msg.id <= get_last_forwarded(src):
                    continue
                await forward_one(src, msg)
        except Exception as e:
            print(f"⚠️ Error in catch-up for {src}: {e}")

# --- On new messages (only from configured sources) ---
@app.on_message(filters.chat(SOURCE_CHANNELS))
async def forward_messages(client, message):
    await forward_one(message.chat.id, message)

# --- Main lifecycle (manual control; no app.run here) ---
async def run_with_retries():
    retries = 0
    MAX_RETRIES = 5

    while True:
        try:
            await app.start()
            user = await app.get_me()
            print(f"✅ Logged in as: {user.first_name} (@{user.username}) [{user.id}]")

            # Catch up once at start
            await catch_up()

            # Keep alive
            await asyncio.Event().wait()

        except RPCError as e:
            if "PERSISTENT_TIMESTAMP_OUTDATED" in str(e):
                retries += 1
                print(f"⚠️ Persistent timestamp error, retry {retries}/{MAX_RETRIES}")
                if retries >= MAX_RETRIES:
                    print("🗑️ Resetting session...")
                    try:
                        os.remove(f"{SESSION}.session")
                    except FileNotFoundError:
                        pass
                    retries = 0
            else:
                print(f"⚠️ RPCError: {e}")
        except Exception as e:
            print(f"⚠️ Unexpected error: {e}")
        finally:
            try:
                await app.stop()
            except Exception:
                pass

        await asyncio.sleep(5)  # backoff before retry

if __name__ == "__main__":
    asyncio.run(run_with_retries())
