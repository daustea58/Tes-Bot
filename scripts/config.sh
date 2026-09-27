#!/usr/bin/env bash
# config.sh — Konfigurasi sumber kernel, toolchain, dan komponen tambahan
# untuk build kernel POCO X3 NFC (codename: surya)

# URL sumber kernel
SOURCE_STRATOSPHERE="https://github.com/urmommine/android_kernel_xiaomi_surya"
SOURCE_STORMBREAKER="https://github.com/stormbreaker-project/kernel_xiaomi_surya"
STORMBREAKER_TAG="X8"

# Toolchain compiler
PROTON_CLANG="https://github.com/kdrag0n/proton-clang"

# Komponen tambahan (opsional, dipasang lewat setup.sh masing-masing)
MEMKERNEL_SETUP="https://raw.githubusercontent.com/Poko-Apps/MemKernel/main/kernel/setup.sh"
KERNELSU_NEXT_SETUP="https://raw.githubusercontent.com/KernelSU-Next/KernelSU-Next/next/kernel/setup.sh"

# Packaging
ANY_KERNEL3="https://github.com/osm0sis/AnyKernel3"

# Target device
DEVICE_CODENAME="surya"
ARCH="arm64"

# Nama defconfig — sesuaikan kalau berbeda di source yang dipakai
DEFCONFIG_NAME="vendor/surya-perf_defconfig"
