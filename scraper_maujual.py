import os
import sys
import time
import json
import html
import re
import logging
import threading
from urllib.parse import urljoin
from datetime import datetime

import requests
from bs4 import BeautifulSoup
import schedule
import telebot
from telebot.types import InlineKeyboardMarkup, InlineKeyboardButton
import http.server
import socketserver

# Pastikan output console selalu mendukung UTF-8 (termasuk emoji) di semua OS
if hasattr(sys.stdout, "reconfigure"):
    sys.stdout.reconfigure(encoding="utf-8", errors="replace")
if hasattr(sys.stderr, "reconfigure"):
    sys.stderr.reconfigure(encoding="utf-8", errors="replace")

# ==============================================================================
# KONFIGURASI BOT & SCRAPER
# ==============================================================================
BASE_DIR = os.path.dirname(os.path.abspath(__file__))

# Baca file .env lokal jika ada (untuk PC/Termux)
def _load_env_file():
    env_path = os.path.join(BASE_DIR, ".env")
    if os.path.exists(env_path):
        with open(env_path, "r", encoding="utf-8") as f:
            for line in f:
                line = line.strip()
                if line and not line.startswith("#") and "=" in line:
                    k, v = line.split("=", 1)
                    os.environ.setdefault(k.strip(), v.strip())

_load_env_file()

# Kredensial murni dari Environment Variables / GitHub Secrets / .env lokal
TELEGRAM_TOKEN = os.getenv("TELEGRAM_TOKEN", "")
CHAT_ID = os.getenv("CHAT_ID", "")

# File database & preferensi
DB_FILE = os.path.join(BASE_DIR, "sent_jackpot.json")
PREFS_FILE = os.path.join(BASE_DIR, "user_preferences.json")

# Interval waktu cron job dalam menit (default 15 menit)
INTERVAL_MENIT = 15

HEADERS = {
    "User-Agent": (
        "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
        "AppleWebKit/537.36 (KHTML, like Gecko) "
        "Chrome/124.0.0.0 Safari/537.36"
    ),
    "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,image/avif,image/webp,*/*;q=0.8",
    "Accept-Language": "id-ID,id;q=0.9,en-US;q=0.8,en;q=0.7",
}

# ==============================================================================
# LOGGING SETUP
# ==============================================================================
logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(message)s",
    handlers=[
        logging.StreamHandler(sys.stdout)
    ]
)
logger = logging.getLogger("MaujualBot")

# Inisialisasi Bot Telegram (hanya jika TELEGRAM_TOKEN ada)
bot = telebot.TeleBot(TELEGRAM_TOKEN, parse_mode="HTML") if TELEGRAM_TOKEN else None

# Memory cache untuk state interaktif per-user
user_wizard_state = {}

# Daftar Opsi Wizard
AVAILABLE_BRANDS = ["Samsung", "Xiaomi", "Oppo", "Vivo", "Realme", "iPhone", "Infinix"]
AVAILABLE_STORAGES = ["32GB", "64GB", "128GB", "256GB"]
AVAILABLE_CONDITIONS = ["Mulus", "Standar", "Ekonomis"]
AVAILABLE_RAMS = [
    ("Bebas / Berapa Saja", 0),
    ("Min 3GB", 3),
    ("Min 4GB", 4),
    ("Min 6GB", 6),
    ("Min 8GB", 8),
]
PRICE_PRESETS = [
    ("Maks 1 Juta", 1000000),
    ("Maks 1.25 Juta", 1250000),
    ("Maks 1.5 Juta", 1500000),
    ("Maks 2 Juta", 2000000),
    ("Bebas / Tanpa Batas", 0),
]


# ==============================================================================
# PREFERENCES & DATABASE FUNCTIONS (MULTI-WISHLIST)
# ==============================================================================
def load_preferences():
    """
    Memuat seluruh data preferensi wishlist dari user_preferences.json.
    Mendukung migrasi otomatis dari format lama (single wishlist).
    """
    default_data = {"wishlists": []}
    if not os.path.exists(PREFS_FILE):
        return default_data

    try:
        with open(PREFS_FILE, "r", encoding="utf-8") as f:
            data = json.load(f)

        # Migrasi dari format lama (single-wishlist)
        if isinstance(data, dict) and "wishlists" not in data:
            if "brands" in data or "max_price" in data or "is_configured" in data:
                legacy_wl = {
                    "id": f"wl_{int(time.time())}",
                    "name": "Target Utama",
                    "is_active": data.get("is_active", True),
                    "brands": data.get("brands", []),
                    "storages": data.get("storages", []),
                    "conditions": data.get("conditions", []),
                    "min_ram_gb": data.get("min_ram_gb", 0),
                    "max_price": data.get("max_price", 1000000),
                    "created_at": datetime.now().strftime("%Y-%m-%d %H:%M:%S")
                }
                migrated = {"wishlists": [legacy_wl]}
                save_preferences(migrated)
                logger.info("Migrasi data user_preferences.json ke multi-wishlist berhasil.")
                return migrated

        if isinstance(data, dict) and "wishlists" in data:
            return data

        return default_data
    except Exception as e:
        logger.error(f"Gagal membaca {PREFS_FILE}: {e}")
        return default_data


def save_preferences(data):
    """Menyimpan data wishlist ke file user_preferences.json."""
    try:
        with open(PREFS_FILE, "w", encoding="utf-8") as f:
            json.dump(data, f, indent=2, ensure_ascii=False)
        logger.info(f"Preferensi pengguna berhasil disimpan ke {PREFS_FILE}")
    except Exception as e:
        logger.error(f"Gagal menyimpan ke {PREFS_FILE}: {e}")


def load_sent_data():
    """
    Memuat riwayat URL produk terkirim per-wishlist.
    Format: {"wl_id": ["url1", "url2"]}
    Mendukung migrasi dari format lama (list URL sederhana).
    """
    if not os.path.exists(DB_FILE):
        return {}

    try:
        with open(DB_FILE, "r", encoding="utf-8") as f:
            data = json.load(f)

        if isinstance(data, list):
            # Format lama: list string -> migrasi ke dict
            return {"_legacy": set(data)}
        elif isinstance(data, dict):
            return {k: set(v) for k, v in data.items()}
        return {}
    except Exception as e:
        logger.error(f"Gagal membaca {DB_FILE}: {e}")
        return {}


def save_sent_data(sent_data):
    """Menyimpan riwayat URL produk terkirim per-wishlist ke sent_jackpot.json."""
    try:
        serializable = {k: sorted(list(v)) for k, v in sent_data.items()}
        with open(DB_FILE, "w", encoding="utf-8") as f:
            json.dump(serializable, f, indent=2, ensure_ascii=False)
    except Exception as e:
        logger.error(f"Gagal menyimpan ke {DB_FILE}: {e}")


