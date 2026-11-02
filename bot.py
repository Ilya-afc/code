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

# ═══════════ ХРАНЕНИЕ ДАННЫХ ═══════════
def load(p):
    if os.path.exists(p):
        with open(p) as f: return json.load(f)
    return [] if p != SUBS_FILE and p != REF_FILE else {}

def save(p,d):
    with open(p,"w") as f: json.dump(d,f)

usernames = load(DATA_FILE)
found = load(FOUND_FILE)
subs = load(SUBS_FILE)
referrals = load(REF_FILE)  # {"ref_code": {"owner_id": 123, "invited": [456, 789]}}

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

def require_sub(fn):
    async def w(u,c):
        if not is_sub(u.effective_user.id):
            await reply(u, f"🔒 <b>Нужна подписка</b>\n{LINE}\nЭта функция доступна по подписке.\n💎 Оформить: /subscribe\n🎁 Или пригласи друга: /ref")
            return
        return await fn(u,c)
    return w

# ═══════════ РЕФЕРАЛЬНАЯ СИСТЕМА ═══════════
def get_ref_code(uid):
    """Получить или создать реф-код для пользователя"""
    for code, data in referrals.items():
        if data.get("owner_id") == uid:
            return code
    # Создаём новый код
    code = hashlib.md5(str(uid).encode()).hexdigest()[:8]
    referrals[code] = {"owner_id": uid, "invited": [], "total_earned": 0}
    save(REF_FILE, referrals)
    return code

def add_referral(ref_code, new_uid):
    """Добавить реферала и наградить владельца"""
    if ref_code not in referrals:
        return False, "Неверная ссылка"
    
    ref_data = referrals[ref_code]
    owner_id = ref_data["owner_id"]
    
    # Проверяем что новый юзер ещё не был приглашён
    if new_uid in ref_data["invited"]:
        return False, "Вы уже были приглашены"
    
    # Проверяем что это не сам владелец
    if new_uid == owner_id:
        return False, "Нельзя пригласить самого себя"
    
    # Добавляем реферала
    ref_data["invited"].append(new_uid)
    ref_data["total_earned"] = ref_data.get("total_earned", 0) + 1
    save(REF_FILE, referrals)
    
    # Награждаем владельца +1 час
    grant(owner_id, "1h")
    
    return True, owner_id

def get_ref_stats(uid):
    """Получить статистику рефералов пользователя"""
    for code, data in referrals.items():
        if data.get("owner_id") == uid:
            return {
                "code": code,
                "invited_count": len(data.get("invited", [])),
                "total_earned": data.get("total_earned", 0)
            }
    return None

