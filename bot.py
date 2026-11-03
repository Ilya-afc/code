import asyncio, os, json, random, time, hashlib
from datetime import datetime, timedelta
from dotenv import load_dotenv
from aiohttp import web, ClientSession, TCPConnector
from telethon import TelegramClient
from telegram.ext import Application, CommandHandler, CallbackQueryHandler, ContextTypes, PreCheckoutQueryHandler, MessageHandler, filters
from telegram.constants import ParseMode
from telegram import InlineKeyboardButton, InlineKeyboardMarkup, LabeledPrice

load_dotenv()
API_ID = int(os.getenv("API_ID"))
API_HASH = os.getenv("API_HASH")
BOT_TOKEN = os.getenv("BOT_TOKEN")
CRYPTO_BOT_TOKEN = os.getenv("CRYPTO_BOT_TOKEN", "")
OWNER_ID = 6288011144
OWNER_LINK = "https://t.me/faluoo"

FOUND_FILE = "found_v2.json"
WATCH_FILE = "watch_v2.json"
SUBS_FILE = "subs.json"
REF_FILE = "referrals.json"

BATCH_SIZE = 10
MIN_DELAY = 0.5
MAX_DELAY = 1.5
BIG_PAUSE = 5
HTTP_TIMEOUT = 2
CACHE_TTL = 300
FREE_BATCH = 5

tg_client = None
http_session = None
auto_on = False
check_counter = 0
found_set = set()
watch_set = set()
subs_dict = {}
refs_dict = {}
result_cache = {}

PLANS = {
    "1h": {"name": "⏰ 1 Час", "rub": 10, "stars": 5, "delta": timedelta(hours=1)},
    "1d": {"name": "📅 1 День", "rub": 50, "stars": 25, "delta": timedelta(days=1)},
    "7d": {"name": "🗓️ 7 Дней", "rub": 100, "stars": 50, "delta": timedelta(days=7)},
    "life": {"name": "♾️ Навсегда", "rub": 500, "stars": 250, "delta": None},
}

def load_data():
    global found_set, watch_set, subs_dict, refs_dict
    if os.path.exists(FOUND_FILE):
        with open(FOUND_FILE) as f: found_set = set(json.load(f))
    if os.path.exists(WATCH_FILE):
        with open(WATCH_FILE) as f: watch_set = set(json.load(f))
    else:
        watch_set = {"admin", "crypto", "ton", "btc"}
        save_watch()
    if os.path.exists(SUBS_FILE):
        with open(SUBS_FILE) as f: subs_dict = json.load(f)
    if os.path.exists(REF_FILE):
        with open(REF_FILE) as f: refs_dict = json.load(f)

def save_found():
    with open(FOUND_FILE, "w") as f: json.dump(list(found_set), f)

def save_watch():
    with open(WATCH_FILE, "w") as f: json.dump(list(watch_set), f)

def save_subs():
    with open(SUBS_FILE, "w") as f: json.dump(subs_dict, f)

def save_refs():
    with open(REF_FILE, "w") as f: json.dump(refs_dict, f)

def is_subscribed(uid):
    if str(uid) == str(OWNER_ID): return True
    val = subs_dict.get(str(uid))
    if not val: return False
    if val == "lifetime": return True
    try:
        return datetime.fromisoformat(val) > datetime.now()
    except: return False

def grant_sub(uid, plan_key):
    p = PLANS[plan_key]
    if p["delta"] is None:
        subs_dict[str(uid)] = "lifetime"
    else:
        base = datetime.now()
        cur = subs_dict.get(str(uid))
        if cur and cur != "lifetime":
            try:
                d = datetime.fromisoformat(cur)
                if d > base: base = d
            except: pass
        subs_dict[str(uid)] = (base + p["delta"]).isoformat()
    save_subs()

def get_ref_code(uid):
    for code, data in refs_dict.items():
        if data.get("owner") == uid: return code
    code = hashlib.md5(str(uid).encode()).hexdigest()[:8]
    refs_dict[code] = {"owner": uid, "invited": [], "pending": {}}
    save_refs()
    return code