# ==============================================================================
# KEYBOARD BUILDERS
# ==============================================================================
def build_brand_markup(selected_brands):
    markup = InlineKeyboardMarkup(row_width=2)
    buttons = []
    for b in AVAILABLE_BRANDS:
        is_selected = b in selected_brands
        prefix = "✓ " if is_selected else ""
        buttons.append(
            InlineKeyboardButton(
                text=f"[{prefix}{b}]",
                callback_data=f"brand:toggle:{b}"
            )
        )
    markup.add(*buttons)
    markup.add(
        InlineKeyboardButton("✨ Pilih Semua / Bebas", callback_data="brand:all"),
        InlineKeyboardButton("➡️ Selesai & Lanjut", callback_data="brand:done")
    )
    return markup


def build_storage_markup(selected_storages):
    markup = InlineKeyboardMarkup(row_width=2)
    buttons = []
    for s in AVAILABLE_STORAGES:
        is_selected = s in selected_storages
        prefix = "✓ " if is_selected else ""
        buttons.append(
            InlineKeyboardButton(
                text=f"[{prefix}{s}]",
                callback_data=f"storage:toggle:{s}"
            )
        )
    markup.add(*buttons)
    markup.add(
        InlineKeyboardButton("✨ Pilih Semua / Bebas", callback_data="storage:all"),
        InlineKeyboardButton("➡️ Selesai & Lanjut", callback_data="storage:done")
    )
    return markup


def build_condition_markup(selected_conditions):
    markup = InlineKeyboardMarkup(row_width=1)
    for c in AVAILABLE_CONDITIONS:
        is_selected = c in selected_conditions
        prefix = "✓ " if is_selected else ""
        markup.add(
            InlineKeyboardButton(
                text=f"[{prefix}{c}]",
                callback_data=f"cond:toggle:{c}"
            )
        )
    markup.add(
        InlineKeyboardButton("✨ Pilih Semua / Bebas", callback_data="cond:all"),
        InlineKeyboardButton("➡️ Selesai & Lanjut", callback_data="cond:done")
    )
    return markup


def build_ram_markup():
    markup = InlineKeyboardMarkup(row_width=2)
    for label, val in AVAILABLE_RAMS:
        markup.add(
            InlineKeyboardButton(text=label, callback_data=f"ram:{val}")
        )
    return markup


def build_price_markup():
    markup = InlineKeyboardMarkup(row_width=2)
    for label, val in PRICE_PRESETS:
        markup.add(
            InlineKeyboardButton(text=label, callback_data=f"price:{val}")
        )
    markup.add(
        InlineKeyboardButton("✏️ Ketik Manual Bebas", callback_data="price:manual")
    )
    return markup


def build_wishlist_dashboard_markup(wishlists):
    """Membangun tombol navigasi untuk Dashboard Multi-Wishlist."""
    markup = InlineKeyboardMarkup(row_width=1)

    for wl in wishlists:
        wl_id = wl["id"]
        wl_name = wl.get("name", "Tanpa Nama")
        is_act = wl.get("is_active", True)
        status_icon = "🟢" if is_act else "⏸️"
        toggle_label = "Jeda ⏸️" if is_act else "Resume ▶️"

        # Baris kontrol per-wishlist
        row = [
            InlineKeyboardButton(f"{status_icon} {wl_name}", callback_data=f"wl:view:{wl_id}"),
            InlineKeyboardButton(toggle_label, callback_data=f"wl:toggle:{wl_id}"),
            InlineKeyboardButton("🗑️", callback_data=f"wl:del_confirm:{wl_id}")
        ]
        markup.row(*row)

    markup.add(
        InlineKeyboardButton("➕ Tambah Incaran Baru", callback_data="wl:new")
    )
    return markup


