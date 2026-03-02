from fastapi import FastAPI
import os
from telethon import TelegramClient
from telethon.sessions import StringSession
import asyncio
app = FastAPI()

@app.get("/")
def root():
    return {"status": "tg-parser is running"}

@app.get("/health")
def health():
    return {"health": "ok"}

if __name__ == "__main__":
    import uvicorn
    port = int(os.environ.get("PORT", 8080))
    uvicorn.run(app, host="0.0.0.0", port=port)
