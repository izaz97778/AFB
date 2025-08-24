import uvloop
import asyncio
from pyrogram import Client, filters
from pyrogram.errors import FloodWait, ChannelInvalid
from pymongo import MongoClient
import re
from os import environ

print("Starting...")
uvloop.install()

id_pattern = re.compile(r'^-?\d+$')

# Load from environment
SESSION = environ.get("SESSION", "")
API_ID = int(environ.get("API_ID", ""))
API_HASH = environ.get("API_HASH", "")
TARGET_CHANNEL = int(environ.get("TARGET_CHANNEL", ""))
SOURCE_CHANNELS = [int(ch) if id_pattern.match(ch) else ch for ch in environ.get("SOURCE_CHANNELS", "").split()]
MONGO_URI = environ.get("MONGO_URI", "mongodb://localhost:27017")

# MongoDB setup
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
    name=SESSION,
    session_string=SESSION,
    api_id=API_ID,
    api_hash=API_HASH
)

async def resume_forwarding():
    for source in SOURCE_CHANNELS:
        try:
            last_id = get_last_forwarded(source)
            print(f"Resuming from {last_id} in {source}")

            async for message in app.get_chat_history(source, offset_id=last_id, reverse=True):
                if message.id <= last_id:
                    continue

                while True:
                    try:
                        await message.copy(TARGET_CHANNEL)
                        print(f"✅ Resumed and forwarded message {message.id} from {source}")
                        save_last_forwarded(source, message.id)
                        break
                    except FloodWait as e:
                        print(f"⏳ FloodWait: Sleeping for {e.value}s")
                        await asyncio.sleep(e.value)
                    except Exception as e:
                        print(f"❌ Error forwarding message {message.id} from {source}: {e}")
                        break

        except ChannelInvalid:
            print(f"❌ Invalid channel: {source}")
        except Exception as e:
            print(f"❌ Error with channel {source}: {e}")

@app.on_message(filters.channel)
async def forward_new_messages(client, message):
    if message.chat.id in SOURCE_CHANNELS:
        last_id = get_last_forwarded(message.chat.id)

        if message.id <= last_id:
            return

        while True:
            try:
                await message.copy(TARGET_CHANNEL)
                print(f"✅ Forwarded new message {message.id} from {message.chat.id}")
                save_last_forwarded(message.chat.id, message.id)
                break
            except FloodWait as e:
                print(f"⏳ FloodWait for new message: Sleeping {e.value}s")
                await asyncio.sleep(e.value)
            except Exception as e:
                print(f"❌ Error forwarding new message {message.id}: {e}")
                break

async def start_bot():
    await app.start()
    user = await app.get_me()
    print(f"✅ Logged in as: {user.first_name} (@{user.username})")

    await resume_forwarding()
    print("✅ Resume complete. Listening for new messages...")
    await asyncio.Event().wait()

app.run(start_bot())
