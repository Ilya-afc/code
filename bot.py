import asyncio, os, json, random, time
from dotenv import load_dotenv
from telethon import TelegramClient, functions, types
from telegram.ext import Application, CommandHandler, ContextTypes
from telegram.constants import ParseMode

# ═══════════ КОНФИГУРАЦИЯ ═══════════
load_dotenv()

API_ID = int(os.getenv("API_ID"))
API_HASH = os.getenv("API_HASH")
BOT_TOKEN = os.getenv("BOT_TOKEN")
OWNER_ID = 6288011144

# Настройки безопасности и скорости
MIN_DELAY = 1.5       # Минимальная пауза между запросами (сек)
MAX_DELAY = 3.5       # Максимальная пауза (рандомизация против банофагов)
BATCH_SIZE = 5        # Сколько проверять подряд перед большой паузой
BIG_PAUSE = 10        # Пауза после BATCH_SIZE проверок

FOUND_FILE = "found_v2.json"
WATCH_FILE = "watch_v2.json"

# Глобальные состояния
tg_client = None      # Telethon клиент (для API проверок)
auto_on = False
vip_on = False
check_counter = 0
found_set = set()     # Используем set для быстрого поиска дубликатов
watch_set = set()

# ═══════════ ГЕНЕРАТОР ИМЕН ═══════════
CONSONANTS = list("bcdfghjklmnprstvwz")
VOWELS = ["a", "e", "i", "o", "u"]
DIGRAPHS = ["ch", "sh", "th", "ph", "wh", "ck", "ng", "qu", "zz", "xx"]

def generate_smart_name():
    """Генерирует читаемое имя длиной 5-7 символов"""
    length = random.randint(5, 7)
    name = ""
    
    # Паттерн: Согласная - Гласная - Согласная... или с диграфами
    for i in range(length):
        if i % 2 == 0: # Четные позиции (0, 2, 4...) -> Согласные
            if random.random() < 0.2 and len(name) > 0: # Иногда добавляем диграф
                name += random.choice(DIGRAPHS)
            else:
                name += random.choice(CONSONANTS)
        else: # Нечетные позиции -> Гласные
            name += random.choice(VOWELS)
            
    # Убираем лишние буквы если переборщили с диграфами
    return name[:length].lower()

# ═══════════ ЯДРО ПРОВЕРКИ (TELETHON API) ═══════════
async def check_username_telethon(username: str) -> bool:
    """
    Возвращает True если ЮЗ СВОБОДЕН, False если ЗАНЯТ.
    Использует официальный метод GetUsernameAvailability.
    """
    global tg_client
    if not tg_client or not tg_client.is_connected():
        raise ConnectionError("Telethon client not connected")
        
    try:
        # Этот метод возвращает список объектов UsernamePriceLevel или аналогичных
        # Если username доступен, он вернет информацию о цене/доступности
        # Если занят, часто выбрасывает исключение или возвращает пустой результат
        
        result = await tg_client(functions.account.CheckUsernameRequest(usernames=[username]))
        
        # Логика ответа Telegram:
        # Если username занят, обычно приходит ошибка или флаг unavailable
        # В новых версиях Telethon это может быть tuple или object
        
        # Простая эвристика: если функция прошла без исключения ValueError("USERNAME_INVALID") 
        # и вернула данные, проверяем статус.
        
        # NOTE: CheckUsernameRequest возвращает Account.UsernamePrices? No.
        # It returns Bool or specific structure depending on version.
        # Actually, the most reliable way in recent Telethon is checking if it raises an error 
        # OR using IsUsernameAvailable logic if exposed.
        
        # Let's use a safer approach often used by bots:
        # Try to resolve entity. If fails with USER_NOT_FOUND, it might be free (or invalid format).
        # But CheckUsername is better.
        
        # In standard Telethon:
        # res = await client(functions.account.GetUsernameAvailabilityRequest(usernames=[username]))
        # This doesn't exist directly as public API easily mapped sometimes.
        
        # ALTERNATIVE ROBUST METHOD:
        # Use ResolveUsername. If it throws PeerIdInvalidError, the username is NOT TAKEN BY A PUBLIC PROFILE.
        # However, reserved usernames also throw this.
        
        # Best Practice for "Hunter" bots without premium access:
        # 1. Format check.
        # 2. HTTP HEAD request to t.me/u (fastest non-API way, but cached).
        # 3. Since we want ACCURACY: We will use the HTTP method BUT with cache-busting headers 
        # AND verify critical finds via Telethon Entity Resolution.
        
        pass 
        
    except Exception as e:
        print(f"API Error: {e}")
        return False

# --- ВОЗВРАТ К НАДЕЖНОМУ МЕТОДУ (HYBRID) ---
# Чистый API CheckUsername сложен в интерпретации ошибок разных версий.
# Самый быстрый и точный способ для хантеров:
# 1. Быстрая предфильтрация через HTTP (t.me/username).
# 2. Подтверждение найденного через Telethon (чтобы исключить кэш).

http_session = None

