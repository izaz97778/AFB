import uvloop
import asyncio
import os
import re
from pyrogram import Client, filters
from pyrogram.errors import FloodWait, RPCError, ChatWriteForbidden, ChannelInvalid
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
    name="forwarder",
    session_string=SESSION,
    api_id=API_ID,
    api_hash=API_HASH
)

# --- Forwarding queue ---
forward_queue = asyncio.Queue()

# --- Counters ---
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

# --- Forwarding helper ---
async def forward_one(chat_id, message):
    if getattr(message, "service", False):
        counters["skipped"] += 1
        return
    if message.id <= get_last_forwarded(chat_id):
        counters["skipped"] += 1
        return

    while True:
        try:
            await message.copy(TARGET_CHANNEL)
            save_last_forwarded(chat_id, message.id)
            counters["forwarded"] += 1
            print(f"✅ Forwarded message {message.id} from {chat_id} to {TARGET_CHANNEL} "
                  f"| Forwarded: {counters['forwarded']} | Queued: {counters['queued']} | Skipped: {counters['skipped']}")
            break
        except FloodWait as e:
            print(f"⏳ FloodWait: Waiting {e.value}s for message {message.id} from {chat_id}")
            await asyncio.sleep(e.value)
        except ChatWriteForbidden:
            print(f"❌ Cannot write to target channel {TARGET_CHANNEL}. Make sure userbot is admin.")
            counters["skipped"] += 1
            break
        except Exception as e:
            print(f"❌ Error forwarding message {message.id} from {chat_id}: {e}")
            counters["skipped"] += 1
            break

# --- Catch-up routine ---
async def catch_up_channel(chat_id):
    last_id = get_last_forwarded(chat_id)

    # If new source channel → skip history
    if last_id == 0:
        try:
            async for m in app.get_chat_history(chat_id, limit=1):
                save_last_forwarded(chat_id, m.id)
                last_id = m.id
                print(f"🆕 Initialized {chat_id} at message_id {last_id} (skipping history)")
        except ChannelInvalid:
            print(f"⚠️ Channel {chat_id} invalid, skipping...")
            counters["skipped"] += 1
            return
        except Exception as e:
            print(f"⚠️ Could not initialize {chat_id}: {e}")
            counters["skipped"] += 1
            return

    print(f"📌 Catching up {chat_id} from message_id > {last_id} ...")
    try:
        async for msg in app.get_chat_history(chat_id, offset_id=last_id - 1, reverse=True, limit=1000):
            if getattr(msg, "service", False) or msg.id <= get_last_forwarded(chat_id):
                counters["skipped"] += 1
                continue
            await forward_queue.put((chat_id, msg))
            counters["queued"] += 1
            print(f"📥 Queued message {msg.id} from {chat_id} | Queued: {counters['queued']}")
    except ChannelInvalid:
        print(f"⚠️ Channel {chat_id} invalid during catch-up, skipping...")
        counters["skipped"] += 1
    except Exception as e:
        print(f"⚠️ Error in catch-up for {chat_id}: {e}")
        counters["skipped"] += 1

async def catch_up_all():
    tasks = [asyncio.create_task(catch_up_channel(cid)) for cid in SOURCE_CHANNELS]
    await asyncio.gather(*tasks)

# --- On new messages ---
@app.on_message(filters.chat(SOURCE_CHANNELS))
async def forward_messages(client, message):
    if message.id > get_last_forwarded(message.chat.id):
        await forward_queue.put((message.chat.id, message))
        counters["queued"] += 1
        print(f"📥 New message queued {message.id} from {message.chat.id} | Queued: {counters['queued']}")

# --- Main lifecycle ---
async def run_with_retries():
    retries = 0
    MAX_RETRIES = 5

    while True:
        try:
            await app.start()
            user = await app.get_me()
            print(f"✅ Logged in as: {user.first_name} (@{user.username}) [{user.id}]")

            # Debug target channel
            try:
                chat = await app.get_chat(TARGET_CHANNEL)
                print(f"✅ Target chat accessible: {chat.title}")
            except Exception as e:
                print(f"❌ Cannot access target chat: {e}")

            # Start forward worker
            asyncio.create_task(forward_worker())
            # Start catch-up
            await catch_up_all()

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
            if app.is_connected:
                try:
                    await app.stop()
                except Exception:
                    pass

        await asyncio.sleep(5)

if __name__ == "__main__":
    asyncio.run(run_with_retries())
