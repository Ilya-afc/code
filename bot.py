import asyncio, os, json, random, re, time
from dotenv import load_dotenv
from telethon import TelegramClient
from telethon.tl.functions.account import CheckUsernameRequest
from telethon.errors import FloodWaitError, UsernameInvalidError
from telegram import InlineKeyboardButton, InlineKeyboardMarkup
from telegram.ext import Application, CommandHandler, CallbackQueryHandler

load_dotenv()
API_ID = int(os.getenv("API_ID"))
API_HASH = os.getenv("API_HASH")
BOT_TOKEN = os.getenv("BOT_TOKEN")
OWNER_ID = 6288011144
OWNER_LINK = "https://t.me/username"   # ← ЗАМЕНИ на свой профиль/канал
DATA_FILE = "usernames.json"
FOUND_FILE = "found.json"
CHECK_INTERVAL = 300
PAUSE = 4

client = TelegramClient('session', API_ID, API_HASH)
notified = set()
tried = set()
cooldown = {}
auto_on = False
_last_chk = 0

# ═══════════ БАЗЫ ДЛЯ УМНОЙ ГЕНЕРАЦИИ ═══════════
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

def _p1(): return r(CLU)+r(VOW)+r(SIN)+r(DVOW)   # flouroo
def _p2(): return r(SIN)+r(VOW)+r(SIN)+r(DVOW)   # falou
def _p3(): return r(CLU)+r(VOW)+r(SIN)+r(VOW)    # flora
def _p4(): return r(SIN)+r(VOW)+r(CLU)+r(VOW)    # mosto
def _p5(): return r(CLU)+r(DVOW)+r(SIN)+r(VOW)   # floumo
PATTERNS = [_p1,_p2,_p3,_p4,_p5]

def _word():
    w = r(WORDS)
    if len(w) < 5:
        w += r(["oo","o","a","us","ix","ia","eo","ay"])
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
    if random.random() < 0.25:
        return _word(), True
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
    return []

def save(p,d):
    with open(p,"w") as f: json.dump(d,f)

usernames = load(DATA_FILE)
found = load(FOUND_FILE)

# ═══════════ ОФОРМЛЕНИЕ ═══════════
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

# ═══════════ КЛИКАБЕЛЬНЫЕ КНОПКИ ═══════════
def kb(uid):
    rows = [[InlineKeyboardButton("🎲 Сгенерировать 5", callback_data="gen"),
             InlineKeyboardButton("❓ Справка", callback_data="help")]]
    if uid == OWNER_ID:
        rows.append([InlineKeyboardButton("📋 Слежка", callback_data="list"),
                     InlineKeyboardButton("💎 Найдено", callback_data="found")])
        rows.append([InlineKeyboardButton("🛑 Автостоп" if auto_on else "🚀 Автостарт",
                                          callback_data="auto")])
    rows.append([InlineKeyboardButton("👤 Владелец", url=OWNER_LINK)])
    return InlineKeyboardMarkup(rows)

HELP = ("❓ <b>Справка</b>\n" + LINE + "\n"
        "🎲 <code>/gen 10</code> — сгенерировать красивые юзы (до 20)\n"
        "🔍 <code>/check name</code> — проверить юз на свободу (раз в 15 сек)\n\n"
        "💡 Если юз свободен — забирай его в настройках Telegram:\n"
        "<i>Настройки → Изменить профиль → Имя пользователя</i>\n"
        f"{LINE}\n👤 Вопросы: <a href=\"{OWNER_LINK}\">владелец</a>")

def do_gen(n):
    seen = []; guard = 0
    while len(seen) < n and guard < n*50:
        guard += 1
        w, ok = candidate()
        if ok and w not in seen: seen.append(w)
    body = "\n".join(f"• <code>{w}</code>  ·  {len(w)} букв" for w in seen)
    return (f"🎲 <b>Сгенерировано {len(seen)}:</b>\n{LINE}\n{body}\n"
            f"{LINE}\n🔍 Проверить любой: <code>/check имя</code>")

def do_list():
    if not usernames: return "📭 <b>Список пуст.</b> Добавь: <code>/add username</code>"
    body = "\n".join(f"• <code>@{x}</code>" for x in usernames)
    return f"📋 <b>Слежка ({len(usernames)}):</b>\n{LINE}\n{body}"

def do_found():
    if not found: return f"💎 <b>Пока ничего не найдено.</b>\nВключи: <code>/autostart</code>"
    last = found[-30:]
    body = "\n".join(f"{i}. <code>@{w}</code>  ·  {len(w)} букв" for i,w in enumerate(last,1))
    return f"💎 <b>Найдено всего: {len(found)}</b> (последние {len(last)})\n{LINE}\n{body}"

