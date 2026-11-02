import asyncio, os, json, random, re, time
from datetime import datetime, timedelta
from dotenv import load_dotenv
from telethon import TelegramClient
from telethon.tl.functions.account import CheckUsernameRequest
from telethon.errors import FloodWaitError, UsernameInvalidError
from telegram import (InlineKeyboardButton, InlineKeyboardMarkup,
                      LabeledPrice, PreCheckoutQuery, Update)
from telegram.ext import (Application, CommandHandler, CallbackQueryHandler,
                          PreCheckoutQueryHandler, MessageHandler, filters, ContextTypes)
from aiohttp import ClientSession

load_dotenv()
API_ID = int(os.getenv("API_ID"))
API_HASH = os.getenv("API_HASH")
BOT_TOKEN = os.getenv("BOT_TOKEN")
CRYPTO_BOT_TOKEN = os.getenv("CRYPTO_BOT_TOKEN", "")
OWNER_ID = 6288011144
OWNER_LINK = "https://t.me/faluoo"
GIFT_USERNAME = "coldeev"          # ← авто-лайфтайм этому юзу при первом /start
DATA_FILE = "usernames.json"
FOUND_FILE = "found.json"
SUBS_FILE = "subs.json"
CHECK_INTERVAL = 300
PAUSE = 4

client = TelegramClient('session', API_ID, API_HASH)
crypto_session = None
notified = set()
tried = set()
cooldown = {}
auto_on = False
_last_chk = 0

# ═══════════ ТАРИФЫ ═══════════
PLANS = {
    "1h":   {"name": "1 час",     "rub": 10,  "stars": 5,   "delta": timedelta(hours=1)},
    "1d":   {"name": "1 день",    "rub": 50,  "stars": 25,  "delta": timedelta(days=1)},
    "7d":   {"name": "7 дней",    "rub": 100, "stars": 50,  "delta": timedelta(days=7)},
    "life": {"name": "Навсегда",  "rub": 500, "stars": 250, "delta": None},
}

# ═══════════ БАЗЫ ГЕНЕРАЦИИ ═══════════
CLU  = ["fl","fr","gl","gr","pl","pr","st","sp","tr","dr","cl","cr",
        "sl","sm","sn","sw","sh","ch","th","br","bl","sk","sc","qu"]
SIN  = list("bcdfghjklmnprstvwz")
VOW  = ["a","e","i","o","u"]
DVOW = ["oo","ee","aa","ou","au","eo","ea","io","ue","oa","ia","ai","oi","ay","ey"]
WORDS = ["monk","nova","echo","zen","wolf","frost","ember","lunar","solar","storm",
         "blaze","crisp","glow","mint","jade","onyx","ruby","pearl","ashen","drift",
         "flux","halo","iris","kite","lumen","mist","opal","petal","quartz","raven",
         "sable","thorn","umber","velvet","willow","amber","brook","cedar","dune",
         "grove","haven","ivy","lark","moss","nook","oak","pine","quill","reed",
         "sage","tide","vale","wren","coder","ether","flare","gust","jolt","karma",
         "lush","marsh","noble","orbit","plume","quiet","ridge","spire","tundra"]
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

# ═══════════ ХРАНЕНИЕ ═══════════
def load(p):
    if os.path.exists(p):
        with open(p) as f: return json.load(f)
    return [] if p != SUBS_FILE else {}

def save(p,d):
    with open(p,"w") as f: json.dump(d,f)

usernames = load(DATA_FILE)
found = load(FOUND_FILE)
subs = load(SUBS_FILE)   # {"uid_str": "2026-12-01T12:00:00" | "lifetime"}

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

# ═══════════ ПОДПИСКИ ═══════════
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
    if str(uid) == str(OWNER_ID): return "👑 <b>Владелец</b>"
    v = subs.get(str(uid))
    if not v: return "❌ <b>Нет подписки</b>"
    if v == "lifetime": return "💎 <b>Lifetime</b>"
    try:
        d = datetime.fromisoformat(v)
        left = d - datetime.now()
        if left.total_seconds() <= 0: return "❌ <b>Истекла</b>"
        days = left.days; hours = left.seconds//3600
        return f"⏳ Активна: <b>{days}д {hours}ч</b>"
    except: return "❓ Неизвестно"

