import asyncio, os, json, random, time
from dotenv import load_dotenv
from aiohttp import web
from telethon import TelegramClient
from telegram.ext import Application, CommandHandler, ContextTypes
from telegram.constants import ParseMode
from telegram import InlineKeyboardButton, InlineKeyboardMarkup
import aiohttp as aioclient # Alias for HTTP requests inside bot logic

# ═══════════ CONFIG ═══════════
load_dotenv()
API_ID = int(os.getenv("API_ID"))
API_HASH = os.getenv("API_HASH")
BOT_TOKEN = os.getenv("BOT_TOKEN")
OWNER_ID = 6288011144
PORT = 8080

# Files
FOUND_FILE = "found_v2.json"
WATCH_FILE = "watch_v2.json"

# State
tg_client = None
http_session = None
auto_on = False
check_counter = 0
found_set = set()
watch_set = set()

# Security Delays
MIN_DELAY = 1.5
MAX_DELAY = 3.5
BATCH_SIZE = 5
BIG_PAUSE = 10

# ═══════════ DATA UTILS ═══════════
def load_data():
    global found_set, watch_set
    if os.path.exists(FOUND_FILE):
        with open(FOUND_FILE) as f: found_set = set(json.load(f))
    
    default_watch = ["admin", "crypto", "ton", "btc", "eth"]
    if os.path.exists(WATCH_FILE):
        with open(WATCH_FILE) as f: 
            loaded = json.load(f)
            watch_set = set(loaded) if loaded else set(default_watch)
    else:
        watch_set = set(default_watch)
        save_watch()

def save_found():
    with open(FOUND_FILE, "w") as f: json.dump(list(found_set), f)

def save_watch():
    with open(WATCH_FILE, "w") as f: json.dump(list(watch_set), f)

# ═══════════ GENERATOR & CHECKER ═══════════
def gen_name():
    c = list("bcdfghjklmnprstvwz"); v = ["a","e","i","o","u"]
    l = random.randint(5,7); n=""
    for i in range(l): n += random.choice(c) if i%2==0 else random.choice(v)
    return n.lower()

async def init_http():
    global http_session
    if not http_session:
        headers = {"User-Agent": "Mozilla/5.0", "Cache-Control": "no-cache"}
        http_session = aioclient.ClientSession(headers=headers, timeout=aioclient.ClientTimeout(total=3))

async def check_free_http(u):
    global http_session
    if not http_session: await init_http()
    try:
        async with http_session.head(f"https://t.me/{u}", allow_redirects=False) as r:
            return r.status == 404
    except: return False

async def verify_telethon(u):
    global tg_client
    if not tg_client or not tg_client.is_connected(): return False
    try:
        await tg_client.get_entity(u)
        return False # Taken
    except ValueError:
        return True # Free
    except: return False

# ═══════════ BACKGROUND TASKS ═══════════
async def hunter_loop(app_bot):
    global auto_on, check_counter, found_set
    while True:
        if not auto_on:
            await asyncio.sleep(2); continue
        
        batch = 0
        while batch < BATCH_SIZE and auto_on:
            u = gen_name()
            if u in found_set: continue
            
            check_counter += 1; batch += 1
            
            is_free = await check_free_http(u)
            if is_free:
                verified = await verify_telethon(u)
                if verified:
                    found_set.add(u)
                    save_found()
                    try:
                        await app_bot.bot.send_message(OWNER_ID, f"💎 NEW FIND:\n@{u}\nTotal: {len(found_set)}")
                    except: pass
            
            await asyncio.sleep(random.uniform(MIN_DELAY, MAX_DELAY))
            
        if auto_on:
            print(f"Batch Done. Checks: {check_counter}")
            await asyncio.sleep(BIG_PAUSE)

# ═══════════ WEB SERVER (AIOHTTP) ═══════════
async def serve_static(request):
    path = request.match_info['path']
    if ".." in path: return web.Response(status=403)
    
    file_path = os.path.join('web', path)
    if not os.path.exists(file_path) or not os.path.isfile(file_path):
        return web.Response(status=404)
    
    mime_types = {'.html':'text/html', '.css':'text/css', '.js':'application/javascript'}
    ext = os.path.splitext(file_path)[1]
    ctype = mime_types.get(ext, 'text/plain')
    
    with open(file_path, 'rb') as f:
        content = f.read()
    return web.Response(body=content, content_type=ctype)

async def api_stats(request):
    return web.json_response({
        "checked_count": check_counter,
        "found_count": len(found_set),
        "auto_on": auto_on,
        "watch_list": list(watch_set)
    })

async def api_command(request):
    data = await request.json()
    cmd = data.get('command', '')
    
    if '/on' in cmd:
        global auto_on
        auto_on = True
        print(">>> HUNT STARTED VIA WEBAPP")
    elif '/off' in cmd:
        auto_on = False
        print(">>> HUNT STOPPED VIA WEBAPP")
    elif '/add' in cmd:
        parts = cmd.split()
        if len(parts) > 1:
            name = parts[1].lstrip('@').lower()
            watch_set.add(name)
            save_watch()
            
    return web.json_response({"success": True})

# ═══════════ TELEGRAM BOT HANDLERS ═══════════
async def start(update, context):
    user_id = update.effective_user.id
    
    # ⚠️ ВАЖНО: Здесь должен быть твой IP или Ngrok ссылка
    # Для теста локально оставим localhost, но потом заменим
    mini_app_url = "http://localhost:8080" 
    
    keyboard = [[
        InlineKeyboardButton("💎 ОТКРЫТЬ DASHBOARD", web_app={"url": mini_app_url})
    ]]
    
    msg = (
        "<b>✨ USERNAME HUNTER PRO</b>\n\n"
        "Нажми кнопку ниже, чтобы открыть панель управления.\n"
        "Там ты увидишь статистику, запустишь поиск и добавишь VIP имена."
    )
    await update.message.reply_text(msg, parse_mode=ParseMode.HTML, reply_markup=keyboard)

# ═══════════ MAIN ENTRY POINT ═══════════
async def main():
    global tg_client
    
    # 1. Init Telethon
    tg_client = TelegramClient('session_hunter', API_ID, API_HASH)
    await tg_client.start(bot_token=BOT_TOKEN)
    
    # 2. Load Data
    load_data()
    
    # 3. Setup AIOHTTP Server (for WebApp)
    app_web = web.Application()
    # Маршруты для статики
    app_web.router.add_get('/{path:.+}', serve_static)
    # API маршруты
    app_web.router.add_post('/api/command', api_command)
    app_web.router.add_get('/api/stats', api_stats)
    
    runner = web.AppRunner(app_web)
    await runner.setup()
    site = web.TCPSite(runner, host='0.0.0.0', port=PORT)
    await site.start()
    print(f"🌐 WebServer running on http://0.0.0.0:{PORT}")
    
    # 4. Setup PTB Bot
    app_bot = Application.builder().token(BOT_TOKEN).build()
    app_bot.add_handler(CommandHandler("start", start))
    
    await app_bot.initialize()
    await app_bot.start()
    await app_bot.updater.start_polling()
    
    print(" SYSTEM READY. Open Telegram and click /start")
    
    # 5. Run Loops Concurrently
    await asyncio.gather(
        hunter_loop(app_bot)
    )

if __name__ == "__main__":
    try:
        asyncio.run(main())
    except KeyboardInterrupt:
        print("\nShutting down...")
