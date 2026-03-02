from fastapi import FastAPI
import os
from telethon import TelegramClient
from telethon.sessions import StringSession

app = FastAPI()

api_id = int(os.environ.get("API_ID"))
api_hash = os.environ.get("API_HASH")
string_session = os.environ.get("STRING_SESSION")

client = TelegramClient(StringSession(string_session), api_id, api_hash)


@app.on_event("startup")
async def startup():
    await client.connect()


@app.get("/")
async def root():
    return {"status": "tg-parser is running"}


@app.get("/health")
async def health():
    return {"health": "ok"}
