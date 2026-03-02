import os
import base64
from typing import List, Optional, Dict, Any

from fastapi import FastAPI, HTTPException
from pydantic import BaseModel

from telethon import TelegramClient
from telethon.sessions import StringSession
from telethon.tl.types import Message

app = FastAPI()

API_ID = os.environ.get("API_ID")
API_HASH = os.environ.get("API_HASH")
STRING_SESSION = os.environ.get("STRING_SESSION")

if not API_ID or not API_HASH or not STRING_SESSION:
    # Не падаем при импорте, чтобы Railway хоть /health поднял,
    # но дальше /me и /parse вернут ошибку.
    client = None
else:
    client = TelegramClient(StringSession(STRING_SESSION), int(API_ID), API_HASH)


class ParseRequest(BaseModel):
    channels: List[str]                 # ["@channel1", "@channel2"]
    limit: int = 10                     # сколько последних сообщений брать
    include_photos: bool = True         # включать фото
    max_photo_bytes: int = 2_000_000    # ограничение: 2MB на фото (для base64)


@app.get("/")
def root():
    return {"status": "tg-parser is running"}


@app.get("/health")
def health():
    return {"health": "ok"}


@app.on_event("startup")
async def startup():
    if client is None:
        return
    await client.connect()
    if not await client.is_user_authorized():
        # Если сессия битая — лучше явно это видеть
        raise RuntimeError("Telethon session is not authorized. Check STRING_SESSION.")


@app.on_event("shutdown")
async def shutdown():
    if client is None:
        return
    await client.disconnect()


@app.get("/me")
async def me():
    if client is None:
        raise HTTPException(status_code=500, detail="ENV vars missing: API_ID/API_HASH/STRING_SESSION")
    user = await client.get_me()
    return {
        "id": user.id,
        "username": user.username,
        "first_name": user.first_name,
        "phone": user.phone,
    }


def _tme_link(entity: str, msg_id: int) -> str:
    # entity может быть @name или ссылка; для ссылки аккуратно
    if entity.startswith("@"):
        return f"https://t.me/{entity[1:]}/{msg_id}"
    # если дали "https://t.me/name"
    if "t.me/" in entity:
        name = entity.split("t.me/")[-1].strip("/").split("/")[0]
        return f"https://t.me/{name}/{msg_id}"
    return ""


async def _message_to_item(channel_input: str, m: Message, include_photos: bool, max_photo_bytes: int) -> Dict[str, Any]:
    item: Dict[str, Any] = {
        "channel": channel_input,
        "message_id": m.id,
        "date": m.date.isoformat() if m.date else None,
        "text": (m.message or "").strip(),
        "link": _tme_link(channel_input, m.id),
        "has_photo": False,
    }

    if include_photos and m.photo:
        try:
            data = await client.download_media(m, file=bytes)  # bytes
            if data and isinstance(data, (bytes, bytearray)):
                if len(data) <= max_photo_bytes:
                    item["has_photo"] = True
                    item["photo_base64"] = base64.b64encode(data).decode("utf-8")
                    item["photo_mime"] = "image/jpeg"  # Telegram обычно отдаёт jpg
                    item["photo_filename"] = f"{m.id}.jpg"
                else:
                    # фото слишком большое — не шлём base64, чтобы не убить n8n
                    item["has_photo"] = True
                    item["photo_too_large"] = True
                    item["photo_size_bytes"] = len(data)
        except Exception as e:
            item["photo_error"] = str(e)

    return item


@app.post("/parse")
async def parse(req: ParseRequest):
    if client is None:
        raise HTTPException(status_code=500, detail="ENV vars missing: API_ID/API_HASH/STRING_SESSION")

    results: List[Dict[str, Any]] = []

    for ch in req.channels:
        try:
            entity = await client.get_entity(ch)
        except Exception as e:
            results.append({"channel": ch, "error": f"get_entity failed: {e}"})
            continue

        try:
            messages = await client.get_messages(entity, limit=req.limit)
            for m in messages:
                # пропускаем сервисные/пустые если надо — сейчас оставим всё
                item = await _message_to_item(ch, m, req.include_photos, req.max_photo_bytes)
                results.append(item)
        except Exception as e:
            results.append({"channel": ch, "error": f"get_messages failed: {e}"})

    return {"count": len(results), "items": results}
