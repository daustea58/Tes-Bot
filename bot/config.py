"""
config.py — Konfigurasi bot Telegram.
Semua nilai sensitif diambil dari environment variable, JANGAN hardcode
token di sini.
"""

import os

# Token bot Telegram, didapat dari @BotFather
BOT_TOKEN = os.getenv("BOT_TOKEN")

# Personal Access Token GitHub (scope: repo, workflow)
GITHUB_TOKEN = os.getenv("GITHUB_TOKEN")

# Format: "username/nama-repo"
GITHUB_REPO = os.getenv("GITHUB_REPO")

# Nama file workflow yang mau dipicu
GITHUB_WORKFLOW_FILE = os.getenv("GITHUB_WORKFLOW_FILE", "build-kernel.yml")

# Branch tempat workflow dijalankan
GITHUB_REF = os.getenv("GITHUB_REF", "main")

# Daftar chat_id yang diizinkan memakai bot (pisahkan dengan koma di env)
ALLOWED_CHAT_IDS = [
    int(x) for x in os.getenv("ALLOWED_CHAT_IDS", "").split(",") if x.strip()
]

# Jeda minimum antar build per user (detik) — default 30 menit
BUILD_COOLDOWN_SECONDS = int(os.getenv("BUILD_COOLDOWN_SECONDS", "1800"))

# Interval polling status workflow (detik)
POLL_INTERVAL_SECONDS = int(os.getenv("POLL_INTERVAL_SECONDS", "30"))

# Opsi default untuk /build (build cepat tanpa memilih manual)
DEFAULT_SOURCE = "stormbreaker"
DEFAULT_MEMKERNEL = "Y"
DEFAULT_KSUNEXT = "true"
