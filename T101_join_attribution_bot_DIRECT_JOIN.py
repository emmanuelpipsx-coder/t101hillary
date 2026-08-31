"""
T101 Telegram Join Attribution Bot

Flow:
Facebook ad -> landing page -> /track on Railway -> unique Telegram join-request
invite -> approval -> welcome -> Meta CAPI Lead.

IMPORTANT:
- Put secrets only in Railway Variables.
- Do not put META_CAPI_TOKEN or BOT_TOKEN in this file.
"""

import asyncio
import hashlib
import logging
import os
import sqlite3
import time
import uuid
from datetime import datetime, timezone

from aiohttp import web
import aiohttp
from aiogram import Bot, Dispatcher, F
from aiogram.types import (
    ChatJoinRequest,
    InlineKeyboardButton,
    InlineKeyboardMarkup,
    Message,
)

# -----------------------------
# Railway environment variables
# -----------------------------
BOT_TOKEN = os.environ["BOT_TOKEN"]
BOT_USERNAME = os.environ["BOT_USERNAME"].lstrip("@")
CHANNEL_ID = os.environ["CHANNEL_ID"]
WELCOME_MESSAGE = os.environ.get(
    "WELCOME_MESSAGE",
    "✅ You're in. Welcome to the group!",
)
OWNER_ID = os.environ.get("OWNER_ID")

META_PIXEL_ID = os.environ.get("META_PIXEL_ID")
META_CAPI_TOKEN = os.environ.get("META_CAPI_TOKEN")
META_TEST_EVENT_CODE = os.environ.get("META_TEST_EVENT_CODE")
META_API_VERSION = os.environ.get("META_API_VERSION", "v21.0")

# Railway provides PORT for the public HTTP service.
PORT = int(os.environ.get("PORT", "8080"))
DB_PATH = os.environ.get("DB_PATH", "attribution.sqlite3")

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s | %(levelname)s | %(message)s",
)
log = logging.getLogger("t101-join-bot")

bot = Bot(token=BOT_TOKEN)
dp = Dispatcher()


# -----------------------------
# SQLite attribution store
# -----------------------------
def db():
    conn = sqlite3.connect(DB_PATH)
    conn.row_factory = sqlite3.Row
    return conn


def init_db():
    conn = db()
    conn.execute(
        """
        CREATE TABLE IF NOT EXISTS clicks (
            token TEXT PRIMARY KEY,
            fbc TEXT,
            fbp TEXT,
            client_ip TEXT,
            user_agent TEXT,
            landing_url TEXT,
            created_at INTEGER,
            telegram_user_id INTEGER,
            started_at INTEGER,
            joined_at INTEGER,
            campaign TEXT,
            invite_link TEXT
        )
        """
    )
    try:
        conn.execute("ALTER TABLE clicks ADD COLUMN invite_link TEXT")
    except sqlite3.OperationalError:
        pass
    conn.commit()
    conn.close()


def create_tracking_token(data: dict) -> str:
    token = uuid.uuid4().hex[:16]
    conn = db()
    conn.execute(
        """
        INSERT INTO clicks
        (token, fbc, fbp, client_ip, user_agent, landing_url, created_at)
        VALUES (?, ?, ?, ?, ?, ?, ?)
        """,
        (
            token,
            data.get("fbc"),
            data.get("fbp"),
            data.get("client_ip"),
            data.get("user_agent"),
            data.get("landing_url"),
            int(time.time()),
        ),
    )
    conn.commit()
    conn.close()
    return token


def attach_telegram_user(token: str, telegram_user_id: int):
    conn = db()
    conn.execute(
        """
        UPDATE clicks
        SET telegram_user_id = ?, started_at = ?
        WHERE token = ?
        """,
        (telegram_user_id, int(time.time()), token),
    )
    conn.commit()
    conn.close()


def get_attribution_for_user(telegram_user_id: int):
    conn = db()
    row = conn.execute(
        """
        SELECT *
        FROM clicks
        WHERE telegram_user_id = ?
        ORDER BY started_at DESC
        LIMIT 1
        """,
        (telegram_user_id,),
    ).fetchone()
    conn.close()
    return row


def attach_invite_link(token: str, invite_link: str):
    conn = db()
    conn.execute(
        "UPDATE clicks SET invite_link = ? WHERE token = ?",
        (invite_link, token),
    )
    conn.commit()
    conn.close()