# ==============================================================================
# TELEGRAM BOT HANDLERS (/start, /wishlist, /tambah, /status, /help)
# ==============================================================================
if bot:
    @bot.message_handler(commands=["start", "wishlist"])
    def cmd_wishlist_dashboard(message):
        """Menampilkan Dashboard Daftar Wishlist Target Pengguna."""
        chat_id = str(message.chat.id)
        prefs = load_preferences()
        wishlists = prefs.get("wishlists", [])

        if not wishlists:
            text = (
                "👋 <b>Halo! Selamat datang di Bot Pencari HP Maujual.com!</b>\n\n"
                "Anda belum memiliki target incaran HP di wishlist Anda.\n"
                "Klik tombol di bawah untuk membuat target incaran pertama Anda!"
            )
            markup = InlineKeyboardMarkup()
            markup.add(InlineKeyboardButton("➕ Tambah Target Incaran Baru", callback_data="wl:new"))
            bot.send_message(chat_id, text, reply_markup=markup)
            return

        lines = [
            "📋 <b>DASHBOARD WISHLIST TARGET HP ANDA</b>",
            f"<i>Total Incaran: {len(wishlists)} target aktif/terdaftar</i>\n"
        ]

        for i, wl in enumerate(wishlists, 1):
            is_act = wl.get("is_active", True)
            status_tag = "🟢 <b>Aktif</b>" if is_act else "⏸️ <b>Dijeda</b>"
            brands = ", ".join(wl.get("brands", [])) if wl.get("brands") else "Semua Brand"
            storages = ", ".join(wl.get("storages", [])) if wl.get("storages") else "Semua Ukuran"
            conditions = ", ".join(wl.get("conditions", [])) if wl.get("conditions") else "Semua Kondisi"
            ram = f"Min {wl.get('min_ram_gb', 0)}GB" if wl.get("min_ram_gb", 0) > 0 else "Bebas"
            p = wl.get("max_price", 0)
            price_str = f"Maks Rp {p:,}".replace(",", ".") if p > 0 else "Bebas"

            lines.append(
                f"<b>{i}. {html.escape(wl.get('name', 'Target'))}</b> ({status_tag})\n"
                f"   • Brand: {brands} | RAM: {ram}\n"
                f"   • Storage: {storages} | Kondisi: {conditions}\n"
                f"   • Budget: <b>{price_str}</b>\n"
            )

        lines.append("💡 <i>Klik tombol di bawah untuk mengelola atau menambah incaran:</i>")
        text = "\n".join(lines)
        bot.send_message(chat_id, text, reply_markup=build_wishlist_dashboard_markup(wishlists))


    @bot.message_handler(commands=["tambah"])
    def cmd_tambah_wishlist(message):
        """Perintah shortcut untuk langsung menambah wishlist baru."""
        chat_id = str(message.chat.id)
        start_add_wishlist_wizard(chat_id)


    @bot.message_handler(commands=["status"])
    def cmd_status(message):
        cmd_wishlist_dashboard(message)


    @bot.message_handler(commands=["help"])
    def cmd_help(message):
        text = (
            "📖 <b>Daftar Perintah Bot Maujual:</b>\n\n"
            "• /wishlist - Buka Dashboard Multi-Wishlist (Kelola semua target incaran)\n"
            "• /tambah - Tambah target incaran HP baru dengan kriteria kustom\n"
            "• /status - Cek status monitoring & daftar target aktif\n"
            "• /help - Tampilkan panduan ini\n\n"
            "✨ <b>Fitur Utama:</b>\n"
            "• Mendukung banyak target incaran sekaligus dengan kriteria berbeda\n"
            "• Notifikasi otomatis memuat <b>Foto HP Asli</b> & <b>16 Spesifikasi Lengkap</b>\n"
            "• Langsung mengecek stok ready saat wishlist baru dibuat"
        )
        bot.send_message(message.chat.id, text)


    def start_add_wishlist_wizard(chat_id):
        """Memulai wizard penambahan wishlist baru: Langkah 1 input nama."""
        user_wizard_state[chat_id] = {
            "step": "waiting_name",
            "name": "",
            "brands": set(),
            "storages": set(),
            "conditions": set(),
            "min_ram_gb": 0,
            "max_price": 1000000
        }
        text = (
            "📝 <b>Langkah 1/6: Beri Nama Target Incaran Anda</b>\n\n"
            "Silakan ketik nama label untuk target ini langsung di chat.\n"
            "Contoh: <code>HP Gaming</code>, <code>Incaran iPhone</code>, atau <code>HP Cadangan</code>"
        )
        bot.send_message(chat_id, text)


    @bot.callback_query_handler(func=lambda call: True)
    def handle_callbacks(call):
        chat_id = str(call.message.chat.id)
        data = call.data

        # -------------------------------------------------------------
        # DASHBOARD & WISHLIST MANAGEMENT HANDLERS
        # -------------------------------------------------------------
        if data == "wl:new":
            bot.answer_callback_query(call.id)
            start_add_wishlist_wizard(chat_id)
            return

        elif data.startswith("wl:toggle:"):
            wl_id = data.split(":", 2)[2]
            prefs = load_preferences()
            for wl in prefs.get("wishlists", []):
                if wl["id"] == wl_id:
                    wl["is_active"] = not wl.get("is_active", True)
                    status_text = "Diaktifkan kembali" if wl["is_active"] else "Dijeda"
                    bot.answer_callback_query(call.id, f"Target '{wl['name']}' {status_text}")
                    break
            save_preferences(prefs)
            # Refresh dashboard view
            cmd_wishlist_dashboard(call.message)
            return

        elif data.startswith("wl:del_confirm:"):
            wl_id = data.split(":", 2)[2]
            prefs = load_preferences()
            wl = next((w for w in prefs.get("wishlists", []) if w["id"] == wl_id), None)
            if not wl:
                bot.answer_callback_query(call.id, "Target tidak ditemukan")
                return

            bot.answer_callback_query(call.id)
            markup = InlineKeyboardMarkup()
            markup.row(
                InlineKeyboardButton("❌ Batal", callback_data="wl:back"),
                InlineKeyboardButton("🗑️ Ya, Hapus", callback_data=f"wl:delete:{wl_id}")
            )
            bot.edit_message_text(
                chat_id=chat_id,
                message_id=call.message.message_id,
                text=f"⚠️ <b>Konfirmasi Hapus Target</b>\n\nApakah Anda yakin ingin menghapus target <b>'{html.escape(wl['name'])}'</b>?",
                reply_markup=markup
            )
            return

        elif data.startswith("wl:delete:"):
            wl_id = data.split(":", 2)[2]
            prefs = load_preferences()
            original_len = len(prefs.get("wishlists", []))
            prefs["wishlists"] = [w for w in prefs.get("wishlists", []) if w["id"] != wl_id]
            save_preferences(prefs)

            # Hapus juga riwayat sent_data untuk wishlist ini
            sent_data = load_sent_data()
            if wl_id in sent_data:
                del sent_data[wl_id]
                save_sent_data(sent_data)

            bot.answer_callback_query(call.id, "Target berhasil dihapus!")
            cmd_wishlist_dashboard(call.message)
            return

        elif data == "wl:back":
            bot.answer_callback_query(call.id)
            cmd_wishlist_dashboard(call.message)
            return

        elif data.startswith("wl:view:"):
            wl_id = data.split(":", 2)[2]
            prefs = load_preferences()
            wl = next((w for w in prefs.get("wishlists", []) if w["id"] == wl_id), None)
            if not wl:
                bot.answer_callback_query(call.id, "Target tidak ditemukan")
                return

            bot.answer_callback_query(call.id)
            status_tag = "🟢 Aktif" if wl.get("is_active", True) else "⏸️ Dijeda"
            brands = ", ".join(wl.get("brands", [])) if wl.get("brands") else "Semua Brand / Bebas"
            storages = ", ".join(wl.get("storages", [])) if wl.get("storages") else "Semua Ukuran / Bebas"
            conditions = ", ".join(wl.get("conditions", [])) if wl.get("conditions") else "Semua Kondisi / Bebas"
            ram = f"Minimal {wl.get('min_ram_gb', 0)} GB" if wl.get("min_ram_gb", 0) > 0 else "Bebas"
            p = wl.get("max_price", 0)
            price_str = f"Maksimal Rp {p:,}".replace(",", ".") if p > 0 else "Bebas / Tanpa Batas"

            text = (
                f"🎯 <b>DETAIL TARGET: {html.escape(wl['name'])}</b>\n\n"
                f"• <b>Status:</b> {status_tag}\n"
                f"• <b>Brand:</b> {brands}\n"
                f"• <b>Storage:</b> {storages}\n"
                f"• <b>Kondisi:</b> {conditions}\n"
                f"• <b>RAM:</b> {ram}\n"
                f"• <b>Batas Harga:</b> {price_str}\n"
                f"• <b>Dibuat:</b> {wl.get('created_at', '-')}\n"
            )
            markup = InlineKeyboardMarkup()
            markup.row(
                InlineKeyboardButton("🔙 Kembali ke Dashboard", callback_data="wl:back"),
                InlineKeyboardButton("🗑️ Hapus Target", callback_data=f"wl:del_confirm:{wl_id}")
            )
            bot.edit_message_text(
                chat_id=chat_id,
                message_id=call.message.message_id,
                text=text,
                reply_markup=markup
            )
            return

        # -------------------------------------------------------------
        # WIZARD HANDLERS (BRAND, STORAGE, COND, RAM, PRICE)
        # -------------------------------------------------------------
        state = user_wizard_state.get(chat_id)
        if not state:
            bot.answer_callback_query(call.id, "Sesi telah kedaluwarsa. Silakan ketik /wishlist.")
            return

        # --- STEP 2: BRAND HANDLERS ---
        if data.startswith("brand:toggle:"):
            brand_name = data.split(":", 2)[2]
            if brand_name in state["brands"]:
                state["brands"].remove(brand_name)
            else:
                state["brands"].add(brand_name)
            bot.edit_message_reply_markup(
                chat_id=chat_id,
                message_id=call.message.message_id,
                reply_markup=build_brand_markup(state["brands"])
            )
            bot.answer_callback_query(call.id)

        elif data == "brand:all":
            state["brands"] = set()
            state["step"] = "storage"
            bot.answer_callback_query(call.id, "Memilih Semua Brand")
            bot.edit_message_text(
                chat_id=chat_id,
                message_id=call.message.message_id,
                text=(
                    f"🎯 Target: <b>{html.escape(state['name'])}</b>\n"
                    "✅ Brand: <b>Semua Brand / Bebas</b>\n\n"
                    "<b>Langkah 3/6: Pilih Ukuran Storage (Penyimpanan)</b>\n"
                    "<i>(Bisa pilih beberapa sekaligus, lalu klik 'Selesai & Lanjut')</i>"
                ),
                reply_markup=build_storage_markup(set())
            )

        elif data == "brand:done":
            state["step"] = "storage"
            b_list = sorted(list(state["brands"]))
            b_text = ", ".join(b_list) if b_list else "Semua Brand / Bebas"
            bot.answer_callback_query(call.id)
            bot.edit_message_text(
                chat_id=chat_id,
                message_id=call.message.message_id,
                text=(
                    f"🎯 Target: <b>{html.escape(state['name'])}</b>\n"
                    f"✅ Brand Dipilih: <b>{b_text}</b>\n\n"
                    "<b>Langkah 3/6: Pilih Ukuran Storage (Penyimpanan)</b>\n"
                    "<i>(Bisa pilih beberapa sekaligus, lalu klik 'Selesai & Lanjut')</i>"
                ),
                reply_markup=build_storage_markup(set())
            )

        # --- STEP 3: STORAGE HANDLERS ---
        elif data.startswith("storage:toggle:"):
            storage_name = data.split(":", 2)[2]
            if storage_name in state["storages"]:
                state["storages"].remove(storage_name)
            else:
                state["storages"].add(storage_name)
            bot.edit_message_reply_markup(
                chat_id=chat_id,
                message_id=call.message.message_id,
                reply_markup=build_storage_markup(state["storages"])
            )
            bot.answer_callback_query(call.id)

        elif data == "storage:all":
            state["storages"] = set()
            state["step"] = "condition"
            bot.answer_callback_query(call.id, "Memilih Semua Ukuran")
            bot.edit_message_text(
                chat_id=chat_id,
                message_id=call.message.message_id,
                text=(
                    f"🎯 Target: <b>{html.escape(state['name'])}</b>\n"
                    "✅ Storage: <b>Semua Ukuran / Bebas</b>\n\n"
                    "<b>Langkah 4/6: Pilih Kondisi Unit HP</b>\n"
                    "<i>(Bisa pilih beberapa sekaligus, lalu klik 'Selesai & Lanjut')</i>"
                ),
                reply_markup=build_condition_markup(set())
            )

        elif data == "storage:done":
            state["step"] = "condition"
            s_list = sorted(list(state["storages"]))
            s_text = ", ".join(s_list) if s_list else "Semua Ukuran / Bebas"
            bot.answer_callback_query(call.id)
            bot.edit_message_text(
                chat_id=chat_id,
                message_id=call.message.message_id,
                text=(
                    f"🎯 Target: <b>{html.escape(state['name'])}</b>\n"
                    f"✅ Storage Dipilih: <b>{s_text}</b>\n\n"
                    "<b>Langkah 4/6: Pilih Kondisi Unit HP</b>\n"
                    "<i>(Bisa pilih beberapa sekaligus, lalu klik 'Selesai & Lanjut')</i>"
                ),
                reply_markup=build_condition_markup(set())
            )

        # --- STEP 4: CONDITION HANDLERS ---
        elif data.startswith("cond:toggle:"):
            cond_name = data.split(":", 2)[2]
            if cond_name in state["conditions"]:
                state["conditions"].remove(cond_name)
            else:
                state["conditions"].add(cond_name)
            bot.edit_message_reply_markup(
                chat_id=chat_id,
                message_id=call.message.message_id,
                reply_markup=build_condition_markup(state["conditions"])
            )
            bot.answer_callback_query(call.id)

        elif data == "cond:all":
            state["conditions"] = set()
            state["step"] = "ram"
            bot.answer_callback_query(call.id, "Memilih Semua Kondisi")
            bot.edit_message_text(
                chat_id=chat_id,
                message_id=call.message.message_id,
                text=(
                    f"🎯 Target: <b>{html.escape(state['name'])}</b>\n"
                    "✅ Kondisi: <b>Semua Kondisi / Bebas</b>\n\n"
                    "<b>Langkah 5/6: Pilih Kapasitas RAM Minimal</b>\n"
                    "<i>(Pilih batas minimal RAM yang Anda inginkan)</i>"
                ),
                reply_markup=build_ram_markup()
            )

        elif data == "cond:done":
            state["step"] = "ram"
            c_list = sorted(list(state["conditions"]))
            c_text = ", ".join(c_list) if c_list else "Semua Kondisi / Bebas"
            bot.answer_callback_query(call.id)
            bot.edit_message_text(
                chat_id=chat_id,
                message_id=call.message.message_id,
                text=(
                    f"🎯 Target: <b>{html.escape(state['name'])}</b>\n"
                    f"✅ Kondisi Dipilih: <b>{c_text}</b>\n\n"
                    "<b>Langkah 5/6: Pilih Kapasitas RAM Minimal</b>\n"
                    "<i>(Pilih batas minimal RAM yang Anda inginkan)</i>"
                ),
                reply_markup=build_ram_markup()
            )

        # --- STEP 5: RAM HANDLERS ---
        elif data.startswith("ram:"):
            ram_val = int(data.split(":")[1])
            state["min_ram_gb"] = ram_val
            state["step"] = "price"
            ram_text = f"Minimal {ram_val} GB" if ram_val > 0 else "Bebas / Berapa Saja"
            bot.answer_callback_query(call.id)
            bot.edit_message_text(
                chat_id=chat_id,
                message_id=call.message.message_id,
                text=(
                    f"🎯 Target: <b>{html.escape(state['name'])}</b>\n"
                    f"✅ RAM: <b>{ram_text}</b>\n\n"
                    "<b>Langkah 6/6: Pilih Batas Harga Maksimal</b>\n"
                    "<i>Pilih nominal preset atau klik 'Ketik Manual Bebas'</i>"
                ),
                reply_markup=build_price_markup()
            )

        # --- STEP 6: PRICE HANDLERS ---
        elif data.startswith("price:"):
            price_code = data.split(":")[1]
            if price_code == "manual":
                state["step"] = "waiting_price_input"
                bot.answer_callback_query(call.id)
                bot.edit_message_text(
                    chat_id=chat_id,
                    message_id=call.message.message_id,
                    text=(
                        f"🎯 Target: <b>{html.escape(state['name'])}</b>\n\n"
                        "✏️ <b>Ketik Batas Harga Maksimal</b>\n\n"
                        "Silakan ketik angka batas harga maksimal yang Anda inginkan langsung di chat.\n"
                        "Contoh: <code>1250000</code> atau <code>1.250.000</code>"
                    )
                )
            else:
                price_val = int(price_code)
                state["max_price"] = price_val
                finish_add_wishlist_wizard(chat_id, state)
                bot.answer_callback_query(call.id, "Target Incaran Tersimpan!")


    @bot.message_handler(func=lambda msg: True)
    def handle_text_messages(message):
        """Menangani input teks (nama label target & input harga manual)."""
        chat_id = str(message.chat.id)
        state = user_wizard_state.get(chat_id)

        if not state:
            return

        step = state.get("step")

        # Step 1: Input nama target
        if step == "waiting_name":
            target_name = message.text.strip()
            if not target_name:
                bot.reply_to(message, "⚠️ Nama target tidak boleh kosong. Silakan ketik nama target incaran Anda:")
                return

            state["name"] = target_name
            state["step"] = "brand"

            text = (
                f"🎯 <b>Target: {html.escape(target_name)}</b>\n\n"
                "<b>Langkah 2/6: Pilih Brand HP</b>\n"
                "<i>(Bisa pilih lebih dari satu dengan menekan tombol, lalu klik 'Selesai & Lanjut')</i>"
            )
            bot.send_message(chat_id, text, reply_markup=build_brand_markup(set()))

        # Step 6: Input harga manual
        elif step == "waiting_price_input":
            raw_text = message.text
            digits = re.sub(r"[^\d]", "", raw_text)
            if digits and int(digits) > 0:
                state["max_price"] = int(digits)
                finish_add_wishlist_wizard(chat_id, state)
            else:
                bot.reply_to(
                    message,
                    "⚠️ Format angka tidak valid. Silakan ketik nominal angka saja, contoh: <code>1250000</code>"
                )


