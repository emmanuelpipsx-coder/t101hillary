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

You do not need to touch this file to use it day-to-day. Everything
you configure lives in environment variables (set in Railway, see README).
"""

import asyncio
import logging
import os
from datetime import datetime

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

logging.basicConfig(level=logging.INFO, format="%(asctime)s | %(levelname)s | %(message)s")
log = logging.getLogger("join-bot")

bot = Bot(token=BOT_TOKEN)
dp = Dispatcher()


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


async def main():
    log.info("Bot starting - listening for join requests...")
    await dp.start_polling(bot, allowed_updates=["chat_join_request"])


if __name__ == "__main__":
    asyncio.run(main())