def get_attribution_for_invite(invite_link: str):
    conn = db()
    row = conn.execute(
        "SELECT * FROM clicks WHERE invite_link = ? ORDER BY created_at DESC LIMIT 1",
        (invite_link,),
    ).fetchone()
    conn.close()
    return row


def mark_joined(telegram_user_id: int, campaign: str):
    conn = db()
    conn.execute(
        """
        UPDATE clicks
        SET joined_at = ?, campaign = ?
        WHERE telegram_user_id = ?
        """,
        (int(time.time()), campaign, telegram_user_id),
    )
    conn.commit()
    conn.close()


# -----------------------------
# Helpers
# -----------------------------
def hash_sha256(value: str) -> str:
    return hashlib.sha256(value.strip().lower().encode("utf-8")).hexdigest()


async def notify_owner(user_id: int, username: str, campaign: str):
    if not OWNER_ID:
        return

    text = (
        "✅ New REAL join\n"
        f"User: @{username or user_id}\n"
        f"Campaign: {campaign}"
    )
    try:
        await bot.send_message(chat_id=int(OWNER_ID), text=text)
    except Exception as e:
        log.warning("Owner notification failed: %s", e)


async def send_lead_to_meta(
    user_id: int,
    username: str,
    campaign: str,
    attribution,
):
    if not META_PIXEL_ID or not META_CAPI_TOKEN:
        log.warning("Meta CAPI skipped: missing META_PIXEL_ID or META_CAPI_TOKEN")
        return

    user_data = {
        "external_id": [hash_sha256(str(user_id))],
    }

    # These are intentionally NOT hashed.
    if attribution:
        if attribution["fbc"]:
            user_data["fbc"] = attribution["fbc"]
        if attribution["fbp"]:
            user_data["fbp"] = attribution["fbp"]
        if attribution["client_ip"]:
            user_data["client_ip_address"] = attribution["client_ip"]
        if attribution["user_agent"]:
            user_data["client_user_agent"] = attribution["user_agent"]

    event = {
        "event_name": "Lead",
        "event_time": int(time.time()),
        "action_source": "website",
        "event_id": f"telegram_join_{user_id}_{uuid.uuid4().hex}",
        "user_data": user_data,
        "custom_data": {
            "content_name": "Telegram Channel Join",
            "content_category": campaign,
            "value": 0.00,
            "currency": "USD",
        },
    }

    if attribution and attribution["landing_url"]:
        event["event_source_url"] = attribution["landing_url"]

    payload = {
        "data": [event],
        "access_token": META_CAPI_TOKEN,
    }

    if META_TEST_EVENT_CODE:
        payload["test_event_code"] = META_TEST_EVENT_CODE

    debug_payload = {**payload, "access_token": "***MASKED***"}
    log.info("META SEND: %s", debug_payload)

    url = f"https://graph.facebook.com/{META_API_VERSION}/{META_PIXEL_ID}/events"

    try:
        async with aiohttp.ClientSession() as session:
            async with session.post(
                url,
                json=payload,
                timeout=aiohttp.ClientTimeout(total=10),
            ) as resp:
                body = await resp.text()
                log.info(
                    "META RESPONSE status=%s user=%s campaign=%s body=%s",
                    resp.status,
                    user_id,
                    campaign,
                    body,
                )
    except Exception as e:
        log.exception("Meta CAPI request failed: %s", e)


# -----------------------------
# HTTP endpoint used by landing page
# -----------------------------
async def track(request: web.Request):
    if request.method == "OPTIONS":
        return web.Response(
            status=204,
            headers={
                "Access-Control-Allow-Origin": "*",
                "Access-Control-Allow-Headers": "Content-Type",
                "Access-Control-Allow-Methods": "POST, OPTIONS",
            },
        )

    try:
        data = await request.json()
    except Exception:
        return web.json_response({"ok": False, "error": "invalid_json"}, status=400)

    # Basic validation. Do not store arbitrary headers/fields.
    clean = {
        "fbc": str(data.get("fbc") or "")[:500],
        "fbp": str(data.get("fbp") or "")[:500],
        "client_ip": request.headers.get("X-Forwarded-For", request.remote or "")[:100],
        "user_agent": request.headers.get("User-Agent", "")[:1000],
        "landing_url": str(data.get("landing_url") or "")[:2000],
    }

    token = create_tracking_token(clean)

    # Create a unique join-request invite for THIS visitor.
    # The invite link is stored against the attribution token so the
    # Telegram join request can be mapped back to the Facebook click.
    try:
        invite = await bot.create_chat_invite_link(
            chat_id=CHANNEL_ID,
            name=f"fb-{token}",
            creates_join_request=True,
        )
        invite_url = invite.invite_link
        attach_invite_link(token, invite_url)
    except Exception as e:
        log.exception("Failed to create Telegram invite for token=%s: %s", token, e)
        return web.json_response(
            {"ok": False, "error": "telegram_invite_creation_failed"},
            status=500,
            headers={"Access-Control-Allow-Origin": "*"},
        )

    log.info(
        "TRACK token=%s fbc=%s fbp=%s invite=%s ip=%s",
        token,
        bool(clean["fbc"]),
        bool(clean["fbp"]),
        invite_url,
        clean["client_ip"],
    )

    return web.json_response(
        {
            "ok": True,
            "token": token,
            "telegram_url": invite_url,
        },
        headers={"Access-Control-Allow-Origin": "*"},
    )


