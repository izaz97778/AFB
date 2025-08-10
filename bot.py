import uvloop
import asyncio
from pyrogram import Client, filters
import re
from os import environ
print("Starting...")
# Install uvloop for faster event loops
uvloop.install()

id_pattern = re.compile(r'^.\d+$')

# Read configurations from environment variables
SESSION = environ.get("SESSION", "")  # Session string
API_ID = int(environ.get("API_ID", ""))  # API ID
API_HASH = environ.get("API_HASH")  # API Hash
TARGET_CHANNEL = int(environ.get("TARGET_CHANNEL", ""))  # Source channel username or ID

# For Multiple Id Use One Space Between Each id
SOURCE_CHANNELS = [int(ch) if id_pattern.search(ch) else ch for ch in environ.get('SOURCE_CHANNELS', '').split()]  # For Multiple Id Use One Space Between Each id.

# Create Pyrogram Client using StringSession
app = Client(name=SESSION, session_string=SESSION, api_id=API_ID, api_hash=API_HASH)
async def start_bot():
    await app.start()
    user = await app.get_me()
    print(f"Logged in as : {user.first_name}")

    await asyncio.Event().wait()

# Function to forward messages from the source channel to the bot
@app.on_message(filters.channel)
async def forward_messages(client, message):
    if message.chat.id in SOURCE_CHANNELS:
        try:
            # Forward the message to the bot
            await message.copy(TARGET_CHANNEL)
        except Exception as e:
            print(f"Failed to forward message {message.id}: {e}")

# Run the client
app.run(start_bot())