def require_sub(fn):
    async def w(u,c):
        if not is_sub(u.effective_user.id):
            await reply(u,
                f"🔒 <b>Нужна подписка</b>\n{LINE}\n"
                "Эта команда доступна по подписке.\n"
                "Оформи её через <code>/subscribe</code>")
            return
        return await fn(u,c)
    return w

# ═══════════ КНОПКИ ═══════════
def kb(uid):
    rows = [[InlineKeyboardButton("🎲 Сгенерировать 5", callback_data="gen"),
             InlineKeyboardButton("❓ Справка", callback_data="help")],
            [InlineKeyboardButton("💎 Подписка", callback_data="sub"),
             InlineKeyboardButton("📊 Мой статус", callback_data="status")]]
    if uid == OWNER_ID:
        rows.append([InlineKeyboardButton("📋 Слежка", callback_data="list"),
                     InlineKeyboardButton("💰 Найдено", callback_data="found")])
        rows.append([InlineKeyboardButton("🛑 Автостоп" if auto_on else "🚀 Автостарт",
                                          callback_data="auto")])
    rows.append([InlineKeyboardButton("👤 @faluoo", url=OWNER_LINK)])
    return InlineKeyboardMarkup(rows)

def plans_kb():
    rows = []
    for k,p in PLANS.items():
        rows.append([InlineKeyboardButton(
            f"{p['name']}  ·  {p['rub']}₽  /  {p['stars']}⭐",
            callback_data=f"pay_{k}")])
    rows.append([InlineKeyboardButton("◀️ Назад", callback_data="back")])
    return InlineKeyboardMarkup(rows)

def pay_method_kb(plan):
    return InlineKeyboardMarkup([[
        InlineKeyboardButton("💳 CryptoBot", callback_data=f"m_crypto_{plan}"),
        InlineKeyboardButton("⭐ Stars", callback_data=f"m_stars_{plan}"),
    ],[InlineKeyboardButton("◀️ Назад", callback_data="sub")]])

HELP = ("❓ <b>Справка</b>\n"+LINE+"\n"
        "🎲 <code>/gen 10</code> — сгенерировать юзы (нужна подписка)\n"
        "🔍 <code>/check name</code> — проверить юз (бесплатно, раз в 15 сек)\n"
        "💎 <code>/subscribe</code> — оформить подписку\n"
        "📊 <code>/status</code> — моя подписка\n\n"
        "💡 Свободный юз забирай в настройках TG:\n"
        "<i>Настройки → Изменить профиль → Имя пользователя</i>\n"
        f"{LINE}\n👤 Владелец: <a href=\"{OWNER_LINK}\">@faluoo</a>")

def do_gen(n):
    seen=[]; guard=0
    while len(seen)<n and guard<n*50:
        guard+=1
        w,ok=candidate()
        if ok and w not in seen: seen.append(w)
    body="\n".join(f"• <code>{w}</code>  ·  {len(w)} букв" for w in seen)
    return (f"🎲 <b>Сгенерировано {len(seen)}:</b>\n{LINE}\n{body}\n"
            f"{LINE}\n🔍 Проверить: <code>/check имя</code>")

def do_list():
    if not usernames: return "📭 <b>Список пуст.</b>"
    return f"📋 <b>Слежка ({len(usernames)}):</b>\n{LINE}\n"+"\n".join(f"• <code>@{x}</code>" for x in usernames)

def do_found():
    if not found: return "💎 <b>Пока ничего.</b>"
    last=found[-30:]
    return f"💎 <b>Найдено: {len(found)}</b>\n{LINE}\n"+"\n".join(f"{i}. <code>@{w}</code> · {len(w)}б" for i,w in enumerate(last,1))

