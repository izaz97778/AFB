#!/bin/bash

# Start Flask app in background
gunicorn app:app --bind 0.0.0.0:$PORT &

# Start the Telegram bot (foreground keeps container alive)
python3 bot.py
