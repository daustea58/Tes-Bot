#!/usr/bin/env bash
# build.sh — Script build kernel Surya (POCO X3 NFC)
# Dipanggil oleh workflow GitHub Actions dengan beberapa stage:
#   --stage clone      -> clone kernel source + toolchain
#   --stage integrate  -> integrasi MemKernel & KernelSU-Next
#   --stage build      -> apply config & compile kernel
#   --stage package    -> package hasil build jadi ZIP AnyKernel3
#
# Semua output di-log ke build.log

set -uo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
ROOT_DIR="$(cd "$SCRIPT_DIR/.." && pwd)"
# shellcheck disable=SC1091
source "$SCRIPT_DIR/config.sh"

LOG_FILE="$ROOT_DIR/build.log"
KERNEL_DIR="$ROOT_DIR/kernel_src"
CLANG_DIR="$ROOT_DIR/proton-clang"
OUT_DIR="$KERNEL_DIR/out"
ANYKERNEL_DIR="$ROOT_DIR/AnyKernel3"

# ── Parsing argumen ──────────────────────────────────────────────
SOURCE="stormbreaker"
MEMKERNEL="Y"
KSUNEXT="true"
STAGE=""

while [[ $# -gt 0 ]]; do
  case "$1" in
    --source) SOURCE="$2"; shift 2 ;;
    --memkernel) MEMKERNEL="$2"; shift 2 ;;
    --ksunext) KSUNEXT="$2"; shift 2 ;;
    --stage) STAGE="$2"; shift 2 ;;
    *) echo "Argumen tidak dikenal: $1"; shift ;;
  esac
done

log() {
  echo "[$(date '+%Y-%m-%d %H:%M:%S')] $*" | tee -a "$LOG_FILE"
}

# Cek environment: pastikan ini Linux (runner GitHub Actions), bukan Termux
check_environment() {
  if [[ -d "/data/data/com.termux" ]]; then
    log "ERROR: Script ini didesain untuk Linux (GitHub Actions runner), bukan Termux."
    exit 1
  fi
  log "Environment OK: $(uname -a)"
}

# Retry helper — coba ulang perintah sampai 3 kali kalau gagal
retry() {
  local n=1 max=3 delay=10
  until "$@"; do
    if (( n >= max )); then
      log "ERROR: Perintah gagal setelah $max percobaan: $*"
      return 1
    fi
    log "Percobaan $n gagal, mencoba lagi dalam ${delay}s..."
    n=$((n + 1))
    sleep "$delay"
  done
}

# ── Stage: clone ─────────────────────────────────────────────────
stage_clone() {
  check_environment
  mkdir -p "$ROOT_DIR"

  if [[ "$SOURCE" == "stratosphere" ]]; then
    REPO_URL="$SOURCE_STRATOSPHERE"
    BRANCH_ARGS=()
  else
    REPO_URL="$SOURCE_STORMBREAKER"
    BRANCH_ARGS=(--branch "$STORMBREAKER_TAG")
  fi

  log "Cloning kernel source dari $REPO_URL"
  retry git clone --depth=1 "${BRANCH_ARGS[@]}" "$REPO_URL" "$KERNEL_DIR"

  if [[ ! -d "$CLANG_DIR" ]] || [[ -z "$(ls -A "$CLANG_DIR" 2>/dev/null)" ]]; then
    log "Cloning Proton Clang toolchain"
    retry git clone --depth=1 "$PROTON_CLANG" "$CLANG_DIR"
  else
    log "Proton Clang sudah ada di cache, skip clone."
  fi
}

# ── Stage: integrate (MemKernel + KernelSU-Next) ────────────────
stage_integrate() {
  cd "$KERNEL_DIR" || exit 1

  if [[ "$MEMKERNEL" != "none" ]]; then
    log "Integrasi MemKernel (mode: $MEMKERNEL)"
    retry curl -sSL "$MEMKERNEL_SETUP" -o /tmp/memkernel_setup.sh
    bash /tmp/memkernel_setup.sh "$MEMKERNEL" 2>&1 | tee -a "$LOG_FILE" \
      || log "PERINGATAN: integrasi MemKernel gagal, lanjut tanpa MemKernel."
  else
    log "MemKernel dilewati (none)."
  fi

  if [[ "$KSUNEXT" == "true" ]]; then
    log "Integrasi KernelSU-Next"
    retry curl -sSL "$KERNELSU_NEXT_SETUP" -o /tmp/ksunext_setup.sh
    bash /tmp/ksunext_setup.sh 2>&1 | tee -a "$LOG_FILE" \
      || log "PERINGATAN: integrasi KernelSU-Next gagal, lanjut tanpa KSU-Next."
  else
    log "KernelSU-Next dilewati."
  fi
}

