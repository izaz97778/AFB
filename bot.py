import uvloop
import asyncio
from pyrogram import Client, filters
from pyrogram.types import InlineKeyboardMarkup, InlineKeyboardButton
from pyrogram.errors import FloodWait
from pymongo import MongoClient
import re
from os import environ

uvloop.install()
print("Starting...")

# Regex for numeric IDs
id_pattern = re.compile(r'^-?\d+$')

# --- Environment variables ---
SESSION = environ.get("SESSION", "")
API_ID = int(environ.get("API_ID", ""))
API_HASH = environ.get("API_HASH", "")
BOT_TOKEN = environ.get("BOT_TOKEN", "")
MONGO_URI = environ.get("MONGO_URI", "mongodb://localhost:27017")

# --- MongoDB setup ---
mongo = MongoClient(MONGO_URI)
db = mongo["forwarding_bot"]
state_collection = db["forward_state"]
config_collection = db["config"]

# --- First-time setup ---
if not config_collection.find_one({"_id": "main"}):
    # ⚠️ Replace with your real IDs
    initial_target = -1001234567890
    initial_sources = [-1001111111111, -1002222222222]
    config_collection.insert_one({
        "_id": "main",
        "target_channel": initial_target,
        "source_channels": initial_sources
    })
    print(f"✅ First-time config saved.\nTarget: {initial_target}\nSources: {initial_sources}")

# --- Load configuration ---
def load_config():
    cfg = config_collection.find_one({"_id": "main"})
    if not cfg:
        cfg = {"_id": "main", "target_channel": 0, "source_channels": []}
        config_collection.insert_one(cfg)
    return cfg

config = load_config()
TARGET_CHANNEL = config["target_channel"]
SOURCE_CHANNELS = config["source_channels"]

print(f"✅ Loaded config.\nTarget: {TARGET_CHANNEL}\nSources: {SOURCE_CHANNELS}")

# --- MongoDB helpers ---
def get_last_forwarded(chat_id):
    doc = state_collection.find_one({"_id": str(chat_id)})
    return doc["last_message_id"] if doc else 0

def save_last_forwarded(chat_id, message_id):
    state_collection.update_one(
        {"_id": str(chat_id)},
        {"$set": {"last_message_id": message_id}},
        upsert=True
    )

def save_config():
    config_collection.update_one({"_id": "main"}, {"$set": config}, upsert=True)

# --- Pyrogram clients ---
userbot = Client(
    name=SESSION,
    session_string=SESSION,
    api_id=API_ID,
    api_hash=API_HASH
)

bot = Client(
    name="bot",
    bot_token=BOT_TOKEN,
    api_id=API_ID,
    api_hash=API_HASH
)

# --- Forwarding handler ---
@userbot.on_message(filters.channel)
async def forward_messages(client, message):
    if message.chat.id in SOURCE_CHANNELS:
        chat_id = str(message.chat.id)
        last_id = get_last_forwarded(chat_id)
        if message.id <= last_id:
            return

        while True:
            try:
                await message.copy(TARGET_CHANNEL)
                print(f"✅ Forwarded message {message.id} from {chat_id} to {TARGET_CHANNEL}")
                save_last_forwarded(chat_id, message.id)
                break
            except FloodWait as e:
                print(f"⚠️ FloodWait: Waiting {e.value}s for message {message.id}")
                await asyncio.sleep(e.value)
            except Exception as e:
                print(f"❌ Error forwarding message {message.id}: {e}")
                break

# --- Bot commands with button interface ---
@bot.on_message(filters.private & filters.command("start"))
async def start_cmd(c, m):
    keyboard = InlineKeyboardMarkup(
        [
            [InlineKeyboardButton("Add Source", callback_data="add_source"),
             InlineKeyboardButton("Remove Source", callback_data="remove_source")],
            [InlineKeyboardButton("Set Target", callback_data="set_target")],
            [InlineKeyboardButton("Show Config", callback_data="show_config")]
        ]
    )
    await m.reply("Manage your forwarding bot:", reply_markup=keyboard)

@bot.on_callback_query()
async def handle_buttons(c, query):
    data = query.data

    if data == "show_config":
        await query.message.edit_text(f"📝 Current config:\nTarget: {TARGET_CHANNEL}\nSources: {SOURCE_CHANNELS}")

    elif data == "add_source":
        await query.message.edit_text("Send the channel ID or username to add as source:")

        @bot.on_message(filters.private & filters.incoming)
        async def receive_add(m_c, m):
            ch = m.text
            if id_pattern.search(ch):
                ch = int(ch)
            if ch not in SOURCE_CHANNELS:
                SOURCE_CHANNELS.append(ch)
                config["source_channels"] = SOURCE_CHANNELS
                save_config()
                await m.reply(f"✅ Added source channel: {ch}")
            else:
                await m.reply("⚠️ Channel already exists.")
            bot.remove_handler(receive_add)

    elif data == "remove_source":
        await query.message.edit_text("Send the channel ID or username to remove from sources:")

        @bot.on_message(filters.private & filters.incoming)
        async def receive_remove(m_c, m):
            ch = m.text
            if id_pattern.search(ch):
                ch = int(ch)
            if ch in SOURCE_CHANNELS:
                SOURCE_CHANNELS.remove(ch)
                config["source_channels"] = SOURCE_CHANNELS
                save_config()
                await m.reply(f"❌ Removed source channel: {ch}")
            else:
                await m.reply("⚠️ Channel not found.")
            bot.remove_handler(receive_remove)

    elif data == "set_target":
        await query.message.edit_text("Send the channel ID or username to set as target:")

        @bot.on_message(filters.private & filters.incoming)
        async def receive_target(m_c, m):
            ch = m.text
            if id_pattern.search(ch):
                ch = int(ch)
            global TARGET_CHANNEL
            TARGET_CHANNEL = ch
            config["target_channel"] = TARGET_CHANNEL
            save_config()
            await m.reply(f"🎯 Target channel set to: {TARGET_CHANNEL}")
            bot.remove_handler(receive_target)

# --- Run both clients ---
async def main():
    await userbot.start()
    print("✅ Userbot started")
    await bot.start()
    print("✅ Bot started")
    await asyncio.Event().wait()

asyncio.run(main())
