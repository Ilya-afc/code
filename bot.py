import asyncio, os, json, random, re, time
from datetime import datetime, timedelta
from dotenv import load_dotenv
from telethon import TelegramClient
from telegram import InlineKeyboardButton, InlineKeyboardMarkup, LabeledPrice
from telegram.ext import Application, CommandHandler, CallbackQueryHandler, PreCheckoutQueryHandler, MessageHandler, filters
import aiohttp

load_dotenv()
API_ID = int(os.getenv("API_ID"))
API_HASH = os.getenv("API_HASH")
BOT_TOKEN = os.getenv("BOT_TOKEN")
CRYPTO_BOT_TOKEN = os.getenv("CRYPTO_BOT_TOKEN", "")
OWNER_ID = 6288011144
OWNER_LINK = "https://t.me/faluoo"
GIFT_USERNAME = "coldeev"
DATA_FILE = "usernames.json"
FOUND_FILE = "found.json"
SUBS_FILE = "subs.json"
CHECK_INTERVAL = 300
PAUSE = 4

client = TelegramClient('session', API_ID, API_HASH)
crypto_session = None
http_session = None
proxy_list = []
notified = set()
tried = set()
cooldown = {}
auto_on = False
_last_chk = 0
app_global = None

PLANS = {
    "1h":   {"name": "1 час",     "rub": 10,  "stars": 5,   "delta": timedelta(hours=1)},
    "1d":   {"name": "1 день",    "rub": 50,  "stars": 25,  "delta": timedelta(days=1)},
    "7d":   {"name": "7 дней",    "rub": 100, "stars": 50,  "delta": timedelta(days=7)},
    "life": {"name": "Навсегда",  "rub": 500, "stars": 250, "delta": None},
}

CLU  = ["fl","fr","gl","gr","pl","pr","st","sp","tr","dr","cl","cr","sl","sm","sn","sw","sh","ch","th","br","bl","sk","sc","qu"]
SIN  = list("bcdfghjklmnprstvwz")
VOW  = ["a","e","i","o","u"]
DVOW = ["oo","ee","aa","ou","au","eo","ea","io","ue","oa","ia","ai","oi","ay","ey"]
WORDS = ["monk","nova","echo","zen","wolf","frost","ember","lunar","solar","storm","blaze","crisp","glow","mint","jade","onyx","ruby","pearl","ashen","drift","flux","halo","iris","kite","lumen","mist","opal","petal","quartz","raven","sable","thorn","umber","velvet","willow","amber","brook","cedar","dune","grove","haven","ivy","lark","moss","nook","oak","pine","quill","reed","sage","tide","vale","wren","coder","ether","flare","gust","jolt","karma","lush","marsh","noble","orbit","plume","quiet","ridge","spire","tundra"]
r = random.choice

def _p1(): return r(CLU)+r(VOW)+r(SIN)+r(DVOW)
def _p2(): return r(SIN)+r(VOW)+r(SIN)+r(DVOW)
def _p3(): return r(CLU)+r(VOW)+r(SIN)+r(VOW)
def _p4(): return r(SIN)+r(VOW)+r(CLU)+r(VOW)
def _p5(): return r(CLU)+r(DVOW)+r(SIN)+r(VOW)
PATTERNS = [_p1,_p2,_p3,_p4,_p5]

def _word():
    w = r(WORDS)
    if len(w) < 5: w += r(["oo","o","a","us","ix","ia","eo","ay"])
    return w

def pretty(w):
    if not (5 <= len(w) <= 9): return False
    vs = set("aeiouy"); run = 0
    for c in w:
        if c in vs: run = 0
        else:
            run += 1
            if run >= 3: return False
    for i in range(len(w)-2):
        if w[i]==w[i+1]==w[i+2]: return False
    if w[-1] in "xqj" and w not in WORDS: return False
    return True

def score(w):
    s = 0
    if 5 <= len(w) <= 7: s += 2
    if any(w.startswith(c) for c in CLU): s += 2
    if w[-2:] in DVOW or w[-1] in "aeou": s += 2
    if 2 <= sum(c in "aeiou" for c in w) <= 4: s += 1
    if any(c*2 in w for c in "aeo"): s += 1
    return s

def candidate():
    if random.random() < 0.25: return _word(), True
    best, bs = None, -1
    for _ in range(12):
        w = r(PATTERNS)()
        if pretty(w):
            sc = score(w)
            if sc > bs: best, bs = w, sc
    if best: return best, True
    return _word(), True

def load(p):
    if os.path.exists(p):
        with open(p) as f: return json.load(f)
    return [] if p != SUBS_FILE else {}

def save(p,d):
    with open(p,"w") as f: json.dump(d,f)

usernames = load(DATA_FILE)
found = load(FOUND_FILE)
subs = load(SUBS_FILE)
LINE = "▬▬▬▬▬▬▬▬▬▬▬▬▬▬▬▬▬▬"

