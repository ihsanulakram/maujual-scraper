# 📱 Maujual.com HP Scraper & Interactive Telegram Bot

Bot Telegram pintar dan otomatis untuk mencari stok HP bekas berkualitas di [shop.maujual.com](https://shop.maujual.com). Dilengkapi fitur kuesioner interaktif (`/start`), multi-select kriteria (Brand, Storage, Kondisi, RAM, Harga bebas), kontrol stop/resume, serta notifikasi instan via Telegram.

---

## 🚀 Fitur Utama
1. **Interactive Onboarding (`/start`)**:
   - Bot tidak langsung scan sebelum user mengonfigurasi kriteria.
   - Kuesioner bertahap dengan tombol checklist `[✓]` di Telegram.
2. **Multi-Select Checkbox**:
   - **Brand**: Pilih satu atau beberapa brand (Samsung, Xiaomi, Oppo, Vivo, Realme, iPhone, Infinix, atau Bebas).
   - **Storage**: Pilih beberapa ukuran (32GB, 64GB, 128GB, 256GB, atau Bebas).
   - **Kondisi Unit**: Pilih kondisi yang diinginkan (Mulus, Standar, Ekonomis, atau Bebas).
3. **RAM & Custom Price Input**:
   - Filter kapasitas minimal RAM (Bebas, 3GB, 4GB, 6GB, 8GB+).
   - Batas harga fleksibel: Preset atau **Ketik Manual Bebas** (misal: `1250000` atau `1.250.000`).
4. **Hanya Varian Ready Stock**:
   - Hanya menampilkan varian yang benar-benar tersedia stoknya dan cocok dengan kriteria Anda.
5. **Kontrol Monitoring (`/stop` & `/resume`)**:
   - Berhenti menerima notifikasi kapan saja dengan `/stop`.
   - Mengaktifkan kembali dengan `/resume`.
6. **Database Anti-Spam (`sent_jackpot.json`)**:
   - Tidak akan mengirim produk yang sama dua kali.

---

## 💬 Perintah Bot Telegram

| Perintah | Deskripsi |
|---|---|
| `/start` | Memulai kuesioner awal untuk menentukan kriteria HP yang dicari |
| `/filter` | Mengubah kriteria pencarian (Brand, Storage, Kondisi, RAM, Harga) |
| `/status` | Melihat status bot (Aktif/Nonaktif) & filter yang sedang terpasang |
| `/stop` | Menonaktifkan notifikasi (tidak menerima notifikasi lagi) |
| `/resume` | Mengaktifkan kembali notifikasi |
| `/help` | Menampilkan panduan bantuan |

---

## 📋 Cara Penggunaan

### 1. Menjalankan Bot di Komputer / Termux
Cukup jalankan file launcher:
- **Windows**: Double-click `run_scraper.bat`, atau:
  ```powershell
  python scraper_maujual.py
  ```
- **Android (Termux)** / **Linux**:
  ```bash
  python scraper_maujual.py
  ```

### 2. Atur Kriteria di Telegram
1. Buka bot Anda di aplikasi Telegram.
2. Kirim perintah: `/start`
3. Tekan tombol-tombol pilihan di Telegram sesuai HP idaman Anda:
   - Pilih Brand (bisa pilih beberapa, lalu klik *Selesai & Lanjut*)
   - Pilih Storage (bisa pilih beberapa)
   - Pilih Kondisi (Mulus, Standar, Ekonomis)
   - Pilih Minimal RAM
   - Pilih Batas Harga (atau ketik nominal bebas di chat, misal: `1250000`)
4. Bot akan mengonfirmasi bahwa monitoring telah aktif!

---

## 📁 Struktur File
```
maujual-scraper/
├── .github/workflows/scraper.yml  # Otomatisasi GitHub Actions (30 menit)
├── scraper_maujual.py             # Script utama bot & scraper
├── run_scraper.bat                # Launcher cepat Windows
├── requirements.txt               # Daftar pustaka Python
├── sent_jackpot.json              # Database riwayat produk terkirim
├── user_preferences.json          # Pengaturan kriteria filter pengguna
└── README.md                      # Dokumentasi ini
```