# ═══════════ КНОПКИ ═══════════
def kb(uid):
    rows = [
        [InlineKeyboardButton("🎲 Генератор", callback_data="gen"),
         InlineKeyboardButton("🔄 Авто-проверка 5 шт", callback_data="autocheck")],
        [InlineKeyboardButton("💎 Подписка", callback_data="sub"),
         InlineKeyboardButton("📊 Профиль", callback_data="profile")],
        [InlineKeyboardButton("💎 Мои находки", callback_data="myfound"),
         InlineKeyboardButton(" Рефералы", callback_data="ref")],
    ]
    if uid == OWNER_ID:
        rows.append([InlineKeyboardButton(" Автостоп" if auto_on else " Автостарт (фон)", callback_data="auto")])
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
        [InlineKeyboardButton(" CryptoBot", callback_data=f"m_crypto_{plan}"),
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

def ref_kb(uid):
    stats = get_ref_stats(uid)
    if stats:
        link = f"https://t.me/{app_global.bot.username}?start={stats['code']}"
    else:
        link = f"https://t.me/{app_global.bot.username}?start=ref"
    return InlineKeyboardMarkup([
        [InlineKeyboardButton("📋 Скопировать ссылку", url=link)],
        [InlineKeyboardButton("◀️ Назад", callback_data="back")]
    ])

HELP = ("❓ <b>Справка</b>\n"+LINE+"\n"
        "🎲 <code>/gen 10</code> — сгенерировать юзы (по подписке)\n"
        "🔄 <b>Авто-проверка</b> — безопасно проверит 5 юзов с паузой\n"
        " <code>/check name</code> — проверить 1 юз (бесплатно)\n"
        "💎 <code>/subscribe</code> — оформить подписку\n"
        "👥 <code>/ref</code> — пригласить друга и получить +1 час\n"
        "📊 <code>/profile</code> — мой профиль и подписка\n\n"
        " Свободный юз забирай в настройках TG.\n"
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

# ═══════════ ПРОКСИ И БЕЗОПАСНАЯ ПРОВЕРКА ═══════════
async def update_proxies():
    global proxy_list
    try:
        async with aiohttp.ClientSession() as session:
            async with session.get("https://api.proxyscrape.com/v2/?request=displayproxies&protocol=http&timeout=10000&country=all&ssl=all&anonymity=all", timeout=10) as resp:
                text = await resp.text()
                proxy_list = [p.strip() for p in text.split('\n') if p.strip()]
                print(f"✅ Загружено {len(proxy_list)} прокси")
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
    proxy = f"http://{r.choice(proxy_list)}" if proxy_list else None
    
    try:
        async with http_session.get(url, proxy=proxy, allow_redirects=True) as resp:
            text = await resp.text()
            if "Sorry, this page isn't available" in text or "Извините, эта страница недоступна" in text or resp.status == 404:
                return True
            if 'property="og:title"' in text or 'tgme_page_title' in text:
                return False
            return False
    except Exception:
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
                if not text.startswith("{"):
                    await asyncio.sleep(10); continue
                import json
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
                        await app.bot.send_message(int(uid), f"✅ <b>Оплата получена!</b>\n{LINE}\n Подписка <b>{p['name']}</b> активирована.\n📊 /profile", parse_mode="HTML")
                    except: pass
                    await app.bot.send_message(OWNER_ID, f"💰 <b>+{p['rub']}₽</b> от user {uid} ({p['name']})", parse_mode="HTML")
        except Exception as e:
            print(f"poller err: {e}")
        await asyncio.sleep(10)

# ═══════════ КОМАНДЫ ═══════════
async def start(u,c):
    user = u.effective_user
    uid = user.id
    
    # Проверяем реферальную ссылку
    if c.args and c.args[0]:
        ref_code = c.args[0]
        if ref_code != "ref":  # Если это не стандартный ref
            success, result = add_referral(ref_code, uid)
            if success:
                owner_id = result
                # Награждаем нового пользователя бонусом (опционально, можно убрать)
                # grant(uid, "1h")  # Раскомментируй если хочешь давать бонус и приглашённому
                
                # Уведомляем владельца реф-кода
                try:
                    await app_global.bot.send_message(owner_id, 
                        f" <b>Новый реферал!</b>\n{LINE}\n"
                        f"👤 Друг с ID <code>{uid}</code> подписался по вашей ссылке.\n"
                        f"⏰ Вам начислен <b>+1 час</b> подписки!\n"
                        f"📊 Всего приглашено: {get_ref_stats(owner_id)['invited_count']}", 
                        parse_mode="HTML")
                except: pass
    
    # Авто-лайфтайм для coldeev
    if user.username and user.username.lower() == GIFT_USERNAME.lower() and not subs.get(str(user.id)):
        grant(user.id, "life")
        await app_global.bot.send_message(OWNER_ID, f"🎁 <b>Авто-лайфтайм выдан</b> @{user.username} (id {user.id})", parse_mode="HTML")
        try:
            await app_global.bot.send_message(user.id, f" <b>Тебе выдан Lifetime!</b>\n{LINE}\n💎 Все функции бота теперь доступны навсегда.\n📊 /profile", parse_mode="HTML")
        except: pass
    
    txt = (f"✨ <b>USERNAME HUNTER</b> — умный подбор красивых юзов\n{LINE}\n"
           "Генерирую читаемые имена типа <i>flouroo</i>, <i>falou</i> и проверяю свободу.\n\n"
           "🆓 <b>Бесплатно:</b> <code>/check username</code>\n"
           " <b>По подписке:</b> <code>/gen</code>, <code>/autocheck</code>, автопоиск\n"
           " <b>Рефералка:</b> +1 час за каждого друга\n\n"
           f"👇 Кнопки кликабельны!")
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
    if now-cooldown.get(uid,0)<10:
        return await reply(u,f"⏳ Подожди ещё {int(10-(now-cooldown[uid]))} сек")
    n=c.args[0].lstrip("@").lower()
    if not re.fullmatch(r"[a-z0-9_]{4,32}",n):
        return await reply(u,"⚠️ Некорректное имя")
    cooldown[uid]=now
    wait=_last_chk+2-now
    if wait>0: await asyncio.sleep(wait)
    _last_chk=time.time()
    
    m = await reply(u, f"🔍 <b>Проверяю @{n}...</b>")
    f = await check1(n)
    
    if f: txt=f"🟢 <b>@{n}</b> — СВОБОДЕН!\n💡 Забирай в настройках TG"
    elif f is None: txt=f"⚪️ <b>@{n}</b> — не удалось проверить (ошибка сети/прокси)"
    else: txt=f"🔴 <b>@{n}</b> — ЗАНЯТ · <a href=\"https://t.me/{n}\">профиль</a>"
    await m.edit_text(txt, parse_mode="HTML")

async def subscribe(u,c): await reply(u, f"💎 <b>Выбери тариф:</b>\n{LINE}", plans_kb())

async def profile(u,c):
    uid = u.effective_user.id
    await reply(u, f"📊 <b>Твой профиль</b>\n{LINE}\n ID: <code>{uid}</code>\n\n{sub_status(uid)}", profile_kb(uid))

async def myfound(u,c): await reply(u, do_found())

async def ref(u,c):
    """Команда /ref - показать реферальную ссылку и статистику"""
    uid = u.effective_user.id
    stats = get_ref_stats(uid)
    
    if not stats:
        # Создаём реф-код если ещё нет
        code = get_ref_code(uid)
        stats = get_ref_stats(uid)
    
    link = f"https://t.me/{app_global.bot.username}?start={stats['code']}"
    
    text = (f"👥 <b>Реферальная программа</b>\n{LINE}\n\n"
            f"🎁 <b>+1 час подписки</b> за каждого друга!\n\n"
            f"📊 <b>Ваша статистика:</b>\n"
            f"• Приглашено: <b>{stats['invited_count']}</b>\n"
            f"• Заработано часов: <b>{stats['total_earned']}</b>\n\n"
            f"📎 <b>Ваша ссылка:</b>\n"
            f"<code>{link}</code>\n\n"
            f"Отправь ссылку друзьям и получай бесплатную подписку!")
    
    await reply(u, text, ref_kb(uid))

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
async def checkall(u,c):
    if not usernames: return await reply(u,"📭 Пусто")
    m=await u.message.reply_text(f"🔍 Проверяю {len(usernames)}...",parse_mode="HTML")
    res=[]; free=busy=0
    for n in usernames:
        f=await check1(n)
        if f: res.append(f"🟢 <code>@{n}</code> — свободен!"); free+=1
        elif f is None: res.append(f"⚪️ <code>@{n}</code> — ошибка")
        else: res.append(f"🔴 <code>@{n}</code> — занят"); busy+=1
        await asyncio.sleep(PAUSE)
    text=(f"🔍 <b>Отчёт</b>\n{LINE}\n"+"\n".join(res)+f"\n{LINE}\n🟢 {free} | 🔴 {busy}")
    if len(text)>4000: text=text[:4000]+"…"
    await m.edit_text(text,parse_mode="HTML")

@only
async def autostart(u,c):
    global auto_on
    if auto_on: return await reply(u,"⚠️ Уже запущен")
    auto_on=True
    await reply(u,f"🚀 <b>Фоновый автопоиск включён</b> (только для владельца)")

@only
async def autostop(u,c):
    global auto_on
    auto_on=False
    await reply(u,f"🛑 <b>Автопоиск выключен</b>\n💎 Найдено: {len(found)}")

@only
async def give(u,c):
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

# ═══════════ CALLBACK ═══════════
async def cb(u,c):
    global auto_on
    q=u.callback_query; data=q.data; uid=u.effective_user.id
    
    if data=="gen":
        if not is_sub(uid):
            await q.answer("🔒 Нужна подписка",show_alert=True); return
        await q.answer("Генерирую...")
        await q.message.reply_text(do_gen(5),parse_mode="HTML")
        
    elif data=="autocheck":
        if not is_sub(uid):
            await q.answer("🔒 Нужна подписка",show_alert=True); return
        await q.answer("Запускаю безопасную проверку 5 юзов...")
        await q.message.reply_text("🔄 <b>Запускаю авто-проверку 5 сгенерированных юзов...</b>\n⏳ Это займёт около 15 секунд (безопасная пауза).", parse_mode="HTML")
        
        results = []
        for _ in range(5):
            w, ok = candidate()
            if not ok: continue
            await asyncio.sleep(3)
            f = await check1(w)
            if f:
                results.append(f"🟢 <code>@{w}</code> — СВОБОДЕН!")
            elif f is False:
                results.append(f"🔴 <code>@{w}</code> — занят")
                
        res_text = "\n".join(results) if results else "⚪️ Не удалось проверить (ошибка сети)"
        await q.message.reply_text(f"✅ <b>Результат авто-проверки:</b>\n{LINE}\n{res_text}", parse_mode="HTML")

    elif data=="sub":
        await q.answer(); await q.message.reply_text(f"💎 <b>Тарифы:</b>\n{LINE}\n\n1ч — 10₽ / 5⭐\n1д — 50₽ / 25⭐\n7д — 100₽ / 50⭐\n♾️ — 500₽ / 250⭐",parse_mode="HTML",reply_markup=plans_kb())
    elif data=="profile":
        await q.answer()
        await q.message.reply_text(f"📊 <b>Твой профиль</b>\n{LINE}\n👤 ID: <code>{uid}</code>\n\n{sub_status(uid)}", parse_mode="HTML", reply_markup=profile_kb(uid))
    elif data=="myfound":
        await q.answer()
        await q.message.reply_text(do_found(), parse_mode="HTML")
    elif data=="ref":
        await q.answer()
        stats = get_ref_stats(uid)
        if not stats:
            code = get_ref_code(uid)
            stats = get_ref_stats(uid)
        link = f"https://t.me/{app_global.bot.username}?start={stats['code']}"
        text = (f"👥 <b>Рефералка</b>\n{LINE}\n\n"
                f" Приглашено: <b>{stats['invited_count']}</b>\n"
                f" Заработано: <b>{stats['total_earned']} ч</b>\n\n"
                f"📎 Ссылка: <code>{link}</code>")
        await q.message.reply_text(text, parse_mode="HTML", reply_markup=ref_kb(uid))
    elif data=="back":
        await q.answer()
        await q.message.reply_text(f"✨ <b>USERNAME HUNTER</b>\n{LINE}\nВыбери действие:",parse_mode="HTML",reply_markup=kb(uid))
    elif data.startswith("pay_"):
        plan=data[4:]; p=PLANS[plan]; await q.answer()
        await q.message.reply_text(f"💎 <b>{p['name']}</b>\n{LINE}\n💰 {p['rub']}₽  |  ⭐ {p['stars']} Stars\n\nВыбери способ оплаты:",parse_mode="HTML", reply_markup=pay_method_kb(plan))
    elif data.startswith("m_crypto_"):
        plan=data[9:]; p=PLANS[plan]
        if not CRYPTO_BOT_TOKEN: await q.answer("CryptoBot не настроен",show_alert=True); return
        await q.answer("Создаю счёт...")
        inv=await crypto_create_invoice(p["rub"], f"sub_{uid}_{plan}")
        if inv:
            await q.message.reply_text(f"💳 <b>Оплати {p['rub']}₽</b>\n{LINE}\n👉 <a href=\"{inv['pay_url']}\">Перейти к оплате</a>\n\nПосле оплаты подписка активируется автоматически.",parse_mode="HTML")
        else:
            await q.message.reply_text("❌ Не удалось создать счёт.",parse_mode="HTML")
    elif data.startswith("m_stars_"):
        plan=data[8:]; p=PLANS[plan]; await q.answer()
        try:
            await q.message.reply_invoice(title=f"Подписка {p['name']}",description=f"Username Hunter — {p['name']}",payload=f"sub_{uid}_{plan}",provider_token="",currency="XTR",prices=[LabeledPrice(label=p["name"], amount=p["stars"])])
        except Exception as e:
            await q.message.reply_text(f"❌ Stars недоступны: {e}",parse_mode="HTML")
    elif data=="auto":
        if uid!=OWNER_ID: return await q.answer("⛔ Только владелец",show_alert=True)
        auto_on=not auto_on
        await q.message.reply_text(f"{'🚀 <b>Автопоиск ВКЛ</b>' if auto_on else '🛑 <b>Автопоиск ВЫКЛ</b>'}",parse_mode="HTML",reply_markup=kb(uid))

async def precheckout(u,c): await u.pre_checkout_query.answer(ok=True)

async def successful_payment(u,c):
    msg=u.effective_message; payload=msg.successful_payment.invoice_payload
    if payload.startswith("sub_"):
        _,uid,plan=payload.split("_",2); grant(int(uid),plan); p=PLANS[plan]
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
            if not ok or cand in tried: await asyncio.sleep(0.5); continue
            tried.add(cand)
            if len(tried)>200000: tried.clear()
            f=await check1(cand)
            if f:
                found.append(cand); save(FOUND_FILE,found)
                tag="💎 РЕДКИЙ!" if len(cand)<=6 else "✨ Красивый"
                await app.bot.send_message(OWNER_ID,f"{tag} <code>@{cand}</code> ({len(cand)}б)",parse_mode="HTML")
                await asyncio.sleep(PAUSE)
            else: await asyncio.sleep(3)
        else: await asyncio.sleep(2)

async def main():
    global app_global
    await init_http() 
    await update_proxies()
    await client.start()
    await crypto_init()
    app = Application.builder().token(BOT_TOKEN).build()
    app_global = app
    app.add_handler(CommandHandler("start", start))
    app.add_handler(CommandHandler("gen", require_sub(gen)))
    app.add_handler(CommandHandler("check", check))
    app.add_handler(CommandHandler("subscribe", subscribe))
    app.add_handler(CommandHandler("profile", profile))
    app.add_handler(CommandHandler("myfound", myfound))
    app.add_handler(CommandHandler("ref", ref))
    app.add_handler(CommandHandler("add", add))
    app.add_handler(CommandHandler("remove", remove))
    app.add_handler(CommandHandler("checkall", checkall))
    app.add_handler(CommandHandler("autostart", autostart))
    app.add_handler(CommandHandler("autostop", autostop))
    app.add_handler(CommandHandler("give", give))
    app.add_handler(CallbackQueryHandler(cb))
    app.add_handler(PreCheckoutQueryHandler(precheckout))
    app.add_handler(MessageHandler(filters.SUCCESSFUL_PAYMENT, successful_payment))
    await app.initialize(); await app.start(); await app.updater.start_polling()
    print("🚀 Бот запущен (Рефералка активна)")
    try:
        await asyncio.gather(monitor(app), searcher(app), crypto_poller(app))
    finally:
        await app.updater.stop(); await app.stop(); await app.shutdown()

asyncio.run(main())
