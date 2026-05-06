#!/usr/bin/env bash
set -euo pipefail
source .venv/bin/activate
pm2 start main.py --name waifu-name-bot-v2 --interpreter .venv/bin/python --time
pm2 save
pm2 logs waifu-name-bot-v2 --lines 50
