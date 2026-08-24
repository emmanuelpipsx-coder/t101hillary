"""
Telegram auto-approve join bot
--------------------------------
What this does:
  1. Listens for people requesting to join your channel (via a
     "request to join" invite link you create with create_invite_links.py).
  2. Automatically approves every request instantly.
  3. Immediately sends the new member a welcome DM.
  4. Logs which invite link (campaign) each join came from, so you know
     which ad actually produced a real member - not just a click.
  5. Reports the REAL join back to Meta as a server-side "Lead" event via
     the Conversions API - so your ad account reflects actual joins,
     not just button clicks.

You do not need to touch this file to use it day-to-day. Everything
you configure lives in environment variables (set in Railway, see README).
"""

import asyncio
import hashlib
import logging
import os
import time
from datetime import datetime

import aiohttp
from aiogram import Bot, Dispatcher
from aiogram.types import ChatJoinRequest

# ---------------------------------------------------------------------------
# Configuration - all pulled from environment variables (set these in Railway)
# ---------------------------------------------------------------------------
BOT_TOKEN = os.environ["BOT_TOKEN"]              # from BotFather
WELCOME_MESSAGE = os.environ.get(
    "WELCOME_MESSAGE",
    "Welcome! 🎉 You're in. I'll be sending you setups and updates here directly.",
)

# Meta Conversions API - optional. If these aren't set, the bot still works,
# it just skips reporting joins back to Meta.
META_PIXEL_ID = os.environ.get("META_PIXEL_ID")            # e.g. 2217682802419563
META_CAPI_TOKEN = os.environ.get("META_CAPI_TOKEN")        # from Events Manager > Conversions API
META_TEST_EVENT_CODE = os.environ.get("META_TEST_EVENT_CODE")  # optional, only while testing
META_API_VERSION = "v21.0"

logging.basicConfig(level=logging.INFO, format="%(asctime)s | %(levelname)s | %(message)s")
log = logging.getLogger("join-bot")

bot = Bot(token=BOT_TOKEN)
dp = Dispatcher()


def hash_sha256(value: str) -> str:
    """Meta requires identifiers to be lowercased and SHA-256 hashed."""
    return hashlib.sha256(value.strip().lower().encode("utf-8")).hexdigest()


async def send_lead_to_meta(user_id: int, username: str, campaign: str):
    """
    Sends a real, server-side 'Lead' event to Meta's Conversions API the
    moment someone is actually approved into the channel.

    Match quality note: because Telegram is off-platform, we don't have
    the ad click ID (fbc) or browser cookie (fbp) here, so Meta can't tie
    this back to the exact ad click with full confidence. We still send a
    hashed external_id (the Telegram user ID) so repeat events for the
    same person can be recognized as the same person over time, which
    Meta uses as one of several matching signals.
    """
    if not META_PIXEL_ID or not META_CAPI_TOKEN:
        log.info("Skipping Meta CAPI report (META_PIXEL_ID/META_CAPI_TOKEN not set)")
        return

    url = f"https://graph.facebook.com/{META_API_VERSION}/{META_PIXEL_ID}/events"

    event = {
        "event_name": "Lead",
        "event_time": int(time.time()),
        "action_source": "system_generated",
        "event_id": f"telegram_join_{user_id}_{int(time.time())}",
        "user_data": {
            "external_id": [hash_sha256(str(user_id))],
        },
        "custom_data": {
            "content_name": "Telegram Channel Join",
            "content_category": campaign,
            "value": 0.00,
            "currency": "USD",
        },
    }

    payload = {
        "data": [event],
        "access_token": META_CAPI_TOKEN,
    }
    if META_TEST_EVENT_CODE:
        payload["test_event_code"] = META_TEST_EVENT_CODE

    try:
        async with aiohttp.ClientSession() as session:
            async with session.post(url, json=payload, timeout=aiohttp.ClientTimeout(total=10)) as resp:
                body = await resp.text()
                if resp.status == 200:
                    log.info("Meta CAPI Lead reported for user_id=%s campaign=%s", user_id, campaign)
                else:
                    log.warning("Meta CAPI error (status=%s): %s", resp.status, body)
    except Exception as e:
        log.warning("Meta CAPI request failed for user_id=%s: %s", user_id, e)


@dp.chat_join_request()
async def handle_join_request(request: ChatJoinRequest):
    user = request.from_user
    invite_link = request.invite_link
    campaign = invite_link.name if invite_link and invite_link.name else "unlabeled"

    try:
        # Step 1: approve them instantly
        await bot.approve_chat_join_request(
            chat_id=request.chat.id,
            user_id=user.id,
        )
        log.info(
            "APPROVED user_id=%s username=%s campaign=%s time=%s",
            user.id, user.username, campaign, datetime.utcnow().isoformat(),
        )
    except Exception as e:
        log.error("Failed to approve user_id=%s: %s", user.id, e)
        return

    try:
        # Step 2: DM them immediately - this works because the join
        # request itself counts as the user initiating contact with the bot.
        await bot.send_message(chat_id=user.id, text=WELCOME_MESSAGE)
    except Exception as e:
        # This can fail if the user has DMs restricted to contacts only -
        # that's normal for a small percentage of users, not a bug.
        log.warning("Could not DM user_id=%s: %s", user.id, e)

    # Step 3: report the real join back to Meta as a Lead event.
    await send_lead_to_meta(user.id, user.username, campaign)


async def main():
    log.info("Bot starting - listening for join requests...")
    await dp.start_polling(bot, allowed_updates=["chat_join_request"])


if __name__ == "__main__":
    asyncio.run(main())