def finish_add_wishlist_wizard(chat_id, state):
    """Menyimpan wishlist baru ke user_preferences.json dan memulai scan awal instan."""
    prefs = load_preferences()
    new_wl_id = f"wl_{int(time.time())}"

    new_wl = {
        "id": new_wl_id,
        "name": state.get("name", f"Target {len(prefs.get('wishlists', [])) + 1}"),
        "is_active": True,
        "brands": sorted(list(state["brands"])),
        "storages": sorted(list(state["storages"])),
        "conditions": sorted(list(state["conditions"])),
        "min_ram_gb": state.get("min_ram_gb", 0),
        "max_price": state.get("max_price", 1000000),
        "created_at": datetime.now().strftime("%Y-%m-%d %H:%M:%S")
    }

    prefs.setdefault("wishlists", []).append(new_wl)
    save_preferences(prefs)
    state["step"] = "completed"

    brands_str = ", ".join(new_wl["brands"]) if new_wl["brands"] else "Semua Brand / Bebas"
    storages_str = ", ".join(new_wl["storages"]) if new_wl["storages"] else "Semua Ukuran / Bebas"
    conditions_str = ", ".join(new_wl["conditions"]) if new_wl["conditions"] else "Semua Kondisi / Bebas"
    ram_str = f"Minimal {new_wl['min_ram_gb']} GB" if new_wl["min_ram_gb"] > 0 else "Bebas"
    price_str = f"Maksimal Rp {new_wl['max_price']:,}".replace(",", ".") if new_wl["max_price"] > 0 else "Bebas / Tanpa Batas"

    summary_text = (
        f"🎉 <b>TARGET INCATAN BARU BERHASIL DISIMPAN!</b>\n\n"
        f"🏷️ <b>Nama Target:</b> {html.escape(new_wl['name'])}\n"
        f"• <b>Brand:</b> {brands_str}\n"
        f"• <b>Storage:</b> {storages_str}\n"
        f"• <b>Kondisi:</b> {conditions_str}\n"
        f"• <b>RAM:</b> {ram_str}\n"
        f"• <b>Batas Harga:</b> {price_str}\n\n"
        "🔎 <b>Memulai Scan Awal...</b>\n"
        "Bot sedang memeriksa seluruh katalog Maujual.com untuk mencari HP ready yang cocok dengan target ini. Harap tunggu sebentar..."
    )
    bot.send_message(chat_id, summary_text)

    # Jalankan scan awal seketika di background thread khusus wishlist baru ini
    threading.Thread(target=scan_single_wishlist, args=(new_wl,), daemon=True).start()


