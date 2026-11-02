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
CHECK_INTERVAL = 300
AUTO_PAUSE = 10  # ⏱️ Жесткая задержка 10 секунд для автостарта

client = TelegramClient('session', API_ID, API_HASH)
crypto_session = None
http_session = None
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

def generate_captcha():
    a = random.randint(2, 15)
    b = random.randint(2, 15)
    op = random.choice(['+', '-'])
    if op == '-' and a < b: a, b = b, a
    answer = a + b if op == '+' else a - b
    return f"{a} {op} {b}", answer

def get_ref_code(uid):
    for code, data in referrals.items():
        if data.get("owner_id") == uid: return code
    code = hashlib.md5(str(uid).encode()).hexdigest()[:8]
    referrals[code] = {"owner_id": uid, "invited": [], "total_earned": 0, "pending": {}}
    save(REF_FILE, referrals)
    return code

def add_referral(ref_code, new_uid):
    if ref_code not in referrals: return False, "Неверная ссылка"
    ref_data = referrals[ref_code]
    owner_id = ref_data["owner_id"]
    if new_uid in ref_data["invited"] or str(new_uid) in ref_data.get("pending", {}): return False, "Вы уже участвуете"
    if new_uid == owner_id: return False, "Сам себя пригласить нельзя"
    question, answer = generate_captcha()
    if "pending" not in ref_data: ref_data["pending"] = {}
    ref_data["pending"][str(new_uid)] = {"answer": answer, "question": question, "attempts": 0}
    save(REF_FILE, referrals)
    return True, owner_id

def check_captcha(ref_code, new_uid, user_answer):
    if ref_code not in referrals: return False, "Неверная ссылка"
    ref_data = referrals[ref_code]
    owner_id = ref_data["owner_id"]
    if str(new_uid) not in ref_data.get("pending", {}): return False, "Капча не найдена"
    captcha_data = ref_data["pending"][str(new_uid)]
    try: user_answer = int(user_answer)
    except: return False, "Неверный формат"
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

# ═══════════ КНОПКИ ═══════════
def kb(uid):
    rows = [
        [InlineKeyboardButton("🎲 Генератор", callback_data="gen"), InlineKeyboardButton("🔄 Авто-проверка 5 шт", callback_data="autocheck")],
        [InlineKeyboardButton("💎 Подписка", callback_data="sub"), InlineKeyboardButton("📊 Профиль", callback_data="profile")],
        [InlineKeyboardButton("💎 Мои находки", callback_data="myfound"), InlineKeyboardButton("👥 Рефералы", callback_data="ref")],
    ]
    if uid == OWNER_ID:
        rows.append([InlineKeyboardButton("🛑 Автостоп" if auto_on else "🚀 Автостарт", callback_data="auto")])
    rows.append([InlineKeyboardButton("📩 Связь с разработчиком", url=OWNER_LINK)])
    return InlineKeyboardMarkup(rows)

def plans_kb():
    rows = [[InlineKeyboardButton(f"{p['name']} · {p['rub']}₽ / {p['stars']}⭐", callback_data=f"pay_{k}")] for k,p in PLANS.items()]
    rows.append([InlineKeyboardButton("◀️ Назад", callback_data="back")])
    return InlineKeyboardMarkup(rows)

def pay_method_kb(plan):
    return InlineKeyboardMarkup([[InlineKeyboardButton("💳 CryptoBot", callback_data=f"m_crypto_{plan}"), InlineKeyboardButton("⭐ Stars", callback_data=f"m_stars_{plan}")], [InlineKeyboardButton("◀️ Назад", callback_data="sub")]])

def profile_kb(uid):
    if uid == OWNER_ID: return InlineKeyboardMarkup([[InlineKeyboardButton("◀️ Назад", callback_data="back")]])
    return InlineKeyboardMarkup([[InlineKeyboardButton("💎 Оформить", callback_data="sub")], [InlineKeyboardButton("◀️ Назад", callback_data="back")]])

def ref_kb(uid):
    stats = get_ref_stats(uid)
    link = f"https://t.me/{app_global.bot.username}?start={stats['code']}" if stats else f"https://t.me/{app_global
