---
title: Maujual Bot
emoji: 📱
colorFrom: blue
colorTo: indigo
sdk: docker
app_port: 7860
pinned: false
---

# 📱 Maujual.com HP Scraper & Multi-Wishlist Telegram Bot

Bot Telegram pintar dan otomatis untuk berburu stok HP bekas berkualitas di [shop.maujual.com](https://shop.maujual.com). Dilengkapi **Sistem Multi-Wishlist** (bisa memantau banyak target incaran sekaligus dengan kriteria berbeda), **Foto Produk Asli**, **16 Parameter Spesifikasi Lengkap**, serta otomatisasi GitHub Actions setiap 15 menit.

---

## 🚀 Fitur Unggulan

1. **🎯 Sistem Multi-Wishlist (`/wishlist`)**:
   - Pasang beberapa incaran HP berbeda sekaligus (contoh: *"HP Gaming"*, *"Incaran iPhone"*, *"HP Cadangan Murah"*).
   - Setiap incaran memiliki kriteria mandiri (Brand, Storage, Kondisi, RAM, dan Harga).
   - Notifikasi Telegram mencantumkan nama target incaran dengan jelas (`🎯 TARGET: [Nama Target]`).

2. **📸 Foto HP & 16 Spesifikasi Lengkap**:
   - Mengambil foto unit asli langsung dari katalog Maujual via API `sendPhoto`.
   - Menampilkan spesifikasi teknis lengkap: Chipset, RAM, OS, Baterai, Charging, Layar, Kamera Utama & Selfie, NFC, USB, SIM, Berat, dan Dimensi.
   - User tidak perlu lagi membuka web Maujual hanya untuk mengecek spek!

3. **⚡ Scan Awal Instan**:
   - Begitu sebuah target incaran baru ditambahkan via Telegram, bot langsung melakukan scan seketika ke seluruh katalog untuk melaporkan stok ready saat ini.

4. **🎛️ Dashboard Interaktif Telegram**:
   - Menu tombol untuk mengelola semua target incaran:
     - `[➕ Tambah Incaran Baru]`
     - `[👁️ Lihat Detail Kriteria]`
     - `[⏸️ Jeda / ▶️ Resume]`
     - `[🗑️ Hapus Target]`

5. **🛡️ Anti-Spam Cerdas Per-Wishlist**:
   - Melacak riwayat produk terkirim per-target incaran, sehingga tidak ada spam pesan dobel untuk target yang sama.

6. **☁️ GitHub Actions 15 Menit Unlimited**:
   - Berjalan otomatis di cloud GitHub Actions setiap 15 menit tanpa membebani komputer Anda.

---

## 💬 Perintah Bot Telegram

| Perintah | Deskripsi |
|---|---|
| `/wishlist` | Membuka Dashboard Multi-Wishlist (lihat, jeda/resume, dan hapus target) |
| `/tambah` | Shortcut membuat target incaran HP baru |
| `/status` | Cek status monitoring dan daftar target aktif |
| `/help` | Menampilkan panduan penggunaan bot |

---

## 📋 Cara Penggunaan

### 1. Menjalankan Bot Interaktif di Komputer
Cukup double-click file launcher:
- **Windows**: Jalankan `run_scraper.bat`, atau:
  ```powershell
  python scraper_maujual.py
  ```

### 2. Kelola Target Incaran di Telegram
1. Buka bot Anda di Telegram, kirim perintah: `/wishlist`
2. Klik tombol **➕ Tambah Incaran Baru**
3. Masukkan nama incaran Anda (contoh: `HP Gaming Murah`)
4. Pilih kriteria melalui tombol checklist:
   - **Brand**: Samsung, Xiaomi, Oppo, Vivo, Realme, iPhone, Infinix, atau Bebas
   - **Storage**: 32GB, 64GB, 128GB, 256GB, atau Bebas
   - **Kondisi**: Mulus, Standar, Ekonomis, atau Bebas
   - **RAM**: Bebas, Min 3GB, Min 4GB, Min 6GB, Min 8GB+
   - **Batas Budget**: Preset atau ketik nominal bebas di chat (contoh: `1250000`)
5. Bot akan langsung menyimpan target Anda dan melakukan scan awal seketika!

---

## 📁 Struktur File Proyek
```
maujual-scraper/
├── .github/workflows/scraper.yml  # Otomatisasi GitHub Actions (setiap 15 menit)
├── scraper_maujual.py             # Script utama bot, scraper, dan multi-wishlist engine
├── run_scraper.bat                # Launcher cepat Windows
├── requirements.txt               # Daftar pustaka Python
├── sent_jackpot.json              # Database riwayat produk terkirim per-wishlist
├── user_preferences.json          # Database daftar multi-wishlist pengguna
├── .env.example                   # Template konfigurasi environment variables
└── README.md                      # Dokumentasi proyek
```