def gen_name():
    c = list("bcdfghjklmnprstvwz")
    v = ["a", "e", "i", "o", "u"]
    digits = ["0", "1", "2", "3", "4", "5", "6", "7", "8", "9"]
    l = random.randint(7, 10)
    n = ""
    for i in range(l):
        if i % 2 == 0: n += random.choice(c)
        else:
            if random.random() < 0.3: n += random.choice(digits)
            else: n += random.choice(v)
    return n.lower()

async def init_http():
    global http_session
    if not http_session:
        connector = TCPConnector(limit=100, ttl_dns_cache=300)
        headers = {"User-Agent": "Mozilla/5.0 (Linux; Android 10) AppleWebKit/537.36 Chrome/90 Mobile Safari/537.36"}
        http_session = ClientSession(connector=connector, headers=headers, timeout=__import__('aiohttp').ClientTimeout(total=HTTP_TIMEOUT))

def check_cache(username):
    if username in result_cache:
        is_free, timestamp = result_cache[username]
        if time.time() - timestamp < CACHE_TTL: return is_free
    return None

async def check_free_fast(username):
    cached = check_cache(username)
    if cached is not None: return cached
    
    global http_session
    if not http_session: await init_http()
    
    try:
        async with http_session.head(f"https://t.me/{username}", allow_redirects=False) as r:
            if r.status == 404:
                result_cache[username] = (True, time.time())
                return True
    except: pass
    
    global tg_client
    if tg_client and tg_client.is_connected():
        try:
            await tg_client.get_entity(username)
            result_cache[username] = (False, time.time())
            return False
        except ValueError:
            result_cache[username] = (True, time.time())
            return True
        except: pass
    
    result_cache[username] = (False, time.time())
    return False

async def check_batch(usernames):
    tasks = [check_free_fast(u) for u in usernames]
    results = await asyncio.gather(*tasks, return_exceptions=True)
    return [(u, r) for u, r in zip(usernames, results) if not isinstance(r, Exception)]

async def hunter_loop(app_bot):
    global auto_on, check_counter, found_set
    
    while True:
        if not auto_on:
            await asyncio.sleep(2)
            continue
        
        batch = []
        for _ in range(BATCH_SIZE):
            u = gen_name()
            if u not in found_set and u not in result_cache:
                batch.append(u)
        
        if not batch:
            await asyncio.sleep(0.5)
            continue
        
        results = await check_batch(batch)
        
        for username, is_free in results:
            check_counter += 1
            if is_free:
                found_set.add(username)
                save_found()
                msg = f"💎 <b>НАЙДЕНО!</b>\n\n🔖 @{username}\n📊 Всего: {len(found_set)}"
                print(f"💎 @{username}")
                try:
                    await app_bot.bot.send_message(OWNER_ID, msg, parse_mode=ParseMode.HTML)
                except: pass
        
        if check_counter % 50 == 0:
            print(f"⚡ Checks: {check_counter} | Found: {len(found_set)}")
        
        await asyncio.sleep(random.uniform(MIN_DELAY, MAX_DELAY))
        
        if check_counter % 1000 == 0:
            now = time.time()
            result_cache = {k: v for k, v in result_cache.items() if now - v[1] < CACHE_TTL}

# ═══════════ ДИЗАЙН КЛАВИАТУР ═══════════

def main_menu_kb(uid, is_hunting=False):
    """Главное меню с динамической кнопкой автостарта"""
    btn_hunt = InlineKeyboardButton("🛑 ОСТАНОВИТЬ ПОИСК", callback_data="hunt_off") if is_hunting else InlineKeyboardButton("🚀 ЗАПУСТИТЬ ПОИСК", callback_data="hunt_on")
    
    keyboard = [
        [btn_hunt],
        [
            InlineKeyboardButton("🎲 ГЕНЕРАТОР", callback_data="gen"),
            InlineKeyboardButton("🔍 ПРОВЕРИТЬ", callback_data="check_ask")
        ],
        [
            InlineKeyboardButton("💎 ПОДПИСКА", callback_data="sub"),
            InlineKeyboardButton("👥 РЕФЕРАЛЫ", callback_data="ref")
        ],
        [
            InlineKeyboardButton("📊 ПРОФИЛЬ", callback_data="profile"),
            InlineKeyboardButton("👁️ VIP", callback_data="vip")
        ],
        [InlineKeyboardButton("📩 СВЯЗЬ", url=OWNER_LINK)]
    ]
    return InlineKeyboardMarkup(keyboard)

