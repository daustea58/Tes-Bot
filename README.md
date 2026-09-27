# Kernel Build Bot — POCO X3 NFC (surya)

Bot Telegram yang memicu build kernel Android untuk **POCO X3 NFC (codename: surya, Android 10)**
lewat GitHub Actions. Kamu tidak perlu HP kuat, Termux, atau laptop — semua proses build
berjalan di server gratis GitHub.

## Fitur

- Trigger build kernel langsung dari chat Telegram (`/build`)
- Pilih manual source kernel, MemKernel, dan KernelSU-Next lewat inline keyboard (`/build_custom`)
- Polling status build otomatis, kirim notifikasi begitu selesai
- Kirim file ZIP kernel langsung ke Telegram (kalau < 50MB) + checksum SHA256
- Cek status (`/status`), batalkan build (`/cancel`), ambil log (`/logs`)
- Verifikasi user lewat whitelist chat_id
- Rate limit 1 build per user per 30 menit (bisa diubah)

## Struktur Repository

```
kernel-bot/
├── .github/workflows/build-kernel.yml   # Workflow GitHub Actions
├── bot/
│   ├── bot.py            # Bot Telegram (Python)
│   ├── config.py         # Konfigurasi (baca dari environment variable)
│   └── requirements.txt  # Dependency Python
├── scripts/
│   ├── build.sh           # Script build kernel (dipanggil workflow)
│   └── config.sh          # Konfigurasi sumber kernel & toolchain
├── README.md
└── .gitignore
```

## Cara Setup

### 1. Buat Bot Telegram

1. Chat [@BotFather](https://t.me/BotFather), kirim `/newbot`, ikuti instruksinya.
2. Catat **BOT_TOKEN** yang diberikan.
3. Chat [@userinfobot](https://t.me/userinfobot) untuk mendapatkan **chat_id** kamu sendiri.

### 2. Buat Repository GitHub

1. Buat repository baru (boleh public atau private).
2. Upload semua file dari struktur di atas ke repository tersebut.
3. Buat **Personal Access Token** GitHub dengan scope `repo` dan `workflow`
   (Settings → Developer settings → Personal access tokens).
4. Di repository, buka **Settings → Secrets and variables → Actions**, tambahkan:
   - `BOT_TOKEN` — token bot Telegram
   - `TELEGRAM_CHAT_ID` — chat_id kamu (dipakai workflow untuk kirim notifikasi)
5. Pastikan Actions aktif: **Settings → Actions → General → Allow all actions**.

### 3. Jalankan Bot

Bot perlu jalan terus-menerus (long polling) supaya bisa menerima perintah.
Isi environment variable berikut sebelum menjalankan `bot.py`:

```bash
export BOT_TOKEN="isi-token-botfather"
export GITHUB_TOKEN="isi-personal-access-token"
export GITHUB_REPO="username/nama-repo"
export ALLOWED_CHAT_IDS="123456789,987654321"
```

Lalu:

```bash
cd bot
pip install -r requirements.txt
python3 bot.py
```

Pilihan tempat menjalankan bot supaya tetap online 24/7:

- **VPS (Ubuntu)** — pakai `systemd` service, lihat contoh `kernel-bot.service` di bawah.
- **Railway.app** — deploy sebagai worker Python, isi environment variable di dashboard.
- **Render.com** — deploy sebagai Background Worker.
- **Termux HP sendiri** — hanya untuk menjalankan bot (build tetap di GitHub Actions,
  bukan di HP), cukup ringan karena bot cuma polling + panggil API.

### 4. Contoh systemd service

Simpan sebagai `/etc/systemd/system/kernel-bot.service`:

```ini
[Unit]
Description=Kernel Build Bot
After=network.target

[Service]
Type=simple
User=ubuntu
WorkingDirectory=/home/ubuntu/kernel-bot/bot
Environment="BOT_TOKEN=isi-token"
Environment="GITHUB_TOKEN=isi-token"
Environment="GITHUB_REPO=username/nama-repo"
Environment="ALLOWED_CHAT_IDS=123456789"
ExecStart=/usr/bin/python3 bot.py
Restart=always

[Install]
WantedBy=multi-user.target
```

Aktifkan:

```bash
sudo systemctl daemon-reload
sudo systemctl enable --now kernel-bot.service
sudo systemctl status kernel-bot.service
```

## Cara Pakai Bot

| Perintah | Fungsi |
|---|---|
| `/start` | Sambutan + info singkat |
| `/help` | Daftar perintah |
| `/build` | Build default: StormBreaker X8 + MemKernel Y + KernelSU-Next |
| `/build_custom` | Pilih source, MemKernel, dan KernelSU-Next manual lewat tombol |
| `/status` | Cek status build terakhir |
| `/cancel` | Batalkan build yang sedang berjalan |
| `/logs` | Ambil link log build terakhir |
| `/about` | Info bot |

Alur build:

1. Kirim `/build` atau `/build_custom`.
2. Bot memicu workflow GitHub Actions dan mulai polling status.
3. Setelah build selesai (30–90 menit), bot kirim notifikasi hasil.
4. Kalau ZIP < 50MB, file dikirim otomatis oleh workflow lewat Telegram.
   Kalau lebih besar, ambil dari tab **Actions → run terkait → Artifacts**.

## Troubleshooting Umum

- **Bot tidak merespons** — pastikan proses `bot.py` masih jalan (`systemctl status`
  kalau pakai VPS), dan `BOT_TOKEN` benar.
- **"Gagal memicu workflow"** — cek `GITHUB_TOKEN` masih valid dan punya scope `workflow`,
  serta `GITHUB_REPO` sudah benar formatnya (`username/repo`).
- **Build gagal di step compile** — cek `build.log` di artifact `build-log-*`, biasanya
  karena defconfig tidak cocok dengan source yang dipilih.
- **ZIP tidak terkirim ke Telegram** — kemungkinan ukurannya ≥ 50MB, ambil manual dari
  artifact GitHub Actions.
- **"Tidak diizinkan" saat pakai bot** — chat_id kamu belum ada di `ALLOWED_CHAT_IDS`.

## Catatan Penting

- GitHub Actions gratis untuk repo public (tanpa batas) dan repo private (2000 menit/bulan).
- Build kernel surya biasanya makan waktu 30–90 menit di runner GitHub.
- Ukuran ZIP hasil build sekitar 15–25MB, aman untuk limit Telegram 50MB.
- **Jangan pernah** commit token ke kode — selalu pakai environment variable / GitHub Secrets.
- StormBreaker X8 tidak mendukung MIUI A11 / ROM berbasis vendor MIUI.
- MemKernel bukan driver resmi — pakai dengan risiko sendiri.
- **Selalu backup partisi boot** sebelum flash hasil build.
- Kalau GitHub Actions sedang down, bot tidak bisa memicu build — tunggu status GitHub pulih.

## Kredit & Sumber

- [StormBreaker Project](https://github.com/stormbreaker-project)
- [Proton Clang](https://github.com/kdrag0n/proton-clang)
- [MemKernel](https://github.com/Poko-Apps/MemKernel)
- [KernelSU-Next](https://github.com/KernelSU-Next/KernelSU-Next)
- [AnyKernel3](https://github.com/osm0sis/AnyKernel3)
- [python-telegram-bot](https://github.com/python-telegram-bot/python-telegram-bot)

## Lisensi

Kernel dan komponen di atas mengikuti lisensi masing-masing (umumnya GPLv2 untuk kernel
Linux/Android). Script bot dan workflow di repository ini bebas dipakai dan dimodifikasi
untuk keperluan pribadi.
