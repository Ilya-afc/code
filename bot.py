import asyncio, os, json, random, re, time
from datetime import datetime, timedelta
from dotenv import load_dotenv
from telethon import TelegramClient
from telethon.tl.functions.account import CheckUsernameRequest
from telethon.errors import FloodWaitError, UsernameInvalidError
from telegram import InlineKeyboardButton, InlineKeyboardMarkup, LabeledPrice
from telegram.ext import Application, CommandHandler, CallbackQueryHandler, PreCheckoutQueryHandler, MessageHandler, filters

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
notified = set()
tried = set()
cooldown = {}
auto_on = False
_last_chk = 0
app_global = None

# ═══════════ ТАРИФЫ ═══════════
PLANS = {
    "1h":   {"name": "1 час",     "rub": 10,  "stars": 5,   "delta": timedelta(hours=1)},
    "1d":   {"name": "1 день",    "rub": 50,  "stars": 25,  "delta": timedelta(days=1)},
    "7d":   {"name": "7 дней",    "rub": 100, "stars": 50,  "delta": timedelta(days=7)},
    "life": {"name": "Навсегда",  "rub": 500, "stars": 250, "delta": None},
}

# ═══════════ БАЗЫ ГЕНЕРАЦИИ ═══════════
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

# ═══════════ ХРАНЕНИЕ ═══════════
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
            await reply(u, f" <b>Нужна подписка</b>\n{LINE}\nЭта функция доступна по подписке.\n💎 Оформить: /subscribe")
            return
        return await fn(u,c)
    return w

# ═══════════ КНОПКИ ═══════════
def kb(uid):
    rows = [
        [InlineKeyboardButton("🎲 Генератор", callback_data="gen"),
         InlineKeyboardButton("🔍 Проверить", callback_data="check_btn")],
        [InlineKeyboardButton("💎 Подписка", callback_data="sub"),
         InlineKeyboardButton("📊 Профиль", callback_data="profile")]
    ]
    if uid == OWNER_ID:
        rows.append([InlineKeyboardButton("📋 Слежка", callback_data="list"),
                     InlineKeyboardButton("💎 Найдено", callback_data="found")])
        rows.append([InlineKeyboardButton("🛑 Автостоп" if auto_on else "🚀 Автостарт", callback_data="auto")])
    rows.append([InlineKeyboardButton("👤 @faluoo", url=OWNER_LINK)])
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
        "🔍 <code>/check name</code> — проверить юз (бесплатно, раз в 15 сек)\n"
        "💎 <code>/subscribe</code> — оформить подписку\n"
        " <code>/profile</code> — мой профиль и подписка\n\n"
        "💡 Свободный юз забирай в настройках TG:\n<i>Настройки → Профиль → Имя пользователя</i>\n"
        f"{LINE}\n👤 Владелец: <a href=\"{OWNER_LINK}\">@faluoo</a>")

def do_gen(n):
    seen=[]; guard=0
    while len(seen)<n and guard<n*50:
        guard+=1
        w,ok=candidate()
        if ok and w not in seen: seen.append(w)
    body="\n".join(f"• <code>{w}</code> · {len(w)} букв" for w in seen)
    return f" <b>Сгенерировано {len(seen)}:</b>\n{LINE}\n{body}\n{LINE}\n🔍 Проверить: <code>/check имя</code>"

def do_list():
    if not usernames: return " <b>Список пуст.</b>"
    return f"📋 <b>Слежка ({len(usernames)}):</b>\n{LINE}\n"+"\n".join(f"• <code>@{x}</code>" for x in usernames)

def do_found():
    if not found: return "💎 <b>Пока ничего.</b>"
    last=found[-30:]
    return f"💎 <b>Найдено: {len(found)}</b>\n{LINE}\n"+"\n".join(f"{i}. <code>@{w}</code> · {len(w)}б" for i,w in enumerate(last,1))