# ═══════════ ПУБЛИЧНЫЕ КОМАНДЫ ═══════════
async def start(u,c):
    txt = (f"✨ <b>USERNAME HUNTER</b> — умный подбор красивых юзов TG\n{LINE}\n"
           "Генерирую читаемые имена типа <i>flouroo</i>, <i>falou</i>, <i>brayou</i> "
           "и проверяю, свободны ли они.\n\n"
           "👥 <b>Доступно всем:</b>\n"
           "🎲 <code>/gen [n]</code> — сгенерировать красивые юзы\n"
           "🔍 <code>/check username</code> — проверить юз на свободу\n\n"
           f"🔒 Слежка, автопоиск и находки — только для владельца.\n{LINE}\n"
           "👇 <b>Кнопки ниже — кликабельные!</b>")
    await reply(u, txt, kb(u.effective_user.id))

async def gen(u,c):
    n = 5
    if c.args:
        try: n = max(1, min(20, int(c.args[0])))
        except ValueError: pass
    await reply(u, do_gen(n))

async def check(u,c):
    global _last_chk
    if not c.args:
        return await reply(u, "🔍 <b>Укажи юз:</b> <code>/check flouroo</code>")
    uid = u.effective_user.id
    now = time.time()
    if now - cooldown.get(uid, 0) < 15:
        return await reply(u, f"⏳ <b>Не так часто.</b> Подожди ещё {int(15-(now-cooldown[uid]))} сек")
    n = c.args[0].lstrip("@").lower()
    if not re.fullmatch(r"[a-z0-9_]{4,32}", n):
        return await reply(u, "⚠️ <b>Некорректное имя</b> (буквы a-z, цифры, _)",)
    cooldown[uid] = now
    wait = _last_chk + 3 - now
    if wait > 0: await asyncio.sleep(wait)
    _last_chk = time.time()
    f = await check1(n)
    if f:
        txt = f"🟢 <b>@{n}</b> — СВОБОДЕН!\n💡 Забирай: <i>Настройки TG → Изменить профиль → Имя пользователя</i>"
    elif f is None:
        txt = f"⚪️ <b>@{n}</b> — невалиден или не существует"
    else:
        txt = f"🔴 <b>@{n}</b> — занят · <a href=\"https://t.me/{n}\">посмотреть профиль</a>"
    await reply(u, txt)

# ═══════════ КОМАНДЫ ВЛАДЕЛЬЦА ═══════════
@only
async def add(u,c):
    if not c.args: return await reply(u, "➕ <b>Укажи юз:</b> <code>/add username</code>")
    n = c.args[0].lstrip("@").lower()
    if n in usernames: return await reply(u, f"⚠️ <code>@{n}</code> уже в списке")
    usernames.append(n); save(DATA_FILE, usernames)
    await reply(u, f"✅ <b>Добавлен</b> <code>@{n}</code>\n{LINE}\nВ слежке: {len(usernames)}")

@only
async def remove(u,c):
    if not c.args: return await reply(u, "➖ <b>Укажи юз:</b> <code>/remove username</code>")
    n = c.args[0].lstrip("@").lower()
    if n not in usernames: return await reply(u, f"⚠️ <code>@{n}</code> нет в списке")
    usernames.remove(n); notified.discard(n); save(DATA_FILE, usernames)
    await reply(u, f"🗑 <b>Удалён</b> <code>@{n}</code>\n{LINE}\nВ слежке: {len(usernames)}")

@only
async def lst(u,c):
    await reply(u, do_list())

async def check1(n, retries=3):
    for _ in range(retries):
        try: return await client(CheckUsernameRequest(username=n))
        except UsernameInvalidError: return None
        except FloodWaitError as e: await asyncio.sleep(e.seconds+1)
        except Exception: return None
    return None

@only
async def checkall(u,c):
    if not usernames: return await reply(u, "📭 <b>Список пуст.</b> Добавь: <code>/add username</code>")
    m = await u.message.reply_text(f"🔍 <b>Проверяю {len(usernames)} юзов...</b>", parse_mode="HTML")
    res = []; free = busy = 0
    for n in usernames:
        f = await check1(n)
        if f:   res.append(f"🟢 <code>@{n}</code> — свободен!"); free += 1
        elif f is None: res.append(f"⚪️ <code>@{n}</code> — невалиден")
        else:   res.append(f"🔴 <code>@{n}</code> — занят · <a href=\"https://t.me/{n}\">профиль</a>"); busy += 1
        await asyncio.sleep(PAUSE)
    text = (f"🔍 <b>Отчёт проверки</b>\n{LINE}\n" + "\n".join(res) +
            f"\n{LINE}\n🟢 свободных: <b>{free}</b>  |  🔴 занятых: <b>{busy}</b>")
    if len(text) > 4000: text = text[:4000] + "\n…(обрезано)"
    await m.edit_text(text, parse_mode="HTML")