# Terapkan config tambahan ke defconfig sebelum build
apply_defconfig_options() {
  local defconfig_path="$KERNEL_DIR/arch/$ARCH/configs/$DEFCONFIG_NAME"
  if [[ ! -f "$defconfig_path" ]]; then
    log "PERINGATAN: defconfig $defconfig_path tidak ditemukan, skip apply option."
    return
  fi

  log "Menerapkan config tambahan ke $DEFCONFIG_NAME"
  cat >> "$defconfig_path" << 'EOF'
CONFIG_LOCALVERSION="-Surya-Bot"
CONFIG_MODULES=y
CONFIG_MODULE_FORCE_LOAD=y
CONFIG_MODULE_UNLOAD=y
CONFIG_MODULE_FORCE_UNLOAD=y
CONFIG_MODULE_SIG=n
CONFIG_MODULE_SIG_FORCE=n
CONFIG_MODULE_SIG_ALL=n
CONFIG_OVERLAY_FS=y
EOF
}

# ── Stage: build ─────────────────────────────────────────────────
stage_build() {
  cd "$KERNEL_DIR" || exit 1
  apply_defconfig_options

  export ARCH="$ARCH"
  export SUBARCH="$ARCH"
  export PATH="$CLANG_DIR/bin:$PATH"
  export CROSS_COMPILE="aarch64-linux-gnu-"
  export CROSS_COMPILE_ARM32="arm-linux-gnueabi-"
  export CLANG_TRIPLE="aarch64-linux-gnu-"
  export LLVM=1
  export LLVM_IAS=1

  log "Membuat defconfig: $DEFCONFIG_NAME"
  make O="$OUT_DIR" "$(basename "$DEFCONFIG_NAME")" 2>&1 | tee -a "$LOG_FILE"

  log "Mulai build kernel (make -j$(nproc))"
  make -j"$(nproc)" O="$OUT_DIR" 2>&1 | tee -a "$LOG_FILE"

  IMAGE_PATH="$OUT_DIR/arch/$ARCH/boot/Image.gz-dtb"
  if [[ ! -f "$IMAGE_PATH" ]]; then
    log "ERROR: Build gagal, Image.gz-dtb tidak ditemukan di $IMAGE_PATH"
    exit 1
  fi
  log "Build sukses: $IMAGE_PATH"
}

# ── Stage: package ───────────────────────────────────────────────
stage_package() {
  IMAGE_PATH="$OUT_DIR/arch/$ARCH/boot/Image.gz-dtb"
  if [[ ! -f "$IMAGE_PATH" ]]; then
    log "ERROR: Tidak ada Image.gz-dtb untuk di-package."
    exit 1
  fi

  log "Cloning AnyKernel3"
  retry git clone --depth=1 "$ANY_KERNEL3" "$ANYKERNEL_DIR"

  cp "$IMAGE_PATH" "$ANYKERNEL_DIR/Image.gz-dtb"

  TIMESTAMP="$(date '+%Y%m%d-%H%M')"
  ZIP_NAME="Kernel-Surya-${TIMESTAMP}.zip"
  ZIP_PATH="$ROOT_DIR/$ZIP_NAME"

  cd "$ANYKERNEL_DIR" || exit 1
  zip -r9 "$ZIP_PATH" . -x ".git*" -x "README.md"

  cd "$ROOT_DIR" || exit 1
  sha256sum "$ZIP_NAME" > "${ZIP_NAME}.sha256"

  log "Package selesai: $ZIP_NAME"
  log "SHA256: $(cat "${ZIP_NAME}.sha256")"

  # Dibaca oleh workflow lewat GITHUB_OUTPUT
  echo "$ZIP_PATH" > "$ROOT_DIR/out_zip_path.txt"
}

# ── Router stage ─────────────────────────────────────────────────
case "$STAGE" in
  clone) stage_clone ;;
  integrate) stage_integrate ;;
  build) stage_build ;;
  package) stage_package ;;
  *)
    echo "Stage tidak dikenal atau tidak diisi: '$STAGE'"
    echo "Gunakan salah satu: clone | integrate | build | package"
    exit 1
    ;;
esac
