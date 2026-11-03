import asyncio, os, json, random, time, hashlib
from dotenv import load_dotenv
from aiohttp import web, ClientSession, TCPConnector
from telethon import TelegramClient
from telegram.ext import Application, CommandHandler, CallbackQueryHandler, ContextTypes
from telegram import InlineKeyboardButton, InlineKeyboardMarkup

load_dotenv()
API_ID = int(os.getenv("API_ID"))
API_HASH = os.getenv("API_HASH")
BOT_TOKEN = os.getenv("BOT_TOKEN")
OWNER_ID = 6288011144

FOUND_FILE = "found_v2.json"
WATCH_FILE = "watch_v2.json"

tg_client = None
http_session = None
auto_on = False
check_counter = 0
found_set = set()
watch_set = set()
result_cache = {}

# !!! ВАЖНО: Сюда мы вставим ссылку из localtunnel !!!
MINI_APP_URL = "https://your-tunnel-url.loca.lt" 

def load_data():
    global found_set, watch_set
    if os.path.exists(FOUND_FILE):
        with open(FOUND_FILE) as f: found_set = set(json.load(f))
    if os.path.exists(WATCH_FILE):
        with open(WATCH_FILE) as f: watch_set = set(json.load(f))
    else:
        watch_set = {"admin", "crypto", "ton"}
        save_watch()

def save_found():
    with open(FOUND_FILE, "w") as f: json.dump(list(found_set), f)
def save_watch():
    with open(WATCH_FILE, "w") as f: json.dump(list(watch_set), f)

def gen_name():
    c = list("bcdfghjklmnprstvwz"); v = ["a", "e", "i", "o", "u"]; d = ["0","1","2","3","4","5","6","7","8","9"]
    l = random.randint(7, 10); n = ""
    for i in range(l):
        if i % 2 == 0: n += random.choice(c)
        else: n += random.choice(d) if random.random() < 0.3 else random.choice(v)
    return n.lower()

async def init_http():
    global http_session
    if not http_session:
        http_session = ClientSession(connector=TCPConnector(limit=100), headers={"User-Agent": "Mozilla/5.0"}, timeout=__import__('aiohttp').ClientTimeout(total=2))

async def check_free_fast(username):
    if username in result_cache and time.time() - result_cache[username][1] < 300:
        return result_cache[username][0]
    global http_session
    if not http_session: await init_http()
    try:
        async with http_session.head(f"https://t.me/{username}", allow_redirects=False) as r:
            if r.status == 404:
                result_cache[username] = (True, time.time()); return True
    except: pass
    global tg_client
    if tg_client and tg_client.is_connected():
        try:
            await tg_client.get_entity(username)
            result_cache[username] = (False, time.time()); return False
        except ValueError:
            result_cache[username] = (True, time.time()); return True
    result_cache[username] = (False, time.time()); return False

async def hunter_loop(app_bot):
    global auto_on, check_counter, found_set
    while True:
        if not auto_on: await asyncio.sleep(2); continue
        batch = [gen_name() for _ in range(10) if gen_name() not in found_set and gen_name() not in result_cache]
        if not batch: await asyncio.sleep(0.5); continue
        for u in batch:
            check_counter += 1
            if await check_free_fast(u):
                found_set.add(u); save_found()
                print(f"FOUND @{u}")
                try: await app_bot.bot.send_message(OWNER_ID, f"NEW FIND:\n@{u}\nTotal: {len(found_set)}")
                except: pass
        await asyncio.sleep(random.uniform(0.5, 1.5))

# --- WEB SERVER ---
async def serve_static(request):
    path = request.match_info.get('path', 'index.html')
    file_path = os.path.join('web', path)
    if not os.path.exists(file_path): return web.Response(status=404)
    mime = {'html':'text/html', 'css':'text/css', 'js':'application/javascript'}
    with open(file_path, 'rb') as f: content = f.read()
    return web.Response(body=content, content_type=mime.get(path.split('.')[-1], 'text/plain'))

async def api_stats(request):
    return web.json_response({"checked_count": check_counter, "found_count": len(found_set), "auto_on": auto_on, "watch_list": list(watch_set)})

async def api_command(request):
    global auto_on
    data = await request.json()
    cmd = data.get('command', '')
    if '/on' in cmd: auto_on = True
    elif '/off' in cmd: auto_on = False
    elif '/add' in cmd:
        parts = cmd.split()
        if len(parts) > 1: watch_set.add(parts[1].lstrip('@').lower()); save_watch()
    return web.json_response({"success": True})

# --- BOT ---
async def cmd_start(update, context):
    kb = [[InlineKeyboardButton("OPEN DASHBOARD", web_app={"url": MINI_APP_URL})]]
    await update.message.reply_text("Welcome to Hunter Pro!\nClick below to open the dashboard.", reply_markup=InlineKeyboardMarkup(kb))

async def main():
    global tg_client
    tg_client = TelegramClient('session_hunter', API_ID, API_HASH)
    await tg_client.start(bot_token=BOT_TOKEN)
    load_data(); await init_http()
    
    app_web = web.Application()
    app_web.router.add_get('/{path:.*}', serve_static)
    app_web.router.add_post('/api/command', api_command)
    app_web.router.add_get('/api/stats', api_stats)
    runner = web.AppRunner(app_web)
    await runner.setup()
    await web.TCPSite(runner, host='0.0.0.0', port=8080).start()
    print("WEB SERVER READY on port 8080")
    
    app_bot = Application.builder().token(BOT_TOKEN).build()
    app_bot.add_handler(CommandHandler("start", cmd_start))
    await app_bot.initialize(); await app_bot.start(); await app_bot.updater.start_polling()
    print("BOT READY")
    
    await asyncio.gather(hunter_loop(app_bot))

if __name__ == "__main__":
    try: asyncio.run(main())
    except KeyboardInterrupt: print("\nShutting down...")
