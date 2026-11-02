import asyncio, os, json, random, time
from dotenv import load_dotenv
from aiohttp import web
from telethon import TelegramClient
from telegram.ext import Application, CommandHandler, CallbackQueryHandler, ContextTypes
from telegram.constants import ParseMode
from telegram import InlineKeyboardButton, InlineKeyboardMarkup
import aiohttp as aioclient

load_dotenv()
API_ID = int(os.getenv("API_ID"))
API_HASH = os.getenv("API_HASH")
BOT_TOKEN = os.getenv("BOT_TOKEN")
OWNER_ID = 6288011144
PORT = 8080

FOUND_FILE = "found_v2.json"
WATCH_FILE = "watch_v2.json"

tg_client = None
http_session = None
auto_on = False
check_counter = 0
found_set = set()
watch_set = set()

MIN_DELAY = 1.5
MAX_DELAY = 3.5
BATCH_SIZE = 5
BIG_PAUSE = 10

def load_data():
    global found_set, watch_set
    if os.path.exists(FOUND_FILE):
        with open(FOUND_FILE) as f:
            found_set = set(json.load(f))
    default_watch = ["admin", "crypto", "ton", "btc", "eth"]
    if os.path.exists(WATCH_FILE):
        with open(WATCH_FILE) as f:
            loaded = json.load(f)
            watch_set = set(loaded) if loaded else set(default_watch)
    else:
        watch_set = set(default_watch)
        save_watch()

def save_found():
    with open(FOUND_FILE, "w") as f:
        json.dump(list(found_set), f)

def save_watch():
    with open(WATCH_FILE, "w") as f:
        json.dump(list(watch_set), f)

def gen_name():
    c = list("bcdfghjklmnprstvwz")
    v = ["a", "e", "i", "o", "u"]
    l = random.randint(5, 7)
    n = ""
    for i in range(l):
        n += random.choice(c) if i % 2 == 0 else random.choice(v)
    return n.lower()

async def init_http():
    global http_session
    if not http_session:
        headers = {"User-Agent": "Mozilla/5.0", "Cache-Control": "no-cache"}
        http_session = aioclient.ClientSession(headers=headers, timeout=aioclient.ClientTimeout(total=3))

async def check_free_http(u):
    global http_session
    if not http_session:
        await init_http()
    try:
        async with http_session.head(f"https://t.me/{u}", allow_redirects=False) as r:
            return r.status == 404
    except:
        return False

async def verify_telethon(u):
    global tg_client
    if not tg_client or not tg_client.is_connected():
        return False
    try:
        await tg_client.get_entity(u)
        return False
    except ValueError:
        return True
    except:
        return False

async def hunter_loop(app_bot):
    global auto_on, check_counter, found_set
    while True:
        if not auto_on:
            await asyncio.sleep(2)
            continue
        batch = 0
        while batch < BATCH_SIZE and auto_on:
            u = gen_name()
            if u in found_set:
                continue
            check_counter += 1
            batch += 1
            is_free = await check_free_http(u)
            if is_free:
                verified = await verify_telethon(u)
                if verified:
                    found_set.add(u)
                    save_found()
                    try:
                        await app_bot.bot.send_message(OWNER_ID, f"💎 NEW FIND:\n@{u}\nTotal: {len(found_set)}")
                    except:
                        pass
            await asyncio.sleep(random.uniform(MIN_DELAY, MAX_DELAY))
        if auto_on:
            print(f"Batch Done. Checks: {check_counter}")
            await asyncio.sleep(BIG_PAUSE)

async def start(update, context):
    keyboard = [
        [InlineKeyboardButton("🚀 ЗАПУСТИТЬ ПОИСК", callback_data="hunt_on")],
        [InlineKeyboardButton("🛑 ОСТАНОВИТЬ", callback_data="hunt_off")],
        [InlineKeyboardButton("👁️ VIP МОНИТОР", callback_data="vip_menu")],
        [InlineKeyboardButton("📊 СТАТИСТИКА", callback_data="stats")]
    ]
    markup = InlineKeyboardMarkup(keyboard)
    msg = "<b>✨ USERNAME HUNTER PRO</b>\n\n🔍 Умный поиск редких никнеймов\n⚡ Быстро и безопасно\n💎 Находки приходят в личку\n\nВыбери действие:"
    await update.message.reply_text(msg, parse_mode=ParseMode.HTML, reply_markup=markup)

async def callback_handler(update, context):
    global auto_on
    query = update.callback_query
    await query.answer()
    data = query.data
    if data == "hunt_on":
        auto_on = True
        await query.edit_message_text("🚀 <b>ПОИСК ЗАПУЩЕН!</b>\n\nСмотри логи в Termux.\nНаходки будут приходить сюда.", parse_mode=ParseMode.HTML)
    elif data == "hunt_off":
        auto_on = False
        await query.edit_message_text("🛑 <b>ПОИСК ОСТАНОВЛЕН</b>", parse_mode=ParseMode.HTML)
    elif data == "vip_menu":
        vip_list = "\n".join([f"• @{n}" for n in list(watch_set)[:10]])
        await query.edit_message_text(f"👁️ <b>VIP МОНИТОР</b>\n\n{vip_list}", parse_mode=ParseMode.HTML)
    elif data == "stats":
        status = "АКТИВЕН" if auto_on else "ПАУЗА"
        await query.edit_message_text(f"📊 <b>СТАТИСТИКА</b>\n\n✅ Проверено: {check_counter}\n💎 Найдено: {len(found_set)}\n🟢 Статус: {status}", parse_mode=ParseMode.HTML)

async def main():
    global tg_client
    tg_client = TelegramClient('session_hunter', API_ID, API_HASH)
    await tg_client.start(bot_token=BOT_TOKEN)
    load_data()
    app_bot = Application.builder().token(BOT_TOKEN).build()
    app_bot.add_handler(CommandHandler("start", start))
    app_bot.add_handler(CallbackQueryHandler(callback_handler))
    await app_bot.initialize()
    await app_bot.start()
    await app_bot.updater.start_polling()
    print("SYSTEM READY. Open Telegram and click /start")
    await asyncio.gather(hunter_loop(app_bot))

if __name__ == "__main__":
    try:
        asyncio.run(main())
    except KeyboardInterrupt:
        print("\nShutting down...")