# ═══════════ CRYPTOBOT ═══════════
async def crypto_init():
    global crypto_session
    if not CRYPTO_BOT_TOKEN: return
    try:
        from aiohttp import ClientSession
        crypto_session = ClientSession(base_url="https://pay.crypt.bot/api", headers={"Crypto-Pay-API-Token": CRYPTO_BOT_TOKEN})
    except: pass

async def crypto_create_invoice(amount_rub, payload):
    if not crypto_session: return None
    try:
        async with crypto_session.post("createInvoice", json={"currency_type":"fiat","fiat":"RUB","amount":str(amount_rub),"paid_btn_name":"callback","paid_btn_payload":payload,"payload":payload}) as resp:
            data = await resp.json()
            if data.get("ok"): return data["result"]
    except Exception as e:
        print("CryptoBot error:", e)
    return None

async def crypto_poller(app):
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
                        await app.bot.send_message(int(uid), f"✅ <b>Оплата получена!</b>\n{LINE}\n💎 Подписка <b>{p['name']}</b> активирована.\n📊 /profile", parse_mode="HTML")
                    except: pass
                    await app.bot.send_message(OWNER_ID, f"💰 <b>+{p['rub']}₽</b> от user {uid} ({p['name']})", parse_mode="HTML")
        except Exception as e:
            print("poller err:", e)
        await asyncio.sleep(10)

# ═══════════ КОМАНДЫ ═══════════
async def start(u,c):
    user = u.effective_user
    if user.username and user.username.lower() == GIFT_USERNAME.lower() and not subs.get(str(user.id)):
        grant(user.id, "life")
        await app_global.bot.send_message(OWNER_ID, f"🎁 <b>Авто-лайфтайм выдан</b> @{user.username} (id {user.id})", parse_mode="HTML")
        try:
            await app_global.bot.send_message(user.id, f"🎉 <b>Тебе выдан Lifetime!</b>\n{LINE}\n💎 Все функции бота теперь доступны навсегда.\n📊 /profile", parse_mode="HTML")
        except: pass
    txt = (f"✨ <b>USERNAME HUNTER</b> — умный подбор красивых юзов\n{LINE}\n"
           "Генерирую читаемые имена типа <i>flouroo</i>, <i>falou</i> и проверяю свободу.\n\n"
           "🆓 <b>Бесплатно:</b> <code>/check username</code>\n"
           "💎 <b>По подписке:</b> <code>/gen</code>, слежка, автопоиск\n\n"
           f" Кнопки кликабельны!")
    await reply(u, txt, kb(user.id))

async def gen(u,c):
    n=5
    if c.args:
        try: n=max(1,min(20,int(c.args[0])))
        except: pass
    await reply(u, do_gen(n))

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
    if f: txt=f" <b>@{n}</b> — СВОБОДЕН!\n💡 Забирай в настройках TG"
    elif f is None: txt=f"⚪️ <b>@{n}</b> — невалиден"
    else: txt=f"🔴 <b>@{n}</b> — занят · <a href=\"https://t.me/{n}\">профиль</a>"
    await reply(u,txt)

async def subscribe(u,c):
    await reply(u, f"💎 <b>Выбери тариф:</b>\n{LINE}", plans_kb())

async def profile(u,c):
    uid = u.effective_user.id
    status_text = sub_status(uid)
    await reply(u, f"📊 <b>Твой профиль</b>\n{LINE}\n👤 ID: <code>{uid}</code>\n\n{status_text}", profile_kb(uid))

async def check_btn(u,c):
    await reply(u, "🔍 <b>Проверить юз:</b>\n\nОтправь команду:\n<code>/check username</code>\n\nИли напиши юз прямо сюда — я проверю.", parse_mode="HTML")

@only
async def add(u,c):
    if not c.args: return await reply(u," <code>/add username</code>")
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
    text=(f"🔍 <b>Отчёт</b>\n{LINE}\n"+"\n".join(res)+f"\n{LINE}\n {free} | 🔴 {busy}")
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
    await reply(u,f"🛑 <b>Автопоиск выключен</b>\n💎 Найдено: {len(found)}")

@only
async def shown(u,c): await reply(u, do_found())

