"""
bot.py — Bot Telegram untuk memicu build kernel POCO X3 NFC (surya)
lewat GitHub Actions, lalu mengirim hasilnya (ZIP + log) ke chat Telegram.

Alur:
  1. User kirim /build atau /build_custom
  2. Bot memicu workflow_dispatch di GitHub Actions
  3. Bot polling status run tiap POLL_INTERVAL_SECONDS
  4. Setelah selesai, bot kirim notifikasi + link artifact
     (file ZIP dikirim otomatis oleh workflow lewat sendDocument
     kalau ukurannya < 50MB — lihat build-kernel.yml)
"""

import asyncio
import json
import logging
import time
from datetime import datetime, timezone
from pathlib import Path

import requests
from telegram import InlineKeyboardButton, InlineKeyboardMarkup, Update
from telegram.ext import (
    Application,
    CallbackQueryHandler,
    CommandHandler,
    ContextTypes,
)

import config

logging.basicConfig(
    format="%(asctime)s - %(name)s - %(levelname)s - %(message)s",
    level=logging.INFO,
)
logger = logging.getLogger("kernel-bot")

STATE_FILE = Path(__file__).parent / "state.json"
GITHUB_API = "https://api.github.com"

# Pilihan sementara user saat pakai /build_custom (chat_id -> dict pilihan)
PENDING_CUSTOM_BUILD: dict[int, dict] = {}


# ─────────────────────────── State helper ────────────────────────────
def load_state() -> dict:
    if STATE_FILE.exists():
        try:
            return json.loads(STATE_FILE.read_text())
        except json.JSONDecodeError:
            logger.warning("state.json rusak, membuat state baru.")
    return {}


def save_state(state: dict) -> None:
    STATE_FILE.write_text(json.dumps(state, indent=2))


def get_user_state(chat_id: int) -> dict:
    state = load_state()
    return state.get(str(chat_id), {})


def set_user_state(chat_id: int, **kwargs) -> None:
    state = load_state()
    user_state = state.get(str(chat_id), {})
    user_state.update(kwargs)
    state[str(chat_id)] = user_state
    save_state(state)


# ─────────────────────────── Auth helper ──────────────────────────────
def is_allowed(chat_id: int) -> bool:
    return chat_id in config.ALLOWED_CHAT_IDS


async def guard_allowed(update: Update) -> bool:
    chat_id = update.effective_chat.id
    if not is_allowed(chat_id):
        await update.message.reply_text(
            "Maaf, kamu tidak terdaftar untuk memakai bot ini.\n"
            f"Chat ID kamu: {chat_id} — minta admin menambahkannya ke ALLOWED_CHAT_IDS."
        )
        logger.warning("Akses ditolak untuk chat_id=%s", chat_id)
        return False
    return True


def check_cooldown(chat_id: int) -> float:
    """Return sisa cooldown dalam detik (0 kalau sudah boleh build lagi)."""
    user_state = get_user_state(chat_id)
    last_build_ts = user_state.get("last_build_ts")
    if last_build_ts is None:
        return 0
    elapsed = time.time() - last_build_ts
    remaining = config.BUILD_COOLDOWN_SECONDS - elapsed
    return max(0, remaining)


# ─────────────────────────── GitHub API helper ────────────────────────
def gh_headers() -> dict:
    return {
        "Authorization": f"Bearer {config.GITHUB_TOKEN}",
        "Accept": "application/vnd.github+json",
        "X-GitHub-Api-Version": "2022-11-28",
    }


def trigger_workflow(source: str, memkernel: str, ksunext: str) -> bool:
    url = (
        f"{GITHUB_API}/repos/{config.GITHUB_REPO}/actions/workflows/"
        f"{config.GITHUB_WORKFLOW_FILE}/dispatches"
    )
    payload = {
        "ref": config.GITHUB_REF,
        "inputs": {
            "source": source,
            "memkernel": memkernel,
            "ksunext": ksunext,
        },
    }
    resp = requests.post(url, headers=gh_headers(), json=payload, timeout=30)
    if resp.status_code == 204:
        return True
    logger.error("Gagal trigger workflow: %s %s", resp.status_code, resp.text)
    return False


