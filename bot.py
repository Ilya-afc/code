import asyncio, os, json, random, time
from dotenv import load_dotenv
from telegram.ext import Application, CommandHandler
import aiohttp

# ═══════════ НАСТРОЙКИ ═══════════
load_dotenv()
BOT_TOKEN = os.getenv("BOT_TOKEN")
OWNER_ID = 6288011144  # Твой ID

AUTO_PAUSE = 6.5       # Задержка между проверками (сек)
FOUND_FILE = "found.json"

# Глобальные переменные
http_session = None
auto_on = False
tried = set()          # Уже проверенные имена
found_list = []        # Найденные свободные
check_count = 0        # Счетчик для логов

# ═══════════ БАЗА ДАННЫХ ЮЗОВ ═══════════
CLU = ["fl","fr","gl","gr","pl","pr","st","sp","tr","dr","cl","cr","sl","sm","sn","sw","sh","ch","th","br","bl","sk","sc","qu"]
SIN = list("bcdfghjklmnprstvwz")
VOW = ["a","e","i","o","u"]
DVOW = ["oo","ee","aa","ou","au","eo","ea","io","ue","oa","ia","ai","oi","ay","ey"]

def gen_username():
    """Генерирует красивое имя из паттернов"""
    pattern_type = random.randint(1, 5)
    if pattern_type == 1: return random.choice(CLU)+random.choice(VOW)+random.choice(SIN)+random.choice(DVOW)
    if pattern_type == 2: return random.choice(SIN)+random.choice(VOW)+random.choice(SIN)+random.choice(DVOW)
    if pattern_type == 3: return random.choice(CLU)+random.choice(VOW)+random.choice(SIN)+random.choice(VOW)
    if pattern_type == 4: return random.choice(SIN)+random.choice(VOW)+random.choice(CLU)+random.choice(VOW)
    return random.choice(CLU)+random.choice(DVOW)+random.choice(SIN)+random.choice(VOW)

# ═══════════ ПРОВЕРКА ЧЕРЕЗ HTML (БЕЗ API) ═══════════
async def init_http():
    global http_session
    if not http_session:
        headers = {
            "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36",
            "Accept-Language": "ru-RU"
        }
        http_session = aiohttp.ClientSession(headers=headers, timeout=aiohttp.ClientTimeout(total=5))

async def check_free(username):
    """Проверяет свободен ли юзернейм через t.me"""
    global http_session
    if not http_session: await init_http()
    
    url = f"https://t.me/{username}"
    try:
        async with http_session.get(url, allow_redirects=True) as resp:
            text = await resp.text()
            # Если страница не найдена - значит СВОБОДЕН
            if "Sorry, this page isn't available" in text or resp.status == 404:
                return True
            # Если есть профиль - ЗАНЯТ
            if 'property="og:title"' in text or 'tgme_page_title' in text:
                return False
            return False
    except Exception as e:
        print(f"⚠️ Ошибка сети: {e}")
        return None

# ═══════════ ЛОГИКА АВТОСТАРТА ═══════════
async def auto_search_loop(app):
    """Фоновый процесс поиска"""
    global auto_on, tried, found_list, check_count
    
    while True:
        if not auto_on:
            await asyncio.sleep(2)
            continue
            
        # Генерируем новое имя
        username = gen_username()
        
        # Пропускаем если уже проверяли
        if username in tried:
            await asyncio.sleep(0.1)
            continue
            
        tried.add(username)
        check_count += 1
        
        # Проверяем
        is_free = await check_free(username)
        
        if is_free:
            # Нашли свободный!
            found_list.append(username)
            save_found()
            
            msg = f"💎 НАЙДЕН СВОБОДНЫЙ:\n@{username}\n\n📊 Проверено всего: {check_count}"
            print(msg) # В консоль Termux
            try:
                await app.bot.send_message(OWNER_ID, msg) # В Telegram
            except: pass
        else:
            # Просто лог в консоль каждые 10 попыток
            if check_count % 10 == 0:
                log_msg = f"🔄 Идет поиск... Проверено: {check_count} | Найдено: {len(found_list)}"
                print(log_msg)
                
        # Ждем паузу
        await asyncio.sleep(AUTO_PAUSE)

