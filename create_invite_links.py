"""
Run this ONCE (locally, on your own computer) each time you want a new
tagged invite link for an ad or campaign - e.g. one link for your Meta
ad, a different one for Instagram bio, etc.

Usage:
    1. Set BOT_TOKEN and CHANNEL_ID below (or as environment variables).
    2. Run:  python create_invite_links.py "Meta Ad - Aug launch"
    3. It prints a link like https://t.me/+AbCdEfGhIjKlMnOp
    4. Put THAT link in your ad button (not your channel's public link).

Every join through this link forces a "request to join" step, even if
your channel is normally set to instant-join - so it works regardless
of your channel's general join settings.
"""

import asyncio
import os
import sys

from aiogram import Bot

BOT_TOKEN = os.environ.get("BOT_TOKEN", "PASTE_YOUR_BOT_TOKEN_HERE")
CHANNEL_ID = os.environ.get("CHANNEL_ID", "PASTE_YOUR_CHANNEL_ID_HERE")  # e.g. -1001234567890


async def main():
    if len(sys.argv) < 2:
        print('Usage: python create_invite_links.py "Campaign name"')
        return

    campaign_name = sys.argv[1]
    bot = Bot(token=BOT_TOKEN)

    link = await bot.create_chat_invite_link(
        chat_id=CHANNEL_ID,
        name=campaign_name,          # shows up in Telegram admin panel + our logs
        creates_join_request=True,   # forces the "request to join" flow
    )

    print("\nCreated invite link for:", campaign_name)
    print("Link:", link.invite_link)
    print("\nPut this exact link in your ad button.")

    await bot.session.close()


if __name__ == "__main__":
    asyncio.run(main())
