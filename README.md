# 𝐂𝐨𝐧𝐯𝐞𝐧𝐢𝐞𝐧𝐭 𝐆𝐫𝐚𝐦

Telegram bot for business account management with message tracking, streaks, and automation.

## Features

- Track deleted and edited messages
- Daily conversation streaks
- Message flood utility
- User info lookup
- Multi-user support
- Configurable settings per user
- Cache management

## Setup

1. Clone repository
```bash
git clone https://github.com/quuxgit/convenient-gram.git
cd convenient-gram
```

2. Install dependencies:
```bash
pip install -r requirements.txt
```

3. Get bot token from [@BotFather](https://t.me/BotFather):
   - Send `/newbot` to BotFather
   - Follow instructions to create bot
   - Copy the token

4. Configure environment:
```bash
# Rename .env.example to .env
mv .env.example .env

# Edit .env and replace @BotFather with your actual token
```

5. Enable Business Mode:
   - Open [@BotFather](https://t.me/BotFather)
   - Send `/mybots` → select your bot → Bot Settings → Business Mode
   - Enable it

6. Run bot:
```bash
python bot.py
```

7. Connect bot via Telegram Business settings

## Commands

- `/start` - Initialize bot
- `/settings` - Configure features
- `/info` - Get user information
- `/streak` - Check conversation streak
- `/flood <text> <count>` - Send multiple messages
- `/cache` - View cache statistics
- `/clearcache` - Clear message cache

## License

GPL-3.0 License - see LICENSE file
