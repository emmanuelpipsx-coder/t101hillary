# Auto-Approve Telegram Join Bot — Setup Guide

This bot does three things automatically, with zero manual work once it's running:
1. Approves everyone who requests to join your channel
2. DMs them a welcome message the instant they're approved
3. Logs which ad/campaign each join came from

Follow these steps in order. None of it requires coding.

---

## Step 1 — Create your bot and get a token

1. Open Telegram, search for **@BotFather**, start a chat.
2. Send `/newbot`, follow the prompts (pick a name, then a username ending in `bot`).
3. BotFather gives you a **token** — a long string like `123456789:ABCdefGhIJKlmNoPQRstuVwxyz`.
   Save it somewhere safe. Anyone with this token can control your bot.

## Step 2 — Add your bot as a channel admin

1. Go to your channel → **Manage Channel** → **Administrators** → **Add Admin**.
2. Search for your bot's username, add it.
3. Make sure it has permission to **"Invite Users via Link"**. (This same permission
   lets it approve join requests — no extra toggle needed.)

## Step 3 — Get your Channel ID

1. Add **@userinfobot** or **@RawDataBot** to your channel temporarily (as admin, or just forward a channel post to it), or:
2. Easiest: send any message in your channel, forward it to **@JsonDumpBot** or similar — it'll show a `chat_id` like `-1001234567890`.
3. Save that number — it's your `CHANNEL_ID`.

## Step 4 — Deploy the bot to Railway (free hosting, no server setup)

1. Go to [railway.app](https://railway.app), sign up (GitHub login is easiest).
2. Create a **New Project** → **Deploy from GitHub repo**.
   - If you don't have GitHub: create a free account at github.com, make a new
     repository, and upload these 4 files: `bot.py`, `requirements.txt`, `Procfile`,
     and this `README.md`.
3. Once Railway is connected to your repo, go to your project → **Variables** tab.
4. Add these environment variables:
   - `BOT_TOKEN` → paste the token from Step 1
   - `WELCOME_MESSAGE` → (optional) customize the DM new members get
5. Railway will auto-detect `Procfile` and start running `python bot.py`. Check the
   **Deployments** tab — you should see `Bot starting - listening for join requests...`
   in the logs. That means it's live and running 24/7.

## Step 5 — Generate your ad's invite link

This is a separate one-time step, done from your own computer (not Railway):

1. Make sure you have Python installed on your computer.
2. Open a terminal, run:
   ```
   pip install aiogram
   ```
3. Set your token and channel ID as environment variables, then run the script:
   ```
   BOT_TOKEN=your_token_here CHANNEL_ID=your_channel_id_here python create_invite_links.py "Meta Ad - Aug Launch"
   ```
4. It prints a link like `https://t.me/+AbCdEfGhIjKlMnOp`.
5. **Use this link — not your regular channel link — as the button URL in your ad
   and on your landing page.**

You can repeat Step 5 anytime you want a new tagged link for a new campaign
(e.g. one for Meta, one for Instagram, one for TikTok) so you can see in your
bot's logs exactly which source is producing real joins.

---

## How to check it's working

- Click your own invite link from Step 5 → you should see "Request to join" → tap it.
- Within a second or two, you should be approved automatically and get a DM from your bot.
- In Railway's **Deployments → Logs** tab, you'll see a line like:
  `APPROVED user_id=123456 username=someuser campaign=Meta Ad - Aug Launch`

## Notes

- If a user has DM privacy set to "contacts only," the welcome message may fail to
  send — this only affects a small number of users and isn't something to fix on
  your end.
- This bot only needs to keep running in the background — you don't need to open
  or check anything unless you're changing the welcome message or checking logs.
- If you ever want the join events to also show up back in Meta (so your ad
  reporting reflects real joins, not just clicks), that's a further step using
  Meta's Conversions API — happy to help with that once this part is live.