# ==============================================================================
# PRODUCT DETAILS & SPECIFICATIONS SCRAPER
# ==============================================================================
def get_product_details(product_url):
    """
    Mengambil data detail produk (Spesifikasi Lengkap, Foto HP, dan Varian Ready)
    langsung dari endpoint data Shopify (.js).
    Mengembalikan (specs_dict, raw_ready_variants, image_url).
    """
    try:
        js_url = product_url.rstrip("/") + ".js"
        res = requests.get(js_url, headers=HEADERS, timeout=12)
        if res.status_code != 200:
            return {}, [], ""

        data = res.json()

        # 1. Ambil URL Gambar Produk (Featured Image)
        featured_img = data.get("featured_image", "")
        if not featured_img and data.get("images"):
            featured_img = data["images"][0]

        if featured_img:
            if featured_img.startswith("//"):
                image_url = "https:" + featured_img
            elif featured_img.startswith("/"):
                image_url = urljoin("https://shop.maujual.com", featured_img)
            else:
                image_url = featured_img
        else:
            image_url = ""

        # 2. Parse Seluruh Spesifikasi dari Deskripsi Produk
        desc = data.get("description", "")
        soup = BeautifulSoup(desc, "html.parser")
        lines = [l.strip() for l in soup.get_text("\n").splitlines() if l.strip()]

        raw_specs = {}
        i = 0
        while i < len(lines):
            line = lines[i]
            if ":" in line and not line.endswith(":"):
                parts = line.split(":", 1)
                raw_specs[parts[0].strip().lower()] = parts[1].strip()
            elif line.endswith(":") and i + 1 < len(lines):
                key = line[:-1].strip().lower()
                val = lines[i + 1]
                if not val.endswith(":"):
                    raw_specs[key] = val
                    i += 1
            i += 1

        # Bangun dictionary spesifikasi terstruktur
        specs = {
            "chipset": raw_specs.get("chip options") or raw_specs.get("chipset") or raw_specs.get("processor") or "-",
            "ram": raw_specs.get("memory") or raw_specs.get("ram") or "-",
            "os": raw_specs.get("os") or "-",
            "battery": raw_specs.get("battery type") or raw_specs.get("battery") or "-",
            "charging": raw_specs.get("charging") or "-",
            "display_size": raw_specs.get("display size") or raw_specs.get("display") or "-",
            "display_type": raw_specs.get("display type") or "-",
            "resolution": raw_specs.get("resolution") or "-",
            "main_camera": raw_specs.get("main camera") or raw_specs.get("camera") or "-",
            "selfie_camera": raw_specs.get("selfie camera definition") or raw_specs.get("selfie camera") or "-",
            "nfc": raw_specs.get("nfc") or "-",
            "usb": raw_specs.get("usb") or "-",
            "sim": raw_specs.get("sim") or "-",
            "weight": raw_specs.get("weight") or "-",
            "dimension": raw_specs.get("dimension") or "-",
            "storage_type": raw_specs.get("storage description") or "-"
        }

        # 3. Ambil semua varian yang available (ready stock)
        raw_ready_variants = []
        for v in data.get("variants", []):
            if v.get("available"):
                p_cents = v.get("price", 0)
                raw_ready_variants.append({
                    "title": v.get("title", ""),
                    "price_rp": p_cents // 100,
                    "price_str": f"Rp {p_cents // 100:,}".replace(",", ".")
                })

        return specs, raw_ready_variants, image_url
    except Exception as e:
        logger.warning(f"Gagal mengambil detail spesifikasi produk ({product_url}): {e}")
        return {}, [], ""