def find_latest_run(after_ts: float) -> dict | None:
    """Cari run terbaru dari workflow yang dibuat setelah after_ts."""
    url = (
        f"{GITHUB_API}/repos/{config.GITHUB_REPO}/actions/workflows/"
        f"{config.GITHUB_WORKFLOW_FILE}/runs"
    )
    params = {"branch": config.GITHUB_REF, "per_page": 5}
    resp = requests.get(url, headers=gh_headers(), params=params, timeout=30)
    if resp.status_code != 200:
        logger.error("Gagal ambil daftar run: %s %s", resp.status_code, resp.text)
        return None

    runs = resp.json().get("workflow_runs", [])
    for run in runs:
        created = datetime.fromisoformat(
            run["created_at"].replace("Z", "+00:00")
        ).timestamp()
        if created >= after_ts - 5:  # toleransi 5 detik
            return run
    return None


def get_run(run_id: int) -> dict | None:
    url = f"{GITHUB_API}/repos/{config.GITHUB_REPO}/actions/runs/{run_id}"
    resp = requests.get(url, headers=gh_headers(), timeout=30)
    if resp.status_code != 200:
        return None
    return resp.json()


def cancel_run(run_id: int) -> bool:
    url = f"{GITHUB_API}/repos/{config.GITHUB_REPO}/actions/runs/{run_id}/cancel"
    resp = requests.post(url, headers=gh_headers(), timeout=30)
    return resp.status_code == 202


def list_artifacts(run_id: int) -> list[dict]:
    url = f"{GITHUB_API}/repos/{config.GITHUB_REPO}/actions/runs/{run_id}/artifacts"
    resp = requests.get(url, headers=gh_headers(), timeout=30)
    if resp.status_code != 200:
        return []
    return resp.json().get("artifacts", [])


