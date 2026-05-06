# Waifu Name Bot V2

Production-ready Telegram Waifu name lookup bot for **Waifu Database V2**.

## Features

- Fast in-memory snapshot lookup
- `file_unique_id` exact match first
- SHA-256 exact match
- Photo pHash approximate match
- Video frame pHash approximate match
- Result cache + miss cache
- Source-specific collection mapping
- No.14 `@CharacterLootBot` support: uses `items_character_seizer`, outputs `/loot`
- Group approve (`/gapprove`) system
- Group force join sends user to Bot DM only
- DM force join in Myanmar + English
- Manual lookup commands: `/waifu`, `/w`, `.wa`, `.w`, `/name`, `.name` plus optional `/loot` for Seizer/Loot collection
- Auto lookup in support group and approved groups
- Output includes Name, ID, Rarity; source hidden by default
- Capture, Seizer and Loot results hide ID/Rarity as requested
- Optional copy buttons

## Install on VPS

```bash
unzip waifu-name-bot-v2.zip
cd waifu-name-bot-v2
bash scripts/install_vps.sh
nano .env
python main.py
```

## Run with PM2

```bash
source .venv/bin/activate
pm2 start main.py --name waifu-name-bot-v2 --interpreter .venv/bin/python --time
pm2 save
pm2 logs waifu-name-bot-v2 --lines 50
```

## MongoDB expected fields

The bot reads these fields if present:

- `name` or `character_name`
- `card_id` or `id`
- `rarity`
- `media_type` or `type`
- `file_unique_id`, `photo_file_unique_id`, or `video_file_unique_id`
- `sha256`, `media_sha256`, or `hash`
- `phash` or `photo_phash`
- `frame_hashes` or `video_frame_hashes`

## Important env

```env
BOT_TOKEN=
MONGO_URI=
DB_NAME=waifu_adding_v2
OWNER_IDS=
BOT_USERNAME=
ENABLE_FORCE_JOIN=true
FORCE_JOIN_CHANNELS=@your_channel
ENABLE_GAPPROVE=true
AUTO_LOOKUP_ONLY_APPROVED_GROUPS=true
SHOW_SOURCE_IN_RESULT=false
ENABLE_COPY_BUTTONS=true
FORWARD_SOURCE_COMMANDS=@CaptureDatabase:/capture,@Seizer_Database:/seize,@CharacterLootBot:/loot,@hallowuploads:/hallow
```

## Admin commands

- `/gapprove` — approve current group for auto lookup
- `/gunapprove` — disable current group auto lookup
- `/refresh` — reload database snapshot into RAM
- `/status` or `/stats` — view speed/stat info