# ==============================================================================
# FILTER MATCHING ENGINE
# ==============================================================================
def match_product_filters(product_title, product_price_str, specs, raw_ready_variants, filter_criteria):
    """
    Mengecek apakah produk memenuhi SEMUA filter kriteria suatu wishlist.
    Mengembalikan (is_match, matched_ready_variants).
    """
    # 1. Filter Brand
    selected_brands = filter_criteria.get("brands", [])
    if selected_brands:
        title_lower = product_title.lower()
        if not any(b.lower() in title_lower for b in selected_brands):
            return False, []

    # 2. Filter RAM
    min_ram = filter_criteria.get("min_ram_gb", 0)
    ram = specs.get("ram", "-")
    if min_ram > 0 and ram != "-":
        ram_numbers = [int(n) for n in re.findall(r"(\d+)\s*gb", ram, re.I)]
        if ram_numbers:
            if max(ram_numbers) < min_ram:
                return False, []

    # 3. Filter Varian Ready (Storage, Kondisi, Harga Maksimal)
    selected_storages = [s.lower() for s in filter_criteria.get("storages", [])]
    selected_conditions = [c.lower() for c in filter_criteria.get("conditions", [])]
    max_price = filter_criteria.get("max_price", 0)

    matched_variants = []
    for var in raw_ready_variants:
        v_title = var["title"]
        v_title_lower = v_title.lower()
        v_price = var["price_rp"]

        # Cek storage
        if selected_storages:
            if not any(st in v_title_lower for st in selected_storages):
                continue

        # Cek kondisi
        if selected_conditions:
            if not any(co in v_title_lower for co in selected_conditions):
                continue

        # Cek harga
        if max_price > 0 and v_price > max_price:
            continue

        matched_variants.append(f"{v_title} ({var['price_str']})")

    # Jika produk memiliki varian terdaftar tapi tidak ada yang cocok dengan kriteria varian
    if raw_ready_variants and not matched_variants:
        return False, []

    return True, matched_variants


# ==============================================================================
# TELEGRAM NOTIFICATION SENDER
# ==============================================================================
def send_telegram_notification(title, price, product_url, specs, matched_variants, image_url, target_label="", is_initial_scan=False):
    """
    Mengirim pesan notifikasi lengkap + Foto HP ke Telegram.
    Mencantumkan label nama target wishlist yang cocok.
    """
    if not TELEGRAM_TOKEN or not CHAT_ID:
        logger.warning("TELEGRAM_TOKEN atau CHAT_ID belum disetel.")
        return False

    safe_title = html.escape(title)
    safe_price = html.escape(price)
    safe_url = html.escape(product_url)
    target_header = f"🎯 <b>TARGET: {html.escape(target_label)}</b>\n" if target_label else ""
    initial_tag = "⚡ <i>[Hasil Scan Awal Wishlist Baru]</i>\n" if is_initial_scan else ""

    lines = [
        f"{target_header}{initial_tag}🚨 <b>ADA STOK COCOK DITEMUKAN!</b> 🚨",
        f"📱 <b>{safe_title}</b>",
        f"💰 <b>{safe_price}</b>",
        "━━━━━━━━━━━━━━━━━━━━━",
        "⚙️ <b>SPESIFIKASI LENGKAP:</b>",
    ]

    # Chipset & RAM
    if specs.get("chipset") and specs["chipset"] != "-":
        lines.append(f"• <b>Chipset:</b> {html.escape(specs['chipset'])}")
    if specs.get("ram") and specs["ram"] != "-":
        lines.append(f"• <b>RAM:</b> {html.escape(specs['ram'])}")
    if specs.get("os") and specs["os"] != "-":
        lines.append(f"• <b>OS:</b> {html.escape(specs['os'])}")

    # Baterai & Charging
    bat = specs.get("battery", "-")
    chg = specs.get("charging", "-")
    if bat != "-" or chg != "-":
        bat_str = html.escape(bat) if bat != "-" else ""
        if chg != "-":
            bat_str += f" ({html.escape(chg)})" if bat_str else html.escape(chg)
        lines.append(f"• <b>Baterai:</b> {bat_str}")

    # Layar
    disp = specs.get("display_size", "-")
    dtype = specs.get("display_type", "-")
    res = specs.get("resolution", "-")
    if disp != "-" or dtype != "-" or res != "-":
        disp_parts = [p for p in [disp, dtype] if p != "-"]
        disp_str = " ".join(disp_parts)
        if res != "-":
            disp_str += f" ({res})" if disp_str else res
        lines.append(f"• <b>Layar:</b> {html.escape(disp_str)}")

    # Kamera
    cam = specs.get("main_camera", "-")
    selfie = specs.get("selfie_camera", "-")
    if cam != "-":
        lines.append(f"• <b>Kamera Utama:</b> {html.escape(cam)}")
    if selfie != "-":
        lines.append(f"• <b>Kamera Selfie:</b> {html.escape(selfie)}")

    # Konektivitas & Fitur
    feat_parts = []
    if specs.get("nfc") and specs["nfc"] != "-":
        feat_parts.append(f"NFC: {specs['nfc']}")
    if specs.get("usb") and specs["usb"] != "-":
        feat_parts.append(f"USB: {specs['usb']}")
    if specs.get("sim") and specs["sim"] != "-":
        feat_parts.append(f"SIM: {specs['sim']}")
    if feat_parts:
        lines.append(f"• <b>Konektivitas:</b> {html.escape(' | '.join(feat_parts))}")

    # Fisik
    body_parts = []
    if specs.get("weight") and specs["weight"] != "-":
        body_parts.append(f"Berat: {specs['weight']}")
    if specs.get("dimension") and specs["dimension"] != "-":
        body_parts.append(f"Dimensi: {specs['dimension']}")
    if body_parts:
        lines.append(f"• <b>Fisik:</b> {html.escape(' | '.join(body_parts))}")

    lines.append("━━━━━━━━━━━━━━━━━━━━━")

    # Varian Ready
    if matched_variants:
        lines.append("📦 <b>VARIAN READY COCOK:</b>")
        for v in matched_variants:
            lines.append(f"• {html.escape(v)}")
        lines.append("")

    lines.append(f"🔗 <a href='{safe_url}'>Lihat Produk di Maujual</a>")

    full_text = "\n".join(lines)

    # 1. Coba kirim Foto HP terlebih dahulu jika URL gambar tersedia
    if image_url:
        if len(full_text) <= 1024:
            try:
                photo_api = f"https://api.telegram.org/bot{TELEGRAM_TOKEN}/sendPhoto"
                payload = {
                    "chat_id": str(CHAT_ID),
                    "photo": image_url,
                    "caption": full_text,
                    "parse_mode": "HTML"
                }
                resp = requests.post(photo_api, json=payload, timeout=15)
                if resp.status_code == 200:
                    logger.info(f"✅ Notifikasi Foto & Spek terkirim untuk: {title} ({target_label})")
                    return True
                else:
                    logger.warning(f"sendPhoto gabungan gagal ({resp.status_code}): {resp.text}")
            except Exception as e:
                logger.warning(f"Error sendPhoto: {e}")

        # Jika caption > 1024 karakter, kirim foto dengan caption ringkas lalu kirim teks spek
        try:
            photo_api = f"https://api.telegram.org/bot{TELEGRAM_TOKEN}/sendPhoto"
            short_caption = (
                f"{target_header}{initial_tag}"
                f"🚨 <b>ADA STOK COCOK DITEMUKAN!</b> 🚨\n"
                f"📱 <b>{safe_title}</b>\n"
                f"💰 <b>{safe_price}</b>"
            )
            requests.post(photo_api, json={
                "chat_id": str(CHAT_ID),
                "photo": image_url,
                "caption": short_caption,
                "parse_mode": "HTML"
            }, timeout=15)
        except Exception as e:
            logger.warning(f"Gagal kirim foto terpisah: {e}")

    # 2. Kirim pesan teks detail spesifikasi lengkap
    try:
        msg_api = f"https://api.telegram.org/bot{TELEGRAM_TOKEN}/sendMessage"
        payload = {
            "chat_id": str(CHAT_ID),
            "text": full_text,
            "parse_mode": "HTML",
            "disable_web_page_preview": True
        }
        resp = requests.post(msg_api, json=payload, timeout=15)
        if resp.status_code == 200:
            logger.info(f"✅ Pesan detail spesifikasi terkirim untuk: {title} ({target_label})")
            return True
        else:
            logger.error(f"❌ Telegram API Error ({resp.status_code}): {resp.text}")
            return False
    except requests.RequestException as e:
        logger.error(f"❌ Gagal koneksi ke Telegram API: {e}")
        return False