# ═══════════ CRYPTOBOT API ═══════════
async def crypto_init():
    global crypto_session
    if not CRYPTO_BOT_TOKEN: return
    crypto_session = ClientSession(base_url="https://pay.crypt.bot/api",
        headers={"Crypto-Pay-API-Token": CRYPTO_BOT_TOKEN})

async def crypto_create_invoice(amount_rub, payload):
    if not crypto_session: return None
    try:
        async with crypto_session.post("createInvoice", json={
            "currency_type":"fiat","fiat":"RUB","amount":str(amount_rub),
            "paid_btn_name":"callback","paid_btn_payload":payload,
            "payload":payload
        }) as resp:
            data = await resp.json()
            if data.get("ok"): return data["result"]
    except Exception as e:
        print("CryptoBot error:", e)
    return None

async def crypto_poller(app):
    """Раз в 10 сек опрашиваем CryptoBot на новые оплаченные инвойсы"""
    if not crypto_session: return
    seen_inv = set()
    while True:
        try:
            async with crypto_session.get("getInvoices", params={"state":"paid"}) as resp:
                data = await resp.json()
            for inv in (data.get("result",{}).get("items",[]) if data.get("ok") else []):
                iid = inv["invoice_id"]
                if iid in seen_inv: continue
                seen_inv.add(iid)
                payload = inv.get("payload","")
                if payload.startswith("sub_"):
                    _,uid,plan = payload.split("_",2)
                    grant(int(uid), plan)
                    p = PLANS[plan]
                    try:
                        await app.bot.send_message(int(uid),
                            f"✅ <b>Оплата получена!</b>\n{LINE}\n💎 Подписка <b>{p['name']}</b> активирована.\n"
                            f"📊 Статус: <code>/status</code>", parse_mode="HTML")
                    except: pass
                    await app.bot.send_message(OWNER_ID,
                        f"💰 <b>+{p['rub']}₽</b> от user {uid} ({p['name']})", parse_mode="HTML")
        except Exception as e:
            print("poller err:", e)
        await asyncio.sleep(10)

# ═══════════ КОМАНДЫ ═══════════
async def start(u,c):
    user = u.effective_user
    # Авто-лайфтайм для @coldeev
    if user.username and user.username.lower() == GIFT_USERNAME.lower() and not subs.get(str(user.id)):
        grant(user.id, "life")
        await app_global.bot.send_message(OWNER_ID,
            f"🎁 <b>Авто-лайфтайм выдан</b> @{user.username} (id {user.id})", parse_mode="HTML")
    txt = (f"✨ <b>USERNAME HUNTER</b> — умный подбор красивых юзов\n{LINE}\n"
           "Генерирую читаемые имена типа <i>flouroo</i>, <i>falou</i> и проверяю свободу.\n\n"
           " <b>Бесплатно:</b> <code>/check username</code>\n"
           "💎 <b>По подписке:</b> <code>/gen</code>, слежка, автопоиск\n\n"
           f"👇 Кнопки кликабельны!")
    await reply(u, txt, kb(user.id))

async def gen(u,c):
    n=5
    if c.args:
        try: n=max(1,min(20,int(c.args[0])))
        except: pass
    await reply(u, do_gen(n))   # require_sub навешан через декоратор ниже

async def check(u,c):
    global _last_chk
    if not c.args: return await reply(u,"🔍 <b>Укажи юз:</b> <code>/check flouroo</code>")
    uid=u.effective_user.id; now=time.time()
    if now-cooldown.get(uid,0)<15:
        return await reply(u,f"⏳ Подожди ещё {int(15-(now-cooldown[uid]))} сек")
    n=c.args[0].lstrip("@").lower()
    if not re.fullmatch(r"[a-z0-9_]{4,32}",n):
        return await reply(u,"⚠️ Некорректное имя")
    cooldown[uid]=now
    wait=_last_chk+3-now
    if wait>0: await asyncio.sleep(wait)
    _last_chk=time.time()
    f=await check1(n)
    if f: txt=f"🟢 <b>@{n}</b> — СВОБОДЕН!\n💡 Забирай в настройках TG"
    elif f is None: txt=f"⚪️ <b>@{n}</b> — невалиден"
    else: txt=f"🔴 <b>@{n}</b> — занят · <a href=\"https://t.me/{n}\">профиль</a>"
    await reply(u,txt)