@only
async def give(u,c):
    """Только владелец может выдавать подписки"""
    if not c.args or len(c.args)<2: return await reply(u,"<code>/give @username life|1h|1d|7d</code>")
    uname=c.args[0].lstrip("@").lower(); plan=c.args[1].lower()
    if plan not in PLANS: return await reply(u,"План: 1h/1d/7d/life")
    try:
        ent = await client.get_input_entity(uname)
        uid = ent.user_id if hasattr(ent,"user_id") else ent.channel_id
    except Exception as e:
        return await reply(u,f"❌ Не нашёл юзера: {e}")
    grant(uid, plan)
    await reply(u,f"🎁 Выдано @{uname} → <b>{PLANS[plan]['name']}</b>")
    try: await app_global.bot.send_message(uid,f"🎁 Тебе выдана подписка <b>{PLANS[plan]['name']}</b>\n📊 /profile",parse_mode="HTML")
    except: pass

# ══════════ CALLBACK ═══════════
async def cb(u,c):
    global auto_on
    q=u.callback_query; data=q.data; uid=u.effective_user.id
    if data=="gen":
        if not is_sub(uid):
            await q.answer("🔒 Нужна подписка",show_alert=True)
            await q.message.reply_text("💎 Оформить: /subscribe",parse_mode="HTML"); return
        await q.answer("Генерирую...")
        await q.message.reply_text(do_gen(5),parse_mode="HTML")
    elif data=="check_btn":
        await q.answer()
        await q.message.reply_text("🔍 <b>Проверить юз:</b>\n\nОтправь команду:\n<code>/check username</code>", parse_mode="HTML")
    elif data=="help":
        await q.answer(); await q.message.reply_text(HELP,parse_mode="HTML")
    elif data=="sub":
        await q.answer(); await q.edit_message_text(f"💎 <b>Тарифы:</b>\n{LINE}\n\n1ч — 10₽ / 5⭐\n1д — 50₽ / 25⭐\n7д — 100₽ / 50⭐\n — 500₽ / 250⭐",parse_mode="HTML",reply_markup=plans_kb())
    elif data=="profile":
        await q.answer()
        await q.message.reply_text(f"📊 <b>Твой профиль</b>\n{LINE}\n👤 ID: <code>{uid}</code>\n\n{sub_status(uid)}", parse_mode="HTML", reply_markup=profile_kb(uid))
    elif data=="back":
        await q.answer(); await q.edit_message_text("✨ Меню",parse_mode="HTML",reply_markup=kb(uid))
    elif data.startswith("pay_"):
        plan=data[4:]
        p=PLANS[plan]
        await q.answer()
        await q.edit_message_text(f"💎 <b>{p['name']}</b>\n{LINE}\n💰 {p['rub']}₽  |  ⭐ {p['stars']} Stars\n\nВыбери способ оплаты:",parse_mode="HTML", reply_markup=pay_method_kb(plan))
    elif data.startswith("m_crypto_"):
        plan=data[9:]
        p=PLANS[plan]
        if not CRYPTO_BOT_TOKEN:
            await q.answer("CryptoBot не настроен",show_alert=True); return
        await q.answer("Создаю счёт...")
        inv=await crypto_create_invoice(p["rub"], f"sub_{uid}_{plan}")
        if inv:
            await q.message.reply_text(f"💳 <b>Оплати {p['rub']}₽</b>\n{LINE}\n👉 <a href=\"{inv['pay_url']}\">Перейти к оплате</a>\n\nПосле оплаты подписка активируется автоматически.",parse_mode="HTML")
        else:
            await q.message.reply_text("❌ Не удалось создать счёт. Попробуй Stars.",parse_mode="HTML")
    elif data.startswith("m_stars_"):
        plan=data[8:]
        p=PLANS[plan]
        await q.answer()
        try:
            await q.message.reply_invoice(title=f"Подписка {p['name']}",description=f"Username Hunter — {p['name']}",payload=f"sub_{uid}_{plan}",provider_token="",currency="XTR",prices=[LabeledPrice(label=p["name"], amount=p["stars"])])
        except Exception as e:
            await q.message.reply_text(f"❌ Stars недоступны: {e}",parse_mode="HTML")
    elif data in ("list","found"):
        if uid!=OWNER_ID: return await q.answer("⛔ Только владелец",show_alert=True)
        await q.answer()
        await q.message.reply_text(do_list() if data=="list" else do_found(),parse_mode="HTML")
    elif data=="auto":
        if uid!=OWNER_ID: return await q.answer("⛔ Только владелец",show_alert=True)
        auto_on=not auto_on
        await q.edit_message_reply_markup(reply_markup=kb(uid))
        await q.answer("🚀 ВКЛ" if auto_on else "🛑 ВЫКЛ")