# ─────────────────────────── Command handlers ─────────────────────────
async def start(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    await update.message.reply_text(
        "🤖 Kernel Build Bot — POCO X3 NFC (surya)\n\n"
        "Bot ini memicu build kernel lewat GitHub Actions, jadi kamu "
        "tidak perlu HP kuat, Termux, atau laptop.\n\n"
        "Ketik /help untuk daftar perintah."
    )


async def help_cmd(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    await update.message.reply_text(
        "Daftar perintah:\n"
        "/build — build default (StormBreaker X8 + MemKernel Y + KernelSU-Next)\n"
        "/build_custom — pilih source, MemKernel, dan KernelSU-Next manual\n"
        "/status — cek status build terakhir\n"
        "/cancel — batalkan build yang sedang berjalan\n"
        "/logs — kirim log build terakhir\n"
        "/about — info bot"
    )


async def about(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    await update.message.reply_text(
        "Kernel Build Bot\n"
        "Device target: POCO X3 NFC (surya), Android 10\n"
        "Build server: GitHub Actions (gratis)\n"
        "Dibuat untuk otomasi build kernel tanpa perlu perangkat build lokal."
    )


async def _start_build(
    update: Update, chat_id: int, source: str, memkernel: str, ksunext: str
) -> None:
    remaining = check_cooldown(chat_id)
    if remaining > 0:
        minutes = int(remaining // 60) + 1
        await update.effective_message.reply_text(
            f"⏳ Tunggu sekitar {minutes} menit lagi sebelum build berikutnya "
            f"(limit 1 build / {config.BUILD_COOLDOWN_SECONDS // 60} menit)."
        )
        return

    user_state = get_user_state(chat_id)
    if user_state.get("status") == "running":
        await update.effective_message.reply_text(
            "⚠️ Masih ada build yang sedang berjalan. Pakai /status untuk cek, "
            "atau /cancel untuk membatalkan."
        )
        return

    await update.effective_message.reply_text(
        f"🚀 Build dimulai...\nSource: {source}\nMemKernel: {memkernel}\n"
        f"KernelSU-Next: {ksunext}\n\nMemicu workflow di GitHub Actions..."
    )

    dispatch_ts = time.time()
    if not trigger_workflow(source, memkernel, ksunext):
        await update.effective_message.reply_text(
            "❌ Gagal memicu workflow. Cek GITHUB_TOKEN / GITHUB_REPO, atau coba lagi."
        )
        return

    # GitHub API tidak langsung mengembalikan run_id, jadi cari run terbaru
    run = None
    for _ in range(6):
        await asyncio.sleep(5)
        run = find_latest_run(dispatch_ts)
        if run:
            break

    if not run:
        await update.effective_message.reply_text(
            "⚠️ Workflow terpicu, tapi bot gagal menemukan run_id untuk polling. "
            "Cek manual di tab Actions repo kamu."
        )
        set_user_state(chat_id, last_build_ts=dispatch_ts, status="unknown")
        return

    set_user_state(
        chat_id,
        last_build_ts=dispatch_ts,
        run_id=run["id"],
        status="running",
        source=source,
        memkernel=memkernel,
        ksunext=ksunext,
        run_url=run["html_url"],
    )

    await update.effective_message.reply_text(
        f"✅ Workflow berjalan: {run['html_url']}\n"
        "Bot akan polling status dan mengirim notifikasi begitu selesai "
        "(estimasi 30-90 menit)."
    )

    context.application.create_task(poll_build(chat_id, run["id"], context))


async def build(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    if not await guard_allowed(update):
        return
    chat_id = update.effective_chat.id
    await _start_build(
        update,
        chat_id,
        config.DEFAULT_SOURCE,
        config.DEFAULT_MEMKERNEL,
        config.DEFAULT_KSUNEXT,
    )


async def build_custom(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    if not await guard_allowed(update):
        return
    chat_id = update.effective_chat.id
    PENDING_CUSTOM_BUILD[chat_id] = {}

    keyboard = [
        [
            InlineKeyboardButton("StormBreaker X8", callback_data="src:stormbreaker"),
            InlineKeyboardButton("Stratosphere", callback_data="src:stratosphere"),
        ]
    ]
    await update.message.reply_text(
        "Pilih source kernel:", reply_markup=InlineKeyboardMarkup(keyboard)
    )


async def on_callback(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    query = update.callback_query
    chat_id = query.message.chat_id
    if not is_allowed(chat_id):
        await query.answer("Tidak diizinkan.", show_alert=True)
        return

    await query.answer()
    data = query.data
    choices = PENDING_CUSTOM_BUILD.setdefault(chat_id, {})

    if data.startswith("src:"):
        choices["source"] = data.split(":", 1)[1]
        keyboard = [
            [
                InlineKeyboardButton("MemKernel Y", callback_data="mem:Y"),
                InlineKeyboardButton("MemKernel M", callback_data="mem:M"),
                InlineKeyboardButton("Tanpa MemKernel", callback_data="mem:none"),
            ]
        ]
        await query.edit_message_text(
            f"Source: {choices['source']}\n\nPilih MemKernel:",
            reply_markup=InlineKeyboardMarkup(keyboard),
        )

    elif data.startswith("mem:"):
        choices["memkernel"] = data.split(":", 1)[1]
        keyboard = [
            [
                InlineKeyboardButton("Ya", callback_data="ksu:true"),
                InlineKeyboardButton("Tidak", callback_data="ksu:false"),
            ]
        ]
        await query.edit_message_text(
            f"Source: {choices['source']}\nMemKernel: {choices['memkernel']}\n\n"
            "Pakai KernelSU-Next?",
            reply_markup=InlineKeyboardMarkup(keyboard),
        )

    elif data.startswith("ksu:"):
        choices["ksunext"] = data.split(":", 1)[1]
        await query.edit_message_text(
            f"Source: {choices['source']}\nMemKernel: {choices['memkernel']}\n"
            f"KernelSU-Next: {choices['ksunext']}\n\nMemulai build..."
        )
        await _start_build(
            update,
            chat_id,
            choices["source"],
            choices["memkernel"],
            choices["ksunext"],
        )
        PENDING_CUSTOM_BUILD.pop(chat_id, None)


async def status_cmd(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    if not await guard_allowed(update):
        return
    chat_id = update.effective_chat.id
    user_state = get_user_state(chat_id)

    if not user_state.get("run_id"):
        await update.message.reply_text("Belum ada riwayat build.")
        return

    run = get_run(user_state["run_id"])
    if not run:
        await update.message.reply_text("Gagal mengambil status run dari GitHub.")
        return

    await update.message.reply_text(
        f"Status build terakhir:\n"
        f"Source: {user_state.get('source', '-')}\n"
        f"Status: {run['status']} (conclusion: {run.get('conclusion') or '-'})\n"
        f"Link: {run['html_url']}"
    )


async def cancel_cmd(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    if not await guard_allowed(update):
        return
    chat_id = update.effective_chat.id
    user_state = get_user_state(chat_id)
    run_id = user_state.get("run_id")

    if not run_id or user_state.get("status") != "running":
        await update.message.reply_text("Tidak ada build yang sedang berjalan.")
        return

    if cancel_run(run_id):
        set_user_state(chat_id, status="cancelled")
        await update.message.reply_text("🛑 Build dibatalkan.")
    else:
        await update.message.reply_text(
            "Gagal membatalkan build (mungkin sudah selesai)."
        )


async def logs_cmd(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    if not await guard_allowed(update):
        return
    chat_id = update.effective_chat.id
    user_state = get_user_state(chat_id)
    run_id = user_state.get("run_id")

    if not run_id:
        await update.message.reply_text("Belum ada riwayat build.")
        return

    artifacts = list_artifacts(run_id)
    log_artifact = next(
        (a for a in artifacts if a["name"].startswith("build-log-")), None
    )
    if not log_artifact:
        await update.message.reply_text(
            "Log belum tersedia (build mungkin masih berjalan atau gagal upload log)."
        )
        return

    await update.message.reply_text(
        f"📄 Log build tersedia di artifact GitHub:\n"
        f"{log_artifact['archive_download_url']}\n\n"
        "(Perlu login GitHub dengan akses ke repo untuk mengunduhnya.)"
    )


# ─────────────────────────── Polling background task ──────────────────
async def poll_build(chat_id: int, run_id: int, context: ContextTypes.DEFAULT_TYPE) -> None:
    while True:
        run = get_run(run_id)
        if run is None:
            await context.bot.send_message(
                chat_id, "⚠️ Gagal cek status run, mencoba lagi..."
            )
        elif run["status"] == "completed":
            conclusion = run.get("conclusion", "unknown")
            set_user_state(chat_id, status="completed", conclusion=conclusion)
            emoji = "✅" if conclusion == "success" else "❌"
            await context.bot.send_message(
                chat_id,
                f"{emoji} Build selesai dengan hasil: {conclusion}\n"
                f"Detail: {run['html_url']}\n\n"
                "File ZIP akan dikirim otomatis oleh workflow kalau ukurannya "
                "< 50MB. Kalau tidak muncul, cek artifact di link di atas, "
                "atau pakai /logs.",
            )
            return

        await asyncio.sleep(config.POLL_INTERVAL_SECONDS)


# ─────────────────────────── Main ──────────────────────────────────────
def main() -> None:
    if not config.BOT_TOKEN:
        raise SystemExit("BOT_TOKEN belum diset di environment variable.")
    if not config.GITHUB_TOKEN or not config.GITHUB_REPO:
        raise SystemExit("GITHUB_TOKEN / GITHUB_REPO belum diset.")

    app = Application.builder().token(config.BOT_TOKEN).build()

    app.add_handler(CommandHandler("start", start))
    app.add_handler(CommandHandler("help", help_cmd))
    app.add_handler(CommandHandler("about", about))
    app.add_handler(CommandHandler("build", build))
    app.add_handler(CommandHandler("build_custom", build_custom))
    app.add_handler(CommandHandler("status", status_cmd))
    app.add_handler(CommandHandler("cancel", cancel_cmd))
    app.add_handler(CommandHandler("logs", logs_cmd))
    app.add_handler(CallbackQueryHandler(on_callback))

    logger.info("Bot berjalan...")
    app.run_polling()


if __name__ == "__main__":
    main()
    