async def subscribe(u,c):
    await reply(u, f"💎 <b>Выбери тариф:</b>\n{LINE}", plans_kb())

async def status(u,c):
    await reply(u, f"📊 <b>Твоя подписка</b>\n{LINE}\n{sub_status(u.effective_user.id)}")

@only
async def add(u,c):
    if not c.args: return await reply(u,"➕ <code>/add username</code>")
    n=c.args[0].lstrip("@").lower()
    if n in usernames: return await reply(u,f"⚠️ @{n} уже есть")
    usernames.append(n); save(DATA_FILE,usernames)
    await reply(u,f"✅ Добавлен @{n}")

@only
async def remove(u,c):
    if not c.args: return await reply(u,"➖ <code>/remove username</code>")
    n=c.args[0].lstrip("@").lower()
    if n not in usernames: return await reply(u,f"⚠️ @{n} нет")
    usernames.remove(n); notified.discard(n); save(DATA_FILE,usernames)
    await reply(u,f"🗑 Удалён @{n}")

@only
async def lst(u,c): await reply(u, do_list())

async def check1(n,retries=3):
    for _ in range(retries):
        try: return await client(CheckUsernameRequest(username=n))
        except UsernameInvalidError: return None
        except FloodWaitError as e: await asyncio.sleep(e.seconds+1)
        except: return None
    return None

@only
async def checkall(u,c):
    if not usernames: return await reply(u,"📭 Пусто")
    m=await u.message.reply_text(f"🔍 Проверяю {len(usernames)}...",parse_mode="HTML")
    res=[]; free=busy=0
    for n in usernames:
        f=await check1(n)
        if f: res.append(f"🟢 <code>@{n}</code> — свободен!"); free+=1
        elif f is None: res.append(f"⚪️ <code>@{n}</code> — невалиден")
        else: res.append(f"🔴 <code>@{n}</code> — занят · <a href=\"https://t.me/{n}\">профиль</a>"); busy+=1
        await asyncio.sleep(PAUSE)
    text=(f"🔍 <b>Отчёт</b>\n{LINE}\n"+"\n".join(res)+f"\n{LINE}\n🟢 {free} | 🔴 {busy}")
    if len(text)>4000: text=text[:4000]+"…"
    await m.edit_text(text,parse_mode="HTML")

@only
async def autostart(u,c):
    global auto_on
    if auto_on: return await reply(u,"⚠️ Уже запущен")
    auto_on=True
    await reply(u,f"🚀 <b>Автопоиск включён</b>")

@only
async def autostop(u,c):
    global auto_on
    auto_on=False
    await reply(u,f"🛑 <b>Автопоиск выключен</b>")

@only
async def shown(u,c): await reply(u, do_found())

@only
async def give(u,c):
    """Ручная выдача: /give @username life|1h|1d|7d"""
    if not c.args or len(c.args)<2: return await reply(u,"<code>/give @username life</code>")
    uname=c.args[0].lstrip("@").lower(); plan=c.args[1].lower()
    if plan not in PLANS: return await reply(u,"План: 1h/1d/7d/life")
    # ищем uid по username через telethon
    try:
        ent = await client.get_input_entity(uname)
        uid = ent.user_id if hasattr(ent,"user_id") else ent.channel_id
    except Exception as e:
        return await reply(u,f"❌ Не нашёл юзера: {e}")
    grant(uid, plan)
    await reply(u,f"🎁 Выдано @{uname} → <b>{PLANS[plan]['name']}</b>")
    try: await app_global.bot.send_message(uid,f"🎁 Тебе выдана подписка <b>{PLANS[plan]['name']}</b>",parse_mode="HTML")
    except: pass

# ═══════════ CALLBACK ═══════════
async def cb(u,c):
    global auto_on
    q=u.callback_query; data=q.data
