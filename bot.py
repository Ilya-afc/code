import asyncio, os, json, random, re, time, hashlib
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
REF_FILE = "referrals.json"

# ⚙️ НАСТРОЙКИ
NIGHT_PAUSE = 12       # 12 секунд = 100% безопасно
AUTO_STOP_LIMIT = 9999 # Фактически безлимитно

client = TelegramClient('session', API_ID, API_HASH)
crypto_session = None
http_session = None
notified = set()
tried = set()
cooldown = {}
auto_on = False
auto_found_count = 0
_last_chk = 0
app_global = None
current_pause = NIGHT_PAUSE

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

def _p1(): return random.choice(CLU)+random.choice(VOW)+random.choice(SIN)+random.choice(DVOW)
def _p2(): return random.choice(SIN)+random.choice(VOW)+random.choice(SIN)+random.choice(DVOW)
def _p3(): return random.choice(CLU)+random.choice(VOW)+random.choice(SIN)+random.choice(VOW)
def _p4(): return random.choice(SIN)+random.choice(VOW)+random.choice(CLU)+random.choice(VOW)
def _p5(): return random.choice(CLU)+random.choice(DVOW)+random.choice(SIN)+random.choice(VOW)
PATTERNS = [_p1,_p2,_p3,_p4,_p5]

def _word():
    w = random.choice(WORDS)
    if len(w) < 5: w += random.choice(["oo","o","a","us","ix","ia","eo","ay"])
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
        w = random.choice(PATTERNS)()
        if pretty(w):
            sc = score(w)
            if sc > bs: best, bs = w, sc
    if best: return best, True
    return _word(), True

def load(p):
    if os.path.exists(p):
        with open(p) as f: return json.load(f)
    return [] if p != SUBS_FILE and p != REF_FILE else {}

def save(p,d):
    with open(p,"w") as f: json.dump(d,f)

usernames = load(DATA_FILE)
found = load(FOUND_FILE)
subs = load(SUBS_FILE)
referrals = load(REF_FILE)

LINE = "▬▬▬▬▬▬▬▬▬▬▬▬▬▬▬"

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
    if v == "lifetime": return " <b>Lifetime (навсегда)</b>"
    try:
        d = datetime.fromisoformat(v)
        left = d - datetime.now()
        if left.total_seconds() <= 0: return " <b>Истекла</b>\n💎 Продлить: /subscribe"
        days = left.days
        hours = left.seconds // 3600
        minutes = (left.seconds % 3600) // 60
        return f"⏳ <b>Осталось: {days}д {hours}ч {minutes}м</b>\n💎 Истекает: {d.strftime('%d.%m.%Y %H:%M')}"
    except: return "❓ <b>Неизвестно</b>"

def generate_captcha():
    a = random.randint(2, 15)
    b = random.randint(2, 15)
    op = random.choice(['+', '-'])
    if op == '-' and a < b:
        a, b = b, a
    answer = a + b if op == '+' else a - b
    return f"{a} {op} {b}", answer

def get_ref_code(uid):
    for code, data in referrals.items():
        if data.get("owner_id") == uid:
            return code
    code = hashlib.md5(str(uid).encode()).hexdigest()[:8]
    referrals[code] = {"owner_id": uid, "invited": [], "total_earned": 0, "pending": {}}
    save(REF_FILE, referrals)
    return code

def add_referral(ref_code, new_uid):
    if ref_code not in referrals:
        return False, "Неверная ссылка"
    ref_data = referrals[ref_code]
    owner_id = ref_data["owner_id"]
    if new_uid in ref_data["invited"] or str(new_uid) in ref_data.get("pending", {}):
        return False, "Вы уже участвуете"
    if new_uid == owner_id:
        return False, "Сам себя пригласить нельзя"
    question, answer = generate_captcha()
    if "pending" not in ref_data:
        ref_data["pending"] = {}
    ref_data["pending"][str(new_uid)] = {"answer": answer, "question": question, "attempts": 0}
    save(REF_FILE, referrals)
    return True, owner_id