@only
async def autostart(u,c):
    global auto_on
    if auto_on: return await reply(u, "⚠️ Автопоиск <b>уже запущен</b>")
    auto_on = True
    await reply(u, f"🚀 <b>Автопоиск включён!</b>\n{LINE}\n🤖 Ищу красивые юзы типа <i>flouroo</i>...")

@only
async def autostop(u,c):
    global auto_on
    auto_on = False
    await reply(u, f"🛑 <b>Автопоиск выключен</b>\n{LINE}\n💎 Найдено за всё время: {len(found)}")

@only
async def shown(u,c):
    await reply(u, do_found())

# ═══════════ КНОПКИ (CALLBACK) ═══════════
async def cb(u,c):
    global auto_on
    q = u.callback_query; data = q.data; uid = u.effective_user.id
    if data == "gen":
        await q.answer("Генерирую...")
        await q.message.reply_text(do_gen(5), parse_mode="HTML")
    elif data == "help":
        await q.answer()
        await q.message.reply_text(HELP, parse_mode="HTML")
    elif data in ("list", "found"):
        if uid != OWNER_ID: return await q.answer("⛔ Только владелец", show_alert=True)
        await q.answer()
        await q.message.reply_text(do_list() if data == "list" else do_found(), parse_mode="HTML")
    elif data == "auto":
        if uid != OWNER_ID: return await q.answer("⛔ Только владелец", show_alert=True)
        auto_on = not auto_on
        await q.edit_message_reply_markup(reply_markup=kb(uid))
        await q.answer("🚀 Автопоиск ВКЛ" if auto_on else "🛑 Автопоиск ВЫКЛ")

# ═══════════ ФОНОВЫЕ ПРОЦЕССЫ ═══════════
async def monitor(app):
    while True:
        for n in list(usernames):
            f = await check1(n)
            if f and n not in notified:
                notified.add(n)
                await app.bot.send_message(OWNER_ID,
                    f"🎉 <b>@{n} ОСВОБОДИЛСЯ!</b>\n{LINE}\n💡 Забери в настройках TG",
                    parse_mode="HTML")
            await asyncio.sleep(PAUSE)
        await asyncio.sleep(CHECK_INTERVAL)

async def searcher(app):
    global tried
    while True:
        if auto_on:
            cand, ok = candidate()
            if not ok or cand in tried:
                await asyncio.sleep(0.2); continue
            tried.add(cand)
            if len(tried) > 200000: tried.clear()
            f = await check1(cand)
            if f:
                found.append(cand); save(FOUND_FILE, found)
                tag = "💎 <b>РЕДКИЙ КОРОТКИЙ!</b>" if len(cand) <= 6 else "✨ <b>Красивый юз!</b>"
                m = (f"{tag}\n{LINE}\n👤 <code>@{cand}</code>\n🔤 букв: {len(cand)}\n"
                     f"{LINE}\n💡 Забери в настройках TG")
                await app.bot.send_message(OWNER_ID, m, parse_mode="HTML")
                await asyncio.sleep(PAUSE)
            else:
                await asyncio.sleep(2)
        else:
            await asyncio.sleep(2)

async def main():
    await client.start()
    app = Application.builder().token(BOT_TOKEN).build()
    app.add_handler(CommandHandler("start", start))
    app.add_handler(CommandHandler("gen", gen))
    app.add_handler(CommandHandler("check", check))
    app.add_handler(CommandHandler("add", add))
    app.add_handler(CommandHandler("remove", remove))
    app.add_handler(CommandHandler("list", lst))
    app.add_handler(CommandHandler("checkall", checkall))
    app.add_handler(CommandHandler("autostart", autostart))
    app.add_handler(CommandHandler("autostop", autostop))
    app.add_handler(CommandHandler("found", shown))
    app.add_handler(CallbackQueryHandler(cb))
    await app.initialize(); await app.start(); await app.updater.start_polling()
    print("Бот запущен")
    try:
        await asyncio.gather(monitor(app), searcher(app))
    finally:
        await app.updater.stop(); await app.stop(); await app.shutdown()

asyncio.run(main())