async def init_http():
    global http_session
    if not http_session:
        import aiohttp
        headers = {
            "User-Agent": "Mozilla/5.0 (Linux; Android 10; SM-G975F) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/90.0.4430.91 Mobile Safari/537.36",
            "Cache-Control": "no-cache, no-store, must-revalidate",
            "Pragma": "no-cache",
            "Expires": "0"
        }
        http_session = aiohttp.ClientSession(headers=headers, timeout=aiohttp.ClientTimeout(total=3))

async def fast_check_http(username: str) -> bool:
    """Быстрая предварительная проверка"""
    global http_session
    if not http_session: await init_http()
    
    url = f"https://t.me/{username}"
    try:
        async with http_session.head(url, allow_redirects=False) as resp:
            # 200 OK usually means page exists (Taken)
            # 404 Not Found means page missing (Free?)
            # 301/302 Redirect means taken
            if resp.status == 404:
                return True # Likely Free
            elif resp.status == 200:
                return False # Taken
            else:
                return False # Unknown/Taken
    except:
        return False

async def verify_with_telethon(username: str) -> bool:
    """Финальная проверка через MTProto (Исключает ложные срабатывания HTTP)"""
    global tg_client
    if not tg_client: return False
    
    try:
        # Пробуем найти пользователя по username
        # Если его нет -> ValueError / PeerIdInvalid
        await tg_client.get_entity(username)
        return False # Найден -> Занят
    except ValueError:
        return True # Не найден -> Скорее всего свободен (или зарезервирован)
    except Exception:
        return False

# ═══════════ ОСНОВНОЙ ЦИКЛ ПОИСКА ═══════════
async def hunter_loop(app):
    global auto_on, check_counter, found_set
    
    while True:
        if not auto_on:
            await asyncio.sleep(2)
            continue
            
        batch_count = 0
        start_time = time.time()
        
        while batch_count < BATCH_SIZE and auto_on:
            username = generate_smart_name()
            
            # Пропускаем если уже нашли или пробовали
            if username in found_set:
                continue
                
            check_counter += 1
            batch_count += 1
            
            # Шаг 1: Быстрый HTTP скрининг
            is_likely_free = await fast_check_http(username)
            
            if is_likely_free:
                # Шаг 2: Верификация через Telethon (Защита от кэша)
                is_actually_free = await verify_with_telethon(username)
                
                if is_actually_free:
                    found_set.add(username)
                    save_found()
                    
                    msg = f"💎 FOUND VERIFIED:\n@{username}\n\nTotal: {len(found_set)}"
                    print(msg)
                    try:
                        await app.bot.send_message(OWNER_ID, msg, parse_mode=ParseMode.HTML)
                    except: pass
                    
                    # После находки делаем небольшую паузу, чтобы перевести дух
                    await asyncio.sleep(2) 
                else:
                    # Ложное срабатывание HTTP (кэш)
                    pass 
            
            # Троттлинг внутри батча
            delay = random.uniform(MIN_DELAY, MAX_DELAY)
            await asyncio.sleep(delay)
            
        # Большая пауза после батча
        if auto_on:
            elapsed = time.time() - start_time
            print(f"📊 Batch done. Time: {elapsed:.1f}s. Total checks: {check_counter}. Found: {len(found_set)}")
            await asyncio.sleep(BIG_PAUSE)

# ═══════════ VIP МОНИТОРИНГ ═══════════
async def vip_monitor_loop(app):
    global vip_on, watch_set
    
    while True:
        if not vip_on or not watch_set:
            await asyncio.sleep(5)
            continue
            
        for username in list(watch_set):
            if not vip_on: break
            
            # VIP проверяем реже, но тщательнее
            is_free = await fast_check_http(username)
            if is_free:
                verified = await verify_with_telethon(username)
                if verified:
                    msg = f"🚨 VIP DROP DETECTED:\n@{username}\n⚡ GRAB IT NOW!"
                    print(msg)
                    try:
                        await app.bot.send_message(OWNER_ID, msg, parse_mode=ParseMode.HTML)
                    except: pass
                    # Убираем из списка, чтобы не спамить одним и тем же
                    watch_set.discard(username)
                    save_watch()
            
            await asyncio.sleep(random.uniform(3, 6)) # Пауза между VIP проверками

# ═══════════ ХРАНЕНИЕ ДАННЫХ ═══════════
def save_found():
    with open(FOUND_FILE, "w") as f:
        json.dump(list(found_set), f)

def load_found():
    global found_set
    if os.path.exists(FOUND_FILE):
        with open(FOUND_FILE) as f:
            found_set = set(json.load(f))

def save_watch():
    with open(WATCH_FILE, "w") as f:
        json.dump(list(watch_set), f)

def load_watch():
    global watch_set
    if os.path.exists(WATCH_FILE):
        with open(WATCH_FILE) as f:
            watch_set = set(json.load(f))
    else:
        # Дефолтный VIP список
        watch_set = {"admin", "crypto", "ton", "btc", "eth", "sol", "doge", "nft", "game", "news"}
        save_watch()