def check_captcha(ref_code, new_uid, user_answer):
    if ref_code not in referrals:
        return False, "Неверная ссылка"
    ref_data = referrals[ref_code]
    owner_id = ref_data["owner_id"]
    if str(new_uid) not in ref_data.get("pending", {}):
        return False, "Капча не найдена"
    captcha_data = ref_data["pending"][str(new_uid)]
    try:
        user_answer = int(user_answer)
    except:
        return False, "Неверный формат"
    if user_answer == captcha_data["answer"]:
        del ref_data["pending"][str(new_uid)]
        ref_data["invited"].append(new_uid)
        ref_data["total_earned"] = ref_data.get("total_earned", 0) + 1
        save(REF_FILE, referrals)
        grant(owner_id, "1h")
        return True, owner_id
    else:
        captcha_data["attempts"] += 1
        save(REF_FILE, referrals)
        if captcha_data["attempts"] >= 3:
            del ref_data["pending"][str(new_uid)]
            save(REF_FILE, referrals)
            return False, "❌ Превышено количество попыток."
        return False, f"❌ Неверно! Осталось попыток: {3 - captcha_data['attempts']}"

def get_ref_stats(uid):
    for code, data in referrals.items():
        if data.get("owner_id") == uid:
            return {"code": code, "invited_count": len(data.get("invited", [])), "pending_count": len(data.get("pending", {})), "total_earned": data.get("total_earned", 0)}
    return None

# ═══════════ КНОПКИ ═══════════
def kb(uid):
    rows = [
        [InlineKeyboardButton("🎲 Генератор", callback_data="gen"), InlineKeyboardButton("🔄 Авто-проверка 5 шт", callback_data="autocheck")],
        [InlineKeyboardButton("💎 Подписка", callback_data="sub"), InlineKeyboardButton("📊 Профиль", callback_data="profile")],
        [InlineKeyboardButton("💎 Мои находки", callback_data="myfound"), InlineKeyboardButton(" Рефералы", callback_data="ref")],
    ]
    if uid == OWNER_ID and not auto_on:
        rows.append([InlineKeyboardButton("🚀 Автостарт", callback_data="auto")])
    rows.append([InlineKeyboardButton("📩 Связь", url=OWNER_LINK)])
    return InlineKeyboardMarkup(rows)

def auto_stop_kb():
    return InlineKeyboardMarkup([[InlineKeyboardButton("🛑 Остановить автостарт", callback_data="autostop")]])

def plans_kb():
    rows = [[InlineKeyboardButton(f"{p['name']} · {p['rub']}₽ / {p['stars']}⭐", callback_data=f"pay_{k}")] for k,p in PLANS.items()]
    rows.append([InlineKeyboardButton("◀️ Назад", callback_data="back")])
    return InlineKeyboardMarkup(rows)

def pay_method_kb(plan):
    return InlineKeyboardMarkup([[InlineKeyboardButton(" CryptoBot", callback_data=f"m_crypto_{plan}"), InlineKeyboardButton("⭐ Stars", callback_data=f"m_stars_{plan}")], [InlineKeyboardButton("◀️ Назад", callback_data="sub")]])

def profile_kb(uid):
    if uid == OWNER_ID:
        return InlineKeyboardMarkup([[InlineKeyboardButton("◀️ Назад", callback_data="back")]])
    return InlineKeyboardMarkup([[InlineKeyboardButton("💎 Оформить", callback_data="sub")], [InlineKeyboardButton("◀️ Назад", callback_data="back")]])

def ref_kb(uid):
    stats = get_ref_stats(uid)
    link = f"https://t.me/{app_global.bot.username}?start={stats['code']}" if stats else f"https://t.me/{app_global.bot.username}?start=ref"
    return InlineKeyboardMarkup([[InlineKeyboardButton(" Скопировать", url=link)], [InlineKeyboardButton("◀️ Назад", callback_data="back")]])

def found_filter_kb():
    return InlineKeyboardMarkup([
        [InlineKeyboardButton("⭐ Все", callback_data="filter_all"), InlineKeyboardButton("💎 6 букв", callback_data="filter_6")],
        [InlineKeyboardButton("🔥 5 букв", callback_data="filter_5"), InlineKeyboardButton("◀️ Назад", callback_data="back")]
    ])

# ═══════════ БЫСТРАЯ ПРОВЕРКА ═══════════
async def init_http():
    global http_session
    if not http_session:
        headers = {"User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36", "Accept-Language": "ru-RU"}
        http_session = aiohttp.ClientSession(headers=headers, timeout=aiohttp.ClientTimeout(total=5))

async def check1(n):
    global http_session
    if not http_session: await init_http()
    url = f"https://t.me/{n}"
    try:
        async with http_session.get(url, allow_redirects=True) as resp:
            text = await resp.text()
            if "Sorry, this page isn't available" in text or "Извините, эта страница недоступна" in text or resp.status == 404:
                return True
            if 'property="og:title"' in text or 'tgme_page_title' in text:
                return False
            return False
    except:
        return None