async def reply(u, text, kb=None):
    if len(text) > 4000: text = text[:4000] + "\n…(обрезано)"
    await u.message.reply_text(text, parse_mode="HTML", reply_markup=kb)

def only(fn):
    async def w(u,c):
        if u.effective_user.id != OWNER_ID:
            await u.message.reply_text("⛔ <b>Только для владельца</b>", parse_mode="HTML")
            return
        return await fn(u,c)
    return w

def is_sub(uid):
    if str(uid) == str(OWNER_ID): return True
    v = subs.get(str(uid))
    if not v: return False
    if v == "lifetime": return True
    try: return datetime.fromisoformat(v) > datetime.now()
    except: return False

def grant(uid, plan_key):
    p = PLANS[plan_key]
    if p["delta"] is None:
        subs[str(uid)] = "lifetime"
    else:
        cur = subs.get(str(uid))
        base = datetime.now()
        if cur and cur != "lifetime":
            try:
                d = datetime.fromisoformat(cur)
                if d > base: base = d
            except: pass
        subs[str(uid)] = (base + p["delta"]).isoformat()
    save(SUBS_FILE, subs)

def sub_status(uid):
    if str(uid) == str(OWNER_ID): return "👑 <b>Владелец (безлимит)</b>"
    v = subs.get(str(uid))
    if not v: return "❌ <b>Нет подписки</b>\n💎 Оформить: /subscribe"
    if v == "lifetime": return "💎 <b>Lifetime (навсегда)</b>"
    try:
        d = datetime.fromisoformat(v)
        left = d - datetime.now()
        if left.total_seconds() <= 0: return "❌ <b>Истекла</b>\n💎 Продлить: /subscribe"
        days = left.days
        hours = left.seconds // 3600
        minutes = (left.seconds % 3600) // 60
        return f"⏳ <b>Осталось: {days}д {hours}ч {minutes}м</b>\n💎 Истекает: {d.strftime('%d.%m.%Y %H:%M')}"
    except: return "❓ <b>Неизвестно</b>"

def require_sub(fn):
    async def w(u,c):
        if not is_sub(u.effective_user.id):
            await reply(u, f"🔒 <b>Нужна подписка</b>\n{LINE}\nЭта функция доступна по подписке.\n💎 Оформить: /subscribe")
            return
        return await fn(u,c)
    return w

# ═══════════ КНОПКИ ═══════════
def kb(uid):
    rows = [
        [InlineKeyboardButton("🎲 Генератор", callback_data="gen"),
         InlineKeyboardButton("🔄 Авто-проверка 5 шт", callback_data="autocheck")], # <-- БЕЗОПАСНЫЙ АВТОСТАРТ ДЛЯ ЮЗЕРОВ
        [InlineKeyboardButton("💎 Подписка", callback_data="sub"),
         InlineKeyboardButton("📊 Профиль", callback_data="profile")],
        [InlineKeyboardButton("💎 Мои находки", callback_data="myfound")],
    ]
    if uid == OWNER_ID:
        rows.append([InlineKeyboardButton("🛑 Автостоп" if auto_on else "🚀 Автостарт (фон)", callback_data="auto")])
    rows.append([InlineKeyboardButton("📩 Связь с разработчиком", url=OWNER_LINK)])
    return InlineKeyboardMarkup(rows)

def plans_kb():
    rows = []
    for k,p in PLANS.items():
        rows.append([InlineKeyboardButton(f"{p['name']} · {p['rub']}₽ / {p['stars']}⭐", callback_data=f"pay_{k}")])
    rows.append([InlineKeyboardButton("◀️ Назад", callback_data="back")])
    return InlineKeyboardMarkup(rows)

def pay_method_kb(plan):
    return InlineKeyboardMarkup([
        [InlineKeyboardButton("💳 CryptoBot", callback_data=f"m_crypto_{plan}"),
         InlineKeyboardButton("⭐ Stars", callback_data=f"m_stars_{plan}")],
        [InlineKeyboardButton("◀️ Назад", callback_data="sub")]
    ])

def profile_kb(uid):
    if uid == OWNER_ID:
        return InlineKeyboardMarkup([[InlineKeyboardButton("◀️ Назад", callback_data="back")]])
    return InlineKeyboardMarkup([
        [InlineKeyboardButton("💎 Оформить", callback_data="sub")],
        [InlineKeyboardButton("◀️ Назад", callback_data="back")]
    ])