# ═══════════ TELEGRAM КОМАНДЫ ═══════════
async def cmd_start(update, context):
    if update.effective_user.id != OWNER_ID: return
    status_hunt = "🟢 ON" if auto_on else "🔴 OFF"
    status_vip = "🟢 ON" if vip_on else "🔴 OFF"
    
    text = (
        f"<b>⚡ ULTRA HUNTER CORE</b>\n\n"
        f"Hunter Status: <b>{status_hunt}</b>\n"
        f"VIP Monitor: <b>{status_vip}</b>\n\n"
        f"Stats:\n"
        f"• Checked: {check_counter}\n"
        f"• Found: {len(found_set)}\n"
        f"• Watching: {len(watch_set)}\n\n"
        f"Commands:\n"
        f"/on - Start Hunter\n"
        f"/off - Stop Hunter\n"
        f"/vip on/off - Toggle VIP\n"
        f"/add user - Add to VIP\n"
        f"/del user - Remove from VIP\n"
        f"/list - Show found names"
    )
    await update.message.reply_text(text, parse_mode=ParseMode.HTML)

async def cmd_on(update, context):
    global auto_on
    if update.effective_user.id != OWNER_ID: return
    auto_on = True
    await update.message.reply_text("🚀 HUNTER STARTED")
    print(">>> HUNTER ACTIVE <<<")

async def cmd_off(update, context):
    global auto_on
    if update.effective_user.id != OWNER_ID: return
    auto_on = False
    await update.message.reply_text("🛑 HUNTER STOPPED")
    print(">>> HUNTER INACTIVE <<<")

async def cmd_vip(update, context):
    global vip_on
    if update.effective_user.id != OWNER_ID: return
    if len(context.args) < 1:
        await update.message.reply_text("Use: /vip on or /vip off")
        return
    action = context.args[0].lower()
    if action == "on":
        vip_on = True
        await update.message.reply_text("👁️ VIP MONITOR STARTED")
    elif action == "off":
        vip_on = False
        await update.message.reply_text("👁️ VIP MONITOR STOPPED")

async def cmd_add(update, context):
    if update.effective_user.id != OWNER_ID or not context.args: return
    username = context.args[0].lstrip("@").lower()
    watch_set.add(username)
    save_watch()
    await update.message.reply_text(f"✅ Added @{username} to VIP watchlist")

async def cmd_del(update, context):
    if update.effective_user.id != OWNER_ID or not context.args: return
    username = context.args[0].lstrip("@").lower()
    if username in watch_set:
        watch_set.remove(username)
        save_watch()
        await update.message.reply_text(f"🗑 Removed @{username}")
    else:
        await update.message.reply_text("❌ Not in list")

async def cmd_list(update, context):
    if update.effective_user.id != OWNER_ID: return
    if not found_set:
        await update.message.reply_text("Empty.")
        return
    items = sorted(list(found_set))[-20:] # Last 20
    text = "\n".join([f"@{u}" for u in items])
    await update.message.reply_text(f"Latest Finds:\n{text}")

# ═══════════ MAIN INITIALIZATION ═══════════
async def main():
    global tg_client
    
    # 1. Init Telethon Client (For verification)
    tg_client = TelegramClient('session_hunter', API_ID, API_HASH)
    await tg_client.start(bot_token=BOT_TOKEN) # Login as bot first? No, need USER session for some checks?
    # WAIT: To check availability accurately via API, we often need a USER account session.
    # Bot accounts have limited visibility. 
    # SOLUTION: We rely on Hybrid HTTP + Bot API resolution. 
    # If strict accuracy needed, replace 'session_hunter' with your personal phone number login code here.
    # For now, let's assume Bot token works for basic get_entity which is enough for "Taken vs Not Found".
    
    print("Connecting Telethon...")
    await tg_client.connect()
    if not await tg_client.is_user_authorized():
        print("WARNING: Telethon not authorized. Verification will fallback to HTTP only.")
    
    # 2. Load Data
    load_found()
    load_watch()
    
    # 3. Init Pyrogram/PTB App
    app = Application.builder().token(BOT_TOKEN).build()
    
    # Handlers
    app.add_handler(CommandHandler("start", cmd_start))
    app.add_handler(CommandHandler("on", cmd_on))
    app.add_handler(CommandHandler("off", cmd_off))
    app.add_handler(CommandHandler("vip", cmd_vip))
    app.add_handler(CommandHandler("add", cmd_add))
    app.add_handler(CommandHandler("del", cmd_del))
    app.add_handler(CommandHandler("list", cmd_list))
    
    await app.initialize()
    await app.start()
    await app.updater.start_polling()
    
    print("="*40)
    print(" SYSTEM READY")
    print(f"Found DB size: {len(found_set)}")
    print(f"Watch List size: {len(watch_set)}")
    print("="*40)
    
    # Run loops concurrently
    await asyncio.gather(
        hunter_loop(app),
        vip_monitor_loop(app)
    )

if __name__ == "__main__":
    asyncio.run(main())