# ═══════════ CRYPTOBOT ═══════════
async def crypto_init():
    global crypto_session
    if not CRYPTO_BOT_TOKEN:
        print("⚠️ CRYPTO_BOT_TOKEN не найден")
        return
    try:
        crypto_session = aiohttp.ClientSession(headers={"Crypto-Pay-API-Token": CRYPTO_BOT_TOKEN})
        print("✅ CryptoBot инициализирован")
    except Exception as e:
        print(f"❌ Ошибка CryptoBot: {e}")

async def crypto_create_invoice(amount_rub, payload):
    if not crypto_session: return None
    try:
        async with crypto_session.post("https://pay.crypt.bot/api/createInvoice", json={
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
            async with crypto_session.get("https://pay.crypt.bot/api/getInvoices", params={"state":"paid"}) as resp:
                if resp.status != 200: await asyncio.sleep(10); continue
                text = await resp.text()
                if not text.startswith("{"): await asyncio.sleep(10); continue
                data = json.loads(text)
            for inv in (data.get("result",{}).get("items",[]) if data.get("ok") else []):
                iid = inv["invoice_id"]
                if iid in seen_inv or inv.get("status") != "paid": continue
                seen_inv.add(iid)
                payload = inv.get("payload","")
                if payload.startswith("sub_"):
                    _,uid,plan = payload.split("_",2)
                    grant(int(uid), plan)
                    p = PLANS[plan]
                    try:
                        await app.bot.send_message(int(uid), f"✅ <b>Оплата получена!</b>\n💎 Подписка <b>{p['name']}</b> активирована.", parse_mode="HTML")
                    except: pass
                    await app.bot.send_message(OWNER_ID, f"💰 <b>+{p['rub']}₽</b> от {uid}", parse_mode="HTML")
        except Exception as e:
            print(f"poller err: {e}")
        await asyncio.sleep(10)

# ═══════════ КОМАНДЫ ═══════════
async def start(u,c):
    user = u.effective_user
    uid = user.id
    
    if c.args and c.args[0]:
        ref_code = c.args[0]
        if ref_code != "ref":
            success, result = add_referral(ref_code, uid)
            if success:
                owner_id = result
                ref_data = referrals[ref_code]
                question = ref_data["pending"][str(uid)]["question"]
                msg = f"👋 <b>Привет!</b>\n\n🤖 <b>Проверка на бота:</b>\nРешите пример: <code>{question} = ?</code>\n\nПросто отправьте ответ числом. У вас 3 попытки!"
                await reply(u, msg)
                try:
                    await app_global.bot.send_message(owner_id, f" <b>Новый реферал!</b>\nПользователь {uid} ожидает капчу.", parse_mode="HTML")
                except: pass
                return

    if user.username and user.username.lower() == GIFT_USERNAME.lower() and not subs.get(str(user.id)):
        grant(user.id, "life")
        await app_global.bot.send_message(OWNER_ID, f"🎁 Авто-лайфтайм выдан @{user.username}", parse_mode="HTML")
    
    txt = f"✨ <b>USERNAME HUNTER</b>\n{LINE}\nГенерирую красивые юзы\n\n🆓 <b>Бесплатно:</b> /check\n💎 <b>Подписка:</b> /gen, автопоиск\n👥 <b>Рефералка:</b> +1 час за друга\n\n👇 Кнопки ниже!"
    await reply(u, txt, kb(user.id))

async def gen(u,c):
    n=5
    if c.args:
        try: n=max(1,min(20,int(c.args[0])))
        except: pass
    if not is_sub(u.effective_user.id) and n > 5:
        await reply(u, f"🔒 <b>Нужна подписка</b>\nБез подписки доступно 5 юзов.")
        n = 5
    await reply(u, do_gen(n))

async def check(u,c):
    global _last_chk
    if not c.args: return await reply(u,"🔍 Укажи юз: /check flouroo")
    uid=u.effective_user.id; now=time.time()
    if now-cooldown.get(uid,0)<8:
        return await reply(u,f"⏳ Подожди {int(8-(now-cooldown[uid]))} сек")
    n=c.args[0].lstrip("@").lower()
    if not re.fullmatch(r"[a-z0-9_]{4,32}",n):
        return await reply(u,"⚠️ Некорректное имя")
    cooldown[uid]=now
    _last_chk=time.time()
    m = await reply(u, f"🔍 Проверяю @{n}...")
    f = await check1(n)
    txt = f"🟢 <b>@{n}</b> — СВОБОДЕН!" if f else (f"⚪️ Ошибка" if f is None else f" <b>@{n}</b> — ЗАНЯТ")
    await m.edit_text(txt, parse_mode="HTML")

async def subscribe(u,c): await reply(u, f"💎 Тарифы:\n{LINE}", plans_kb())

async def profile(u,c):
    uid = u.effective_user.id
    await reply(u, f" <b>Профиль</b>\n{LINE}\n👤 ID: <code>{uid}</code>\n\n{sub_status(uid)}", profile_kb(uid))

async def myfound(u,c):
    if u.effective_user.id != OWNER_ID:
        await reply(u, do_found())
    else:
        await reply(u, f"💎 <b>Мои находки: {len(found)}</b>\n{LINE}\nНажми фильтр для сортировки.", found_filter_kb())

async def ref(u,c):
    uid = u.effective_user.id
    stats = get_ref_stats(uid)
    if not stats:
        code = get_ref_code(uid)
        stats = get_ref_stats(uid)
    link = f"https://t.me/{app_global.bot.username}?start={stats['code']}"
    text = f"👥 <b>Рефералка</b>\n{LINE}\n⏰ +1 час за друга!\n\n📊 Статистика:\n• Приглашено: <b>{stats['invited_count']}</b>\n• Ожидают капчу: <b>{stats.get('pending_count', 0)}</b>\n• Заработано: <b>{stats['total_earned']} ч</b>\n\n📎 Ссылка:\n<code>{link}</code>"
    await reply(u, text, ref_kb(uid))

@only
async def setpause(u,c):
    global current_pause
    if not c.args:
        await reply(u, f"⚙️ <b>Текущая пауза:</b> {current_pause} сек\n\nИспользование:\n<code>/setpause 12</code> — ночь (безопасно)\n<code>/setpause 6</code> — день (быстрее)")
        return
    try:
        current_pause = int(c.args[0])
        await reply(u, f"✅ Пауза установлена: <b>{current_pause} сек</b>")
    except:
        await reply(u, "⚠️ Укажите число от 1 до 30")

@only
async def rate(u,c):
    if not c.args:
        await reply(u, "📊 <b>Оценка юза:</b>\n<code>/rate username</code>")
        return
    n = c.args[0].lstrip("@").lower()
    s = score(n)
    rating = "💎 РЕДКИЙ" if s >= 8 else ("✨ Хороший" if s >= 5 else "⚪️ Обычный")
    await reply(u, f"📊 <b>Оценка @{n}</b>\n{LINE}\n• Длина: {len(n)} букв\n• Сложность: {s}/10\n• Статус: {rating}")

@only
async def add(u,c):
    if not c.args: return await reply(u,"➕ /add username")
    n=c.args[0].lstrip("@").lower()
    if n in usernames: return await reply(u,f"⚠️ @{n} уже есть")
    usernames.append(n); save(DATA_FILE,usernames)
    await reply(u,f"✅ Добавлен @{n}")

@only
async def remove(u,c):
    if not c.args: return await reply(u,"➖ /remove username")
    n=c.args[0].lstrip("@").lower()
    if n not in usernames: return await reply(u,f"⚠️ @{n} нет")
    usernames.remove(n); notified.discard(n); save(DATA_FILE,usernames)
    await reply(u,f"🗑 Удалён @{n}")

@only
async def autostart(u,c):
    global auto_on, auto_found_count
    if auto_on: return await reply(u,"⚠️ Уже запущен")
    auto_on = True
    auto_found_count = 0
    await reply(u, f"🚀 <b>Автостарт запущен!</b>\n⏸ Пауза: {current_pause} сек\n♾️ Работает бесконечно", auto_stop_kb())

@only
async def autostop(u,c):
    global auto_on
    auto_on = False
    await reply(u, f"🛑 <b>Автостоп</b>\n Найдено за сессию: {auto_found_count}\n📊 Всего в базе: {len(found)}")

@only
async def give(u,c):
    if not c.args or len(c.args)<2: return await reply(u,"/give @user life|1h|1d|7d")
    uname=c.args[0].lstrip("@").lower(); plan=c.args[1].lower()
    if plan not in PLANS: return await reply(u,"План: 1h/1d/7d/life")
    try:
        ent = await client.get_input_entity(uname)
        uid = ent.user_id
    except Exception as e:
        return await reply(u,f"❌ Не нашёл: {e}")
    grant(uid, plan)
    await reply(u,f"🎁 Выдано @{uname} → {PLANS[plan]['name']}")

async def handle_captcha(u,c):
    uid = u.effective_user.id
    text = u.message.text.strip()
    for ref_code, data in referrals.items():
        if str(uid) in data.get("pending", {}):
            success, result = check_captcha(ref_code, uid, text)
            if success:
                owner_id = result
                await reply(u, f"✅ <b>Капча решена!</b>\nБонус другу начислен +1 час!", kb(uid))
                try:
                    await app_global.bot.send_message(owner_id, f"🎉 <b>Бонус!</b>\nДруг {uid} решил капчу.\n⏰ +1 час начислено!", parse_mode="HTML")
                except: pass
            else:
                await reply(u, result)
            return

# ═══════════ CALLBACK ═══════════
async def cb(u,c):
    global auto_on, auto_found_count
    q=u.callback_query
    data=q.data
    uid=u.effective_user.id
    
    # ⚡ МГНОВЕННЫЙ ОТВЕТ
    await q.answer()
    
    # Проверка капчи
    for ref_code, data_ref in referrals.items():
        if str(uid) in data_ref.get("pending", {}):
            if data not in ["ref", "profile", "back"]:
                await q.message.reply_text("🤖 <b>Сначала решите капчу!</b>")
                return
    
    if data=="gen":
        if not is_sub(uid):
            await q.message.reply_text("🔒 <b>Нужна подписка</b>")
            return
        await q.message.reply_text(do_gen(5), parse_mode="HTML")
        
    elif data=="autocheck":
        if not is_sub(uid):
            await q.message.reply_text("🔒 <b>Нужна подписка</b>")
            return
        await q.message.reply_text("🔄 Проверяю 5 юзов...")
        results = []
        for _ in range(5):
            w, ok = candidate()
            if not ok: continue
            f = await check1(w)
            if f: results.append(f"🟢 <code>@{w}</code>")
            else: results.append(f"🔴 <code>@{w}</code>")
            await asyncio.sleep(0.5)
        await q.message.reply_text("✅ " + "\n".join(results), parse_mode="HTML")

    elif data=="sub":
        await q.message.reply_text(f"💎 Тарифы:\n1ч — 10₽\n1д — 50₽\n7д — 100₽\n∞ — 500₽", reply_markup=plans_kb())
        
    elif data=="profile":
        await q.message.reply_text(f"📊 Профиль\n{sub_status(uid)}", parse_mode="HTML", reply_markup=profile_kb(uid))
        
    elif data=="myfound":
        if uid != OWNER_ID:
            await q.message.reply_text(do_found(), parse_mode="HTML")
        else:
            await q.message.reply_text(f"💎 Найдено: {len(found)}", reply_markup=found_filter_kb())
        
    elif data=="ref":
        await ref(u,c)
        
    elif data=="back":
        await q.message.reply_text(f"✨ <b>USERNAME HUNTER</b>", parse_mode="HTML", reply_markup=kb(uid))
        
    elif data=="autostop":
        if uid != OWNER_ID: return
        auto_on = False
        await q.message.reply_text(f"🛑 <b>Автостоп</b>\nНайдено: {auto_found_count}", reply_markup=kb(uid))
        
    elif data.startswith("filter_"):
        if uid != OWNER_ID: return
        ftype = data[7:]
        if ftype == "all":
            filtered = found[-20:]
        elif ftype == "6":
            filtered = [w for w in found[-20:] if len(w) == 6]
        elif ftype == "5":
            filtered = [w for w in found[-20:] if len(w) == 5]
        else:
            filtered = found[-20:]
        text = f"💎 <b>Фильтр: {ftype}</b>\n{LINE}\n" + "\n".join(f"<code>@{w}</code> · {len(w)}б · ⭐ {score(w)}" for w in filtered) if filtered else "Пусто"
        await q.message.reply_text(text, parse_mode="HTML", reply_markup=found_filter_kb())
        
    elif data.startswith("pay_"):
        plan=data[4:]; p=PLANS[plan]
        await q.message.reply_text(f"💎 {p['name']} — {p['rub']}₽", reply_markup=pay_method_kb(plan))
        
    elif data.startswith("m_crypto_"):
        plan=data[9:]; p=PLANS[plan]
        if not CRYPTO_BOT_TOKEN:
            await q.message.reply_text("CryptoBot не настроен")
            return
        inv=await crypto_create_invoice(p["rub"], f"sub_{uid}_{plan}")
        if inv:
            await q.message.reply_text(f"💳 <a href=\"{inv['pay_url']}\">Оплатить {p['rub']}₽</a>", parse_mode="HTML")
            
    elif data.startswith("m_stars_"):
        plan=data[8:]; p=PLANS[plan]
        try:
            await q.message.reply_invoice(title=f"Подписка {p['name']}",payload=f"sub_{uid}_{plan}",provider_token="",currency="XTR",prices=[LabeledPrice(label=p["name"], amount=p["stars"])])
        except Exception as e:
            await q.message.reply_text(f"❌ Stars: {e}")
            
    elif data=="auto":
        if uid != OWNER_ID: return
        auto_on = not auto_on
        auto_found_count = 0
        if auto_on:
            await q.message.reply_text(f"🚀 <b>Автостарт ВКЛ</b>\n⏸ Пауза: {current_pause} сек\n♾️ Работает бесконечно", reply_markup=auto_stop_kb())
        else:
            await q.message.reply_text("🛑 <b>Автостоп</b>", reply_markup=kb(uid))

async def precheckout(u,c): await u.pre_checkout_query.answer(ok=True)
async def successful_payment(u,c):
    msg=u.effective_message; payload=msg.successful_payment.invoice_payload
    if payload.startswith("sub_"):
        _,uid,plan=payload.split("_",2); grant(int(uid),plan); p=PLANS[plan]
        await msg.reply_text(f"✅ Оплата! {p['name']} активирована.", parse_mode="HTML")

# ═══════════ ФОН ═══════════
async def monitor(app):
    while True:
        for n in list(usernames):
            f=await check1(n)
            if f and n not in notified:
                notified.add(n)
                await app.bot.send_message(OWNER_ID, f"🎉 <b>@{n} ОСВОБОДИЛСЯ!</b>", parse_mode="HTML")
            await asyncio.sleep(3)
        await asyncio.sleep(CHECK_INTERVAL)

async def searcher(app):
    global tried, auto_on, auto_found_count, current_pause
    while True:
        if auto_on:
            cand, ok = candidate()
            if not ok or cand in tried:
                await asyncio.sleep(1)
                continue
            tried.add(cand)
            if len(tried) > 200000: tried.clear()
            f = await check1(cand)
            if f:
                found.append(cand); save(FOUND_FILE, found)
                auto_found_count += 1
                s = score(cand)
                tag = "💎 РЕДКИЙ!" if s >= 8 else ("✨" if s >= 5 else "")
                await app.bot.send_message(OWNER_ID, f"{tag} <code>@{cand}</code> ({len(cand)}б) · ⭐ {s}", parse_mode="HTML")
            await asyncio.sleep(current_pause)
        else:
            await asyncio.sleep(2)

async def main():
    global app_global
    await init_http()
    await client.start()
    await crypto_init()
    app = Application.builder().token(BOT_TOKEN).build()
    app_global = app
    app.add_handler(CommandHandler("start", start))
    app.add_handler(CommandHandler("gen", gen))
    app.add_handler(CommandHandler("check", check))
    app.add_handler(CommandHandler("subscribe", subscribe))
    app.add_handler(CommandHandler("profile", profile))
    app.add_handler(CommandHandler("myfound", myfound))
    app.add_handler(CommandHandler("ref", ref))
    app.add_handler(CommandHandler("add", add))
    app.add_handler(CommandHandler("remove", remove))
    app.add_handler(CommandHandler("autostart", autostart))
    app.add_handler(CommandHandler("autostop", autostop))
    app.add_handler(CommandHandler("setpause", setpause))
    app.add_handler(CommandHandler("rate", rate))
    app.add_handler(CommandHandler("give", give))
    app.add_handler(MessageHandler(filters.TEXT & ~filters.COMMAND, handle_captcha))
    app.add_handler(CallbackQueryHandler(cb))
    app.add_handler(PreCheckoutQueryHandler(precheckout))
    app.add_handler(MessageHandler(filters.SUCCESSFUL_PAYMENT, successful_payment))
    await app.initialize(); await app.start(); await app.updater.start_polling()
    print("🚀 Бот запущен")
    print(f"⏸ Пауза: {current_pause} сек (100% безопасно)")
    print("♾️ Автостоп отключён — работает бесконечно")
    try:
        await asyncio.gather(monitor(app), searcher(app), crypto_poller(app))
    finally:
        await app.updater.stop(); await app.stop(); await app.shutdown()

asyncio.run(main())