def save_found():
    with open(FOUND_FILE, "w") as f:
        json.dump(found_list, f)

def load_found():
    global found_list
    if os.path.exists(FOUND_FILE):
        with open(FOUND_FILE) as f:
            found_list = json.load(f)

# ═══════════ КОМАНДЫ БОТА ═══════════
async def cmd_start(update, context):
    user_id = update.effective_user.id
    if user_id != OWNER_ID:
        return
        
    status = "✅ АКТИВЕН" if auto_on else "❌ ВЫКЛЮЧЕН"
    await update.message.reply_text(
        f"<b>USERNAME HUNTER CORE</b>\n\n"
        f"Статус автопоиска: <b>{status}</b>\n"
        f"Найдено всего: <b>{len(found_list)}</b>\n\n"
        f"Команды:\n"
        f"/on - включить поиск\n"
        f"/off - выключить поиск\n"
        f"/stat - показать статистику\n"
        f"/list - список найденных",
        parse_mode="HTML"
    )

async def cmd_on(update, context):
    global auto_on
    if update.effective_user.id != OWNER_ID: return
    
    if auto_on:
        await update.message.reply_text("⚠️ Поиск уже запущен!")
        return
        
    auto_on = True
    await update.message.reply_text(f"🚀 АВТОПОИСК ЗАПУЩЕН!\nПауза: {AUTO_PAUSE} сек\nСмотри логи в Termux.")
    print(">>> АВТОПОИСК ВКЛЮЧЕН <<<")

async def cmd_off(update, context):
    global auto_on
    if update.effective_user.id != OWNER_ID: return
    
    auto_on = False
    await update.message.reply_text(f"🛑 ПОИСК ОСТАНОВЛЕН.\nНайдено за сессию: {len(found_list)}")
    print(">>> АВТОПОИСК ВЫКЛЮЧЕН <<<")

async def cmd_stat(update, context):
    if update.effective_user.id != OWNER_ID: return
    
    status = "🟢 РАБОТАЕТ" if auto_on else "🔴 ПАУЗА"
    await update.message.reply_text(
        f"📊 СТАТИСТИКА\n\n"
        f"Статус: <b>{status}</b>\n"
        f"Проверено имен: <b>{check_count}</b>\n"
        f"Найдено свободных: <b>{len(found_list)}</b>\n"
        f"Задержка: <b>{AUTO_PAUSE} сек</b>",
        parse_mode="HTML"
    )

async def cmd_list(update, context):
    if update.effective_user.id != OWNER_ID: return
    
    if not found_list:
        await update.message.reply_text("😔 Пока ничего не найдено.")
        return
        
    # Показываем последние 20
    last_20 = found_list[-20:]
    names = "\n".join([f"@{name}" for name in last_20])
    await update.message.reply_text(f"💎 ПОСЛЕДНИЕ НАХОДКИ:\n\n{names}")

# ═══════════ MAIN ═══════════
async def main():
    load_found()
    
    app = Application.builder().token(BOT_TOKEN).build()
    
    # Хендлеры команд
    app.add_handler(CommandHandler("start", cmd_start))
    app.add_handler(CommandHandler("on", cmd_on))
    app.add_handler(CommandHandler("off", cmd_off))
    app.add_handler(CommandHandler("stat", cmd_stat))
    app.add_handler(CommandHandler("list", cmd_list))
    
    await app.initialize()
    await app.start()
    await app.updater.start_polling()
    
    print("="*40)
    print(" USERNAME HUNTER CORE STARTED")
    print(f"Owner ID: {OWNER_ID}")
    print(f"Pause: {AUTO_PAUSE}s")
    print("="*40)
    
    # Запускаем фоновый поиск параллельно с ботом
    await asyncio.gather(auto_search_loop(app))

if __name__ == "__main__":
    asyncio.run(main())