# ==============================================================================
# WEB SCRAPING FUNCTION
# ==============================================================================
def scrape_maujual(max_price=0):
    """Scrape halaman katalog Maujual dengan filter harga dinamis."""
    if max_price > 0:
        target_url = (
            f"https://shop.maujual.com/collections/hp?"
            f"sort_by=created-descending&filter.v.price.gte=1&filter.v.price.lte={max_price}"
        )
    else:
        target_url = "https://shop.maujual.com/collections/hp?sort_by=created-descending"

    logger.info(f"Melakukan request katalog ke: {target_url}")
    try:
        response = requests.get(target_url, headers=HEADERS, timeout=20)
        response.raise_for_status()
    except requests.RequestException as e:
        logger.error(f"Gagal mengambil halaman web: {e}")
        return []

    products = []
    try:
        soup = BeautifulSoup(response.text, "html.parser")
        cards = soup.select("li.product-card")
        if not cards:
            cards = soup.select("[class*='product-card']")

        for card in cards:
            try:
                card_classes = card.get("class", [])
                if "placeholder-product" in card_classes:
                    continue

                title = ""
                product_url = ""

                title_elem = card.find("h3")
                if title_elem:
                    a_tag = title_elem.find("a")
                    if a_tag:
                        title = a_tag.get_text(strip=True)
                        raw_href = a_tag.get("href", "")
                        if raw_href:
                            product_url = urljoin("https://shop.maujual.com", raw_href).split("?")[0]
                    else:
                        title = title_elem.get_text(strip=True)

                if not product_url:
                    fig_a = card.select_one("figure a")
                    if fig_a and fig_a.get("href"):
                        raw_href = fig_a.get("href")
                        if "/products/" in raw_href:
                            product_url = urljoin("https://shop.maujual.com", raw_href).split("?")[0]
                            if not title and fig_a.get("aria-label"):
                                title = fig_a.get("aria-label")

                if not product_url or not title or title.lower() == "product title":
                    continue

                price = "Harga tidak tersedia"
                price_elem = card.select_one(".price, [class*='price']")
                if price_elem:
                    price = price_elem.get_text(" ", strip=True)

                products.append({
                    "title": title,
                    "price": price,
                    "url": product_url
                })
            except Exception as card_err:
                logger.warning(f"Gagal mem-parsing elemen produk: {card_err}")
                continue

    except Exception as parse_err:
        logger.error(f"Gagal mem-parsing HTML katalog: {parse_err}")
        return []

    logger.info(f"Ditemukan {len(products)} produk aktif di halaman katalog.")
    return products


# ==============================================================================
# SCAN SINGLE WISHLIST (SCAN AWAL INSTAN)
# ==============================================================================
def scan_single_wishlist(wishlist):
    """
    Melakukan scan awal seketika begitu sebuah wishlist baru dibuat.
    Mengirimkan semua HP yang saat ini ready di Maujual yang cocok dengan kriteria wishlist tersebut.
    """
    wl_id = wishlist["id"]
    wl_name = wishlist.get("name", "Target")
    max_p = wishlist.get("max_price", 0)

    logger.info(f"Memulai scan awal instan untuk target baru: '{wl_name}' ({wl_id})")
    products = scrape_maujual(max_price=max_p)

    sent_data = load_sent_data()
    sent_set = sent_data.get(wl_id, set())

    found_count = 0
    for item in products:
        p_url = item["url"]
        p_title = item["title"]
        p_price = item["price"]

        if p_url in sent_set:
            continue

        specs, raw_ready_variants, image_url = get_product_details(p_url)
        is_match, matched_variants = match_product_filters(
            p_title, p_price, specs, raw_ready_variants, wishlist
        )

        sent_set.add(p_url)

        if is_match:
            found_count += 1
            logger.info(f"[SCAN AWAL COCOK] {p_title} ({p_price}) -> Target '{wl_name}'")
            if TELEGRAM_TOKEN and CHAT_ID:
                send_telegram_notification(
                    p_title, p_price, p_url, specs, matched_variants, image_url,
                    target_label=wl_name, is_initial_scan=True
                )
            time.sleep(1)

    sent_data[wl_id] = sent_set
    save_sent_data(sent_data)

    if found_count == 0:
        logger.info(f"Scan awal selesai: tidak ada stok ready yang cocok saat ini untuk '{wl_name}'.")
        if TELEGRAM_TOKEN and CHAT_ID:
            try:
                bot.send_message(
                    CHAT_ID,
                    f"🔍 <b>Laporan Scan Awal untuk Target:</b> <code>{html.escape(wl_name)}</code>\n\n"
                    "Saat ini belum ada stok ready di Maujual yang cocok dengan kriteria ini.\n"
                    "Bot akan terus memantau otomatis setiap 15 menit dan memberi tahu Anda begitu stok masuk! 🚀"
                )
            except Exception as e:
                logger.warning(f"Gagal mengirim pesan laporan scan awal: {e}")
    else:
        logger.info(f"Scan awal selesai: {found_count} produk cocok terkirim untuk '{wl_name}'.")