def sub_menu_kb():
    btns = []
    for key, p in PLANS.items():
        btns.append([InlineKeyboardButton(f"{p['name']} • {p['rub']}₽ / {p['stars']}⭐", callback_data=f"pay_{key}")])
    btns.append([InlineKeyboardButton("◀️ НАЗАД", callback_data="back_main")])
    return InlineKeyboardMarkup(btns)

def pay_method_kb(plan):
    p = PLANS[plan]
    btns = [
        [InlineKeyboardButton(f"💳 CryptoBot ({p['rub']}₽)", callback_data=f"m_crypto_{plan}")],
        [InlineKeyboardButton(f"⭐ Stars ({p['stars']})", callback_data=f"m_stars_{plan}")],
        [InlineKeyboardButton("◀️ НАЗАД", callback_data="sub")]
    ]
    return InlineKeyboardMarkup(btns)

# ═══════════ КОМАНДЫ ═══════════

async def cmd_start(update, context):
    uid = update.effective_user.id
    msg = (
        "✨ <b>USERNAME HUNTER PRO</b> ✨\n"
        "━━━━━━━━━━━━━━━━━━━━\n"
        "🔍 <i>Умный поиск свободных никнеймов</i>\n"
        "⚡ <i>Быстро • Безопасно • Надёжно</i>\n"
        "━━━━━━━━━━━━━━━━━━━━\n\n"
        "👇 <b>Выбери действие:</b>"
    )
    await update.message.reply_text(msg, parse_mode=ParseMode.HTML, reply_markup=main_menu_kb(uid, auto_on))