async def precheckout(u,c):
    await u.pre_checkout_query.answer(ok=True)

async def successful_payment(u,c):
    msg=u.effective_message
    payload=msg.successful_payment.invoice_payload
    if payload.startswith("sub_"):
        _,uid,plan=payload.split("_",2)
        grant(int(uid),plan)
        p=PLANS[plan]
        await msg.reply_text(f"✅ <b>Оплата Stars получена!</b>\n{LINE}\n💎 Подписка <b>{p['name']}</b> активирована.\n📊 /profile",parse_mode="HTML")
        await c.bot.send_message(OWNER_ID,f"⭐ <b>+{p['stars']} Stars</b> от {uid} ({p['name']})",parse_mode="HTML")

# ═══════════ ФОН ═══════════
async def monitor(app):
    while True:
        for n in list(usernames):
            f=await check1(n)
            if f and n not in notified:
                notified.add(n)
                await app.bot.send_message(OWNER_ID,f" <b>@{n} ОСВОБОДИЛСЯ!</b>",parse_mode="HTML")
            await asyncio.sleep(PAUSE)
        await asyncio.sleep(CHECK_INTERVAL)

async def searcher(app):
    global tried
    while True:
        if auto_on:
            cand,ok=candidate()
            if not ok or cand in tried: await asyncio.sleep(0.2); continue
            tried.add(cand)
            if len(tried)>200000: tried.clear()
            f=await check1(cand)
            if f:
                found.append(cand); save(FOUND_FILE,found)
                tag="💎 РЕДКИЙ!" if len(cand)<=6 else "✨ Красивый"
                await app.bot.send_message(OWNER_ID,f"{tag} <code>@{cand}</code> ({len(cand)}б)",parse_mode="HTML")
                await asyncio.sleep(PAUSE)
            else: await asyncio.sleep(2)
        else: await asyncio.sleep(2)

async def main():
    global app_global
    await client.start()
    await crypto_init()
    app = Application.builder().token(BOT_TOKEN).build()
    app_global = app
    app.add_handler(CommandHandler("start", start))
    app.add_handler(CommandHandler("gen", require_sub(gen)))
    app.add_handler(CommandHandler("check", check))
    app.add_handler(CommandHandler("subscribe", subscribe))
    app.add_handler(CommandHandler("profile", profile))
    app.add_handler(CommandHandler("add", add))
    app.add_handler(CommandHandler("remove", remove))
    app.add_handler(CommandHandler("list", lst))
    app.add_handler(CommandHandler("checkall", checkall))
    app.add_handler(CommandHandler("autostart", autostart))
    app.add_handler(CommandHandler("autostop", autostop))
    app.add_handler(CommandHandler("found", shown))
    app.add_handler(CommandHandler("give", give))
    app.add_handler(CallbackQueryHandler(cb))
    app.add_handler(PreCheckoutQueryHandler(precheckout))
    app.add_handler(MessageHandler(filters.SUCCESSFUL_PAYMENT, successful_payment))
    await app.initialize(); await app.start(); await app.updater.start_polling()
    print(" Бот запущен")
    try:
        await asyncio.gather(monitor(app), searcher(app), crypto_poller(app))
    finally:
        await app.updater.stop(); await app.stop(); await app.shutdown()

asyncio.run(main())