# ==============================================================================
# MAIN JOB RUNNER (MULTI-WISHLIST SCHEDULER)
# ==============================================================================
def job_check_stok():
    """Tugas berkala: scrape produk, cek riwayat per-wishlist, dan kirim notifikasi terpisah."""
    logger.info("=== [MULAI PENGECEKAN STOK BERKALA] ===")

    prefs = load_preferences()
    wishlists = prefs.get("wishlists", [])
    active_wishlists = [w for w in wishlists if w.get("is_active", True)]

    if not active_wishlists:
        logger.info("Tidak ada wishlist aktif saat ini. Pengecekan stok dilewati.")
        logger.info("=== [PENGECEKAN SELESAI] ===\n")
        return

    # Tentukan query harga maksimal tertinggi di antara semua wishlist aktif
    highest_max_price = 0
    for w in active_wishlists:
        p = w.get("max_price", 0)
        if p == 0:
            highest_max_price = 0
            break
        if p > highest_max_price:
            highest_max_price = p

    products = scrape_maujual(max_price=highest_max_price)
    if not products:
        logger.info("Tidak ada data produk yang didapat pada iterasi ini.")
        logger.info("=== [PENGECEKAN SELESAI] ===\n")
        return

    sent_data = load_sent_data()
    new_notified = 0

    for item in products:
        p_url = item["url"]
        p_title = item["title"]
        p_price = item["price"]

        # Filter wishlist mana saja yang belum pernah memproses URL ini
        candidate_wishlists = [
            w for w in active_wishlists
            if p_url not in sent_data.get(w["id"], set())
        ]

        if not candidate_wishlists:
            continue

        # Ambil spesifikasi detail produk (sekali per produk untuk efisiensi)
        specs, raw_ready_variants, image_url = get_product_details(p_url)

        # Evaluasi kecocokan untuk setiap candidate wishlist secara independen
        for wl in candidate_wishlists:
            wl_id = wl["id"]
            wl_name = wl.get("name", "Target")

            is_match, matched_variants = match_product_filters(
                p_title, p_price, specs, raw_ready_variants, wl
            )

            # Tandai produk sudah dievaluasi untuk wishlist ini agar tidak berulang
            if wl_id not in sent_data:
                sent_data[wl_id] = set()
            sent_data[wl_id].add(p_url)

            if is_match:
                new_notified += 1
                logger.info(f"[PRODUK COCOK] {p_title} ({p_price}) -> Target '{wl_name}'")
                if TELEGRAM_TOKEN and CHAT_ID:
                    send_telegram_notification(
                        p_title, p_price, p_url, specs, matched_variants, image_url,
                        target_label=wl_name
                    )
                time.sleep(1)

        # Simpan database per-wishlist
        save_sent_data(sent_data)

    logger.info(f"Pengecekan selesai. Notifikasi baru terkirim: {new_notified}")
    logger.info("=== [PENGECEKAN SELESAI] ===\n")


# ==============================================================================
# ENTRY POINT
# ==============================================================================
def start_scheduler_loop():
    """Menjalankan background scheduler di thread terpisah."""
    schedule.every(INTERVAL_MENIT).minutes.do(job_check_stok)
    logger.info(f"Background scheduler aktif setiap {INTERVAL_MENIT} menit.")
    while True:
        schedule.run_pending()
        time.sleep(1)


def start_health_check_server():
    """Menjalankan dummy HTTP server ringan untuk health check platform cloud (seperti Render.com)."""
    port = int(os.getenv("PORT", "10000"))

    class HealthHandler(http.server.SimpleHTTPRequestHandler):
        def do_GET(self):
            self.send_response(200)
            self.send_header("Content-type", "text/plain; charset=utf-8")
            self.end_headers()
            self.wfile.write(b"Maujual Telegram Bot is Running 24/7!")

        def log_message(self, format, *args):
            pass

    try:
        socketserver.TCPServer.allow_reuse_address = True
        with socketserver.TCPServer(("", port), HealthHandler) as httpd:
            logger.info(f"Health-check server aktif pada port {port} (Render.com ready).")
            httpd.serve_forever()
    except Exception as e:
        logger.warning(f"Tidak dapat memulai health-check server di port {port}: {e}")


def main():
    print("=" * 65)
    print("       MAUJUAL.COM HP SCRAPER & MULTI-WISHLIST BOT")
    print(f"       Jadwal Scheduler: Setiap {INTERVAL_MENIT} menit")
    print("=" * 65)

    # Mode 1: Sekali jalan (untuk GitHub Actions / external cron)
    if "--once" in sys.argv or os.getenv("RUN_ONCE") == "1":
        logger.info("Mode --once terdeteksi. Menjalankan satu kali pengecekan.")
        job_check_stok()
        logger.info("Mode --once selesai dijalankan. Keluar.")
        return

    # Mode 2: Bot Interaktif 24/7 (Local PC / Termux / Render Cloud)
    if not bot:
        logger.error("TELEGRAM_TOKEN tidak ditemukan. Bot tidak dapat dijalankan.")
        return

    # Aktifkan health-check web server jika berjalan di Render / cloud
    if os.getenv("PORT") or os.getenv("RENDER"):
        web_thread = threading.Thread(target=start_health_check_server, daemon=True)
        web_thread.start()

    # Mulai thread background scheduler
    sched_thread = threading.Thread(target=start_scheduler_loop, daemon=True)
    sched_thread.start()

    logger.info("Bot Telegram siap! Silakan buka Telegram Anda dan ketik /wishlist.")
    print("\n👉 Buka Telegram dan kirim perintah: /wishlist")
    print("👉 Tekan Ctrl+C di terminal ini jika ingin menghentikan bot.\n")

    try:
        bot.infinity_polling(timeout=20, long_polling_timeout=20)
    except KeyboardInterrupt:
        logger.info("Bot dihentikan oleh pengguna (Ctrl+C). Sampai jumpa!")


if __name__ == "__main__":
    main()