async def callback_handler(update, context):
    global auto_on
    query = update.callback_query
    await query.answer()
    data = query.data
    uid = query.from_user.id
    
    if data == "back_main":
        await query.edit_message_reply_markup(reply_markup=main_menu_kb(uid, auto_on))
    
    elif data == "hunt_on":
        if not is_subscribed(uid) and uid != OWNER_ID:
            await query.answer("🔒 Нужна подписка!", show_alert=True)
            return
        auto_on = True
        await query.edit_message_text(
            "🚀 <b>ПОИСК ЗАПУЩЕН!</b>\n\n"
            "⚡ Бот ищет свободные никнеймы\n"
            "📊 Логи видны в Termux\n"
            "💎 Находки придут сюда\n\n"
            "━━━━━━━━━━━━━━━━━━━━\n"
            "👇 <b>Управление:</b>",
            parse_mode=ParseMode.HTML,
            reply_markup=main_menu_kb(uid, True)
        )
    
    elif data == "hunt_off":
        auto_on = False
        await query.edit_message_text(
            "🛑 <b>ПОИСК ОСТАНОВЛЕН</b>\n\n"
            f"📊 Проверено: {check_counter}\n"
            f"💎 Найдено: {len(found_set)}\n\n"
            "━━━━━━━━━━━━━━━━━━━━\n"
            "👇 <b>Меню:</b>",
            parse_mode=ParseMode.HTML,
            reply_markup=main_menu_kb(uid, False)
        )
    
    elif data == "gen":
        if not is_subscribed(uid) and uid != OWNER_ID:
            await query.answer("🔒 Нужна подписка!", show_alert=True)
            return
        names = [gen_name() for _ in range(FREE_BATCH)]
        text = "🎲 <b>ГЕНЕРАТОР</b>\n━━━━━━━━━━━━━━━━━━━━\n\n"
        text += "\n".join([f"• <code>@{n}</code>" for n in names])
        text += "\n\n━━━━━━━━━━━━━━━━━━━━\n👇 <b>Меню:</b>"
        await query.edit_message_text(text, parse_mode=ParseMode.HTML, reply_markup=main_menu_kb(uid, auto_on))
    
    elif data == "check_ask":
        await query.edit_message_text(
            "🔍 <b>ПРОВЕРКА ЮЗЕРНЕЙМА</b>\n\n"
            "Отправь мне username для проверки:\n"
            "<i>Например: @admin</i>",
            parse_mode=ParseMode.HTML
        )
        context.user_data["waiting_check"] = True
    
    elif data == "sub":
        await query.edit_message_text(
            "💎 <b>ТАРИФЫ</b>\n━━━━━━━━━━━━━━━━━━━━\n\n"
            "🚀 <b>Безлимитный поиск</b>\n"
            "⚡ Приоритетная скорость\n"
            "👁️ VIP мониторинг\n"
            "🎲 Генератор без лимитов\n\n"
            "━━━━━━━━━━━━━━━━━━━━\n"
            "👇 <b>Выбери план:</b>",
            parse_mode=ParseMode.HTML,
            reply_markup=sub_menu_kb()
        )
    
    elif data.startswith("pay_"):
        plan = data.split("_")[1]
        p = PLANS[plan]
        await query.edit_message_text(
            f"💳 <b>ОПЛАТА</b>\n━━━━━━━━━━━━━━━━━━━━\n\n"
            f"📦 <b>{p['name']}</b>\n"
            f"💰 Цена: {p['rub']}₽ или {p['stars']} Stars\n\n"
            "━━━━━━━━━━━━━━━━━━━━\n"
            "👇 <b>Способ оплаты:</b>",
            parse_mode=ParseMode.HTML,
            reply_markup=pay_method_kb(plan)
        )
    
    elif data.startswith("m_crypto_"):
        plan = data.split("_")[2]
        p = PLANS[plan]
        if not CRYPTO_BOT_TOKEN:
            await query.answer("❌ CryptoBot не настроен", show_alert=True)
            return
        payload = f"sub_{uid}_{plan}"
        async with ClientSession(headers={"Crypto-Pay-API-Token": CRYPTO_BOT_TOKEN}) as sess:
            resp = await sess.post("https://pay.crypt.bot/api/createInvoice", json={
                "currency_type": "fiat", "fiat": "RUB", "amount": str(p["rub"]),
                "payload": payload, "allow_comments": False
            })
            inv = await resp.json()
            if inv.get("ok"):
                url = inv["result"]["pay_url"]
                await query.edit_message_text(
                    f"✅ <b>СЧЁТ СОЗДАН</b>\n\n"
                    f"💰 Сумма: {p['rub']}₽\n"
                    f"🔗 <a href='{url}'>Оплатить</a>\n\n"
                    "После оплаты подписка активируется автоматически",
                    parse_mode=ParseMode.HTML
                )
            else:
                await query.answer("❌ Ошибка создания счёта", show_alert=True)
    
    elif data.startswith("m_stars_"):
        plan = data.split("_")[2]
        p = PLANS[plan]
        await context.bot.send_invoice(
            chat_id=uid, title=p["name"], description=f"Подписка {p['name']}",
            payload=f"sub_{uid}_{plan}", provider_token="", currency="XTR",
            prices=[LabeledPrice(label="Access", amount=p["stars"])]
        )
    
    elif data == "ref":
        code = get_ref_code(uid)
        link = f"https://t.me/{context.bot.username}?start={code}"
        ref_data = refs_dict.get(code, {})
        invited = len(ref_data.get("invited", []))
        text = (
            "👥 <b>РЕФЕРАЛЬНАЯ ПРОГРАММА</b>\n"
            "━━━━━━━━━━━━━━━━━━━━\n\n"
            "🎁 <b>+1 ЧАС</b> за каждого друга!\n\n"
            f"📊 Приглашено: <b>{invited}</b>\n"
            f"⏰ Заработано: <b>{invited} ч</b>\n\n"
            "━━━━━━━━━━━━━━━━━━━━\n"
            "🔗 <b>Твоя ссылка:</b>\n"
            f"<code>{link}</code>\n\n"
            "━━━━━━━━━━━━━━━━━━━━\n"
            "👇 <b>Меню:</b>"
        )
        await query.edit_message_text(text, parse_mode=ParseMode.HTML, reply_markup=main_menu_kb(uid, auto_on))
    
    elif data == "profile":
        sub_status = "♾️
