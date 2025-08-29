import uvloop
import asyncio
import os
import re
from pyrogram import Client, filters
from pyrogram.errors import FloodWait, RPCError, ChatWriteForbidden, ChannelInvalid
from pymongo import MongoClient

print("Starting...")
uvloop.install()

id_pattern = re.compile(r"^-?\d+$")

SESSION = os.environ.get("SESSION", "")
API_ID = int(os.environ.get("API_ID", "0"))
API_HASH = os.environ.get("API_HASH", "")
TARGET_CHANNEL = int(os.environ.get("TARGET_CHANNEL", "0"))
SOURCE_CHANNELS = [
    int(ch) if id_pattern.search(ch) else ch
    for ch in os.environ.get("SOURCE_CHANNELS", "").split()
]
MONGO_URI = os.environ.get("MONGO_URI", "mongodb://localhost:27017")

mongo = MongoClient(MONGO_URI)
db = mongo["forwarding_bot"]
state_collection = db["forward_state"]

def get_last_forwarded(chat_id):
    doc = state_collection.find_one({"_id": str(chat_id)})
    return doc["last_message_id"] if doc else 0

def save_last_forwarded(chat_id, message_id):
    state_collection.update_one(
        {"_id": str(chat_id)},
        {"$set": {"last_message_id": message_id}},
        upsert=True
    )

app = Client(
    name="forwarder",
    session_string=SESSION,
    api_id=API_ID,
    api_hash=API_HASH
)

forward_queue = asyncio.Queue()

counters = {
    "queued": 0,
    "forwarded": 0,
    "skipped": 0
}

# --- Forwarding worker ---
async def forward_worker():
    while True:
        chat_id, msg = await forward_queue.get()
        await forward_one(chat_id, msg)
        forward_queue.task_done()

async def forward_one(chat_id, message):
    if getattr(message, "service", False) or message.id <= get_last_forwarded(chat_id):
        counters["skipped"] += 1
        return

    while True:
        try:
            await message.copy(TARGET_CHANNEL)
            save_last_forwarded(chat_id, message.id)
            counters["forwarded"] += 1
            print(f"✅ Forwarded message {message.id} from {chat_id} "
                  f"| Forwarded: {counters['forwarded']} | Queued: {counters['queued']} | Skipped: {counters['skipped']}")
            break
        except FloodWait as e:
            print(f"⏳ FloodWait: Waiting {e.value}s for message {message.id}")
            await asyncio.sleep(e.value)
        except ChatWriteForbidden:
            print(f"❌ Cannot write to target channel {TARGET_CHANNEL}. Make sure userbot is admin.")
            counters["skipped"] += 1
            break
        except RPCError as e:
            print(f"⚠️ RPCError: {e}, pausing 30s")
            await asyncio.sleep(30)
        except Exception as e:
            print(f"❌ Error forwarding message {message.id}: {e}")
            counters["skipped"] += 1
            break

# --- Only forward new messages from last saved message ---
@app.on_message(filters.chat(SOURCE_CHANNELS))
async def forward_messages(client, message):
    if message.id > get_last_forwarded(message.chat.id):
        await forward_queue.put((message.chat.id, message))
        counters["queued"] += 1
        print(f"📥 New message queued {message.id} from {message.chat.id} | Queued: {counters['queued']}")

async def run_bot():
    await app.start()
    user = await app.get_me()
    print(f"✅ Logged in as: {user.first_name} (@{user.username}) [{user.id}]")

    try:
        chat = await app.get_chat(TARGET_CHANNEL)
        print(f"✅ Target chat accessible: {chat.title}")
    except Exception as e:
        print(f"❌ Cannot access target chat: {e}")

    # Start the forward worker
    asyncio.create_task(forward_worker())

    # Keep running
    await asyncio.Event().wait()

if __name__ == "__main__":
    asyncio.run(run_bot())