async def health(request: web.Request):
    return web.json_response({"ok": True, "service": "t101-telegram-attribution"})


async def options_track(request: web.Request):
    return web.Response(
        status=204,
        headers={
            "Access-Control-Allow-Origin": "*",
            "Access-Control-Allow-Headers": "Content-Type",
            "Access-Control-Allow-Methods": "POST, OPTIONS",
        },
    )


async def start_web_server():
    app = web.Application()
    app.router.add_get("/health", health)
    app.router.add_post("/track", track)
    app.router.add_options("/track", options_track)

    runner = web.AppRunner(app)
    await runner.setup()
    site = web.TCPSite(runner, "0.0.0.0", PORT)
    await site.start()
    log.info("HTTP attribution server listening on port %s", PORT)
    return runner


# -----------------------------
# Telegram handlers
# -----------------------------
@dp.message(F.text.startswith("/start"))
async def handle_start(message: Message):
    # Legacy support only. The new funnel no longer requires START.
    log.info("START received user_id=%s (legacy flow)", message.from_user.id)
    await message.answer("Please use the JOIN NOW button from the landing page to enter the channel.")


@dp.chat_join_request()
async def handle_join_request(request: ChatJoinRequest):
    user = request.from_user
    invite = request.invite_link
    invite_url = invite.invite_link if invite else ""
    campaign = invite.name if invite and invite.name else "unlabeled"

    # Match the exact invite used to the Facebook attribution captured at /track.
    attribution = get_attribution_for_invite(invite_url) if invite_url else None

    if attribution:
        log.info(
            "JOIN ATTRIBUTED user_id=%s token=%s campaign=%s fbc=%s fbp=%s",
            user.id,
            attribution["token"],
            campaign,
            bool(attribution["fbc"]),
            bool(attribution["fbp"]),
        )
    else:
        log.warning(
            "JOIN WITHOUT ATTRIBUTION user_id=%s invite=%s campaign=%s",
            user.id,
            invite_url,
            campaign,
        )

    # Approve the real Telegram join.
    try:
        await bot.approve_chat_join_request(
            chat_id=request.chat.id,
            user_id=user.id,
        )
        log.info(
            "APPROVED user_id=%s username=%s campaign=%s time=%s",
            user.id,
            user.username,
            campaign,
            datetime.now(timezone.utc).isoformat(),
        )
    except Exception as e:
        log.error("Failed to approve user_id=%s: %s", user.id, e)
        return

    if attribution:
        mark_joined(user.id, campaign)

    # A bot cannot normally start a new private chat with a user who never
    # pressed START. Try the DM, but don't treat failure as a conversion failure.
    try:
        await bot.send_message(
            chat_id=user.id,
            text=WELCOME_MESSAGE,
        )
    except Exception as e:
        log.warning(
            "Welcome DM unavailable user_id=%s (user may not have started bot): %s",
            user.id,
            e,
        )

    await notify_owner(user.id, user.username, campaign)

    # The REAL conversion: only after the actual join was approved.
    await send_lead_to_meta(
        user.id,
        user.username,
        campaign,
        attribution,
    )


async def main():
    init_db()
    runner = await start_web_server()

    log.info("Bot starting - listening for /start and join requests...")
    try:
        await dp.start_polling(
            bot,
            allowed_updates=["message", "chat_join_request"],
        )
    finally:
        await runner.cleanup()
        await bot.session.close()


if __name__ == "__main__":
    asyncio.run(main())