HELP = ("❓ <b>Справка</b>\n"+LINE+"\n"
        "🎲 <code>/gen 10</code> — сгенерировать юзы (по подписке)\n"
        "🔄 <b>Авто-проверка</b> — безопасно проверит 5 юзов с паузой\n"
        "🔍 <code>/check name</code> — проверить 1 юз (бесплатно)\n"
        "💎 <code>/subscribe</code> — оформить подписку\n"
        "📊 <code>/profile</code> — мой профиль и подписка\n\n"
        "💡 Свободный юз забирай в настройках TG.\n"
        f"{LINE}\n👤 Разработчик: <a href=\"{OWNER_LINK}\">@faluoo</a>")

def do_gen(n):
    seen=[]; guard=0
    while len(seen)<n and guard<n*50:
        guard+=1
        w,ok=candidate()
        if ok and w not in seen: seen.append(w)
    body="\n".join(f"• <code>{w}</code> · {len(w)} букв" for w in seen)
    return f"🎲 <b>Сгенерировано {len(seen)}:</b>\n{LINE}\n{body}"

def do_found():
    if not found: return "💎 <b>Пока ничего не найдено.</b>"
    last=found[-30:]
    return f"💎 <b>Найдено: {len(found)}</b>\n{LINE}\n"+"\n".join(f"{i}. <code>@{w}</code> · {len(w)}б" for i,w in enumerate(last,1))

# ═══════════ ПРОКСИ И БЕЗОПАСНАЯ ПРОВЕРКА (СОВЕТЫ КОЛДЕЕВА) ═══════════
async def update_proxies():
    global proxy_list
    try:
        async with aiohttp.ClientSession() as session:
            async with session.get("https://api.proxyscrape.com/v2/?request=displayproxies&protocol=http&timeout=10000&country=all&ssl=all&anonymity=all", timeout=10) as resp:
                text = await resp.text()
                proxy_list = [p.strip() for p in text.split('\n') if p.strip()]
                print(f"✅ Загружено {len(proxy_list)} прокси для безопасных проверок")
    except Exception as e:
        print(f"⚠️ Не удалось загрузить прокси: {e}")

async def init_http():
    global http_session
    if not http_session:
        headers = {
            "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36",
            "Accept-Language": "ru-RU,ru;q=0.9,en-US;q=0.8,en;q=0.7",
            "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,image/webp,*/*;q=0.8"
        }
        timeout = aiohttp.ClientTimeout(total=8)
        http_session = aiohttp.ClientSession(headers=headers, timeout=timeout)

async def check1(n):
    """Безопасная проверка через HTML с рандомным прокси"""
    global http_session, proxy_list
    if not http_session: await init_http()
    if not proxy_list: await update_proxies()
    
    url = f"https://t.me/{n}"
    # Берем случайный прокси, если список есть, иначе None
    proxy = f"http://{r.choice(proxy_list)}" if proxy_list else None
    
    try:
        async with http_session.get(url, proxy=proxy, allow_redirects=True) as resp:
            text = await resp.text()
            if "Sorry, this page isn't available" in text or "Извините, эта страница недоступна" in text or resp.status == 404:
                return True  # СВОБОДЕН
            if 'property="og:title"' in text or 'tgme_page_title' in text:
                return False # ЗАНЯТ
            return False
    except Exception:
        # Если прокси сдох, пробуем без него или считаем ошибкой
        try:
            async with http_session.get(url, allow_redirects=True) as resp:
                text = await resp.text()
                if "Sorry, this page isn't available" in text or resp.status == 404: return True
                if 'property="og:title"' in text: return False
                return False
        except:
            return None

# ═══════════ CRYPTOBOT ═══════════
async def crypto_init():
    global crypto_session
    if not CRYPTO_BOT_TOKEN:
        print("⚠️ CRYPTO_BOT_TOKEN не найден в .env")
        return
    try:
        crypto_session = aiohttp.ClientSession(headers={"Crypto-Pay-API-Token": CRYPTO_BOT_TOKEN})
        print("✅ CryptoBot инициализирован")
    except Exception as e:
        print(f"❌ Ошибка CryptoBot: {e}")

async def crypto_create_invoice(amount_rub, payload):
    if not crypto_session: return None
    try:
        url = "https://pay.crypt.bot/api/createInvoice"
        async with crypto_session.post(url, json={
            "currency_type": "fiat", "fiat": "RUB", "amount": str(amount_rub),
            "paid_btn_name": "callback", "paid_btn_url": "https://t.me/faluoo",
            "paid_btn_payload": payload, "payload": payload
        }) as resp:
            data = await resp.json()
            if data.get("ok"): return data["result"]
    except Exception as e:
        print(f"❌ CryptoBot error: {e}")
    return None

async def crypto_poller(app):
    if not crypto_session: return
    seen_inv = set()
    while True:
        try:
            url = "https://pay.crypt.bot/api/getInvoices"
            async with crypto_session.get(url, params={"state":"paid"}) as resp:
                if resp.status != 200:
                    await asyncio.sleep(10); continue
                text = await resp.text()
                if not text.startswith
