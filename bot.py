import asyncio, os, json, random
from dotenv import load_dotenv
from telethon import TelegramClient
from telethon.tl.functions.account import CheckUsernameRequest
from telethon.tl.functions.channels import CreateChannelRequest, UpdateUsernameRequest
from telethon.errors import FloodWaitError, UsernameInvalidError
from telegram import Update
from telegram.ext import Application, CommandHandler, ContextTypes

load_dotenv()
API_ID = int(os.getenv("API_ID"))
API_HASH = os.getenv("API_HASH")
BOT_TOKEN = os.getenv("BOT_TOKEN")
OWNER_ID = 6288011144
DATA_FILE = "usernames.json"
FOUND_FILE = "found.json"
CHECK_INTERVAL = 300
PAUSE = 4

client = TelegramClient('session', API_ID, API_HASH)
notified = set()
tried = set()
auto_on = False

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

# ─── Паттерны слогов (дают flouroo, falou и т.п.) ───
def _p1(): return r(CLU)+r(VOW)+r(SIN)+r(DVOW)   # fl + ou + r + oo  → flouroo
def _p2(): return r(SIN)+r(VOW)+r(SIN)+r(DVOW)   # f + a + l + ou    → falou
def _p3(): return r(CLU)+r(VOW)+r(SIN)+r(VOW)    # fl + o + r + a    → flora
def _p4(): return r(SIN)+r(VOW)+r(CLU)+r(VOW)    # m + o + st + o    → mosto
def _p5(): return r(CLU)+r(DVOW)+r(SIN)+r(VOW)   # fl + ou + m + o   → floumo
PATTERNS = [_p1,_p2,_p3,_p4,_p5]

def _word():
    w = r(WORDS)
    if len(w) < 5:                      # короткие слова доращиваем: zen → zenoo
        w += r(["oo","o","a","us","ix","ia","eo","ay"])
    return w

def pretty(w):
    """Фильтр: 5-9 букв, произносимо, без мусора"""
    if not (5 <= len(w) <= 9): return False
    vs = set("aeiouy"); run = 0
    for c in w:
        if c in vs: run = 0
        else:
            run += 1
            if run >= 3: return False          # не больше 2 согласных подряд
    for i in range(len(w)-2):
        if w[i]==w[i+1]==w[i+2]: return False  # нет aaa/ooo
    if w[-1] in "xqj" and w not in WORDS: return False
    return True

def score(w):
    """Оценка красоты: выбираем лучший из нескольких кандидатов"""
    s = 0
    if 5 <= len(w) <= 7: s += 2                # идеальная длина
    if any(w.startswith(c) for c in CLU): s += 2   # красивое начало (fl, br...)
    if w[-2:] in DVOW or w[-1] in "aeou": s += 2   # красивое окончание (-oo, -ou)
    if 2 <= sum(c in "aeiou" for c in w) <= 4: s += 1
    if any(c*2 in w for c in "aeo"): s += 1        # удвоенные гласные
    return s

def candidate():
    if random.random() < 0.25:
        return _word(), True
    best, bs = None, -1
    for _ in range(12):                        # 12 попыток, берём лучший
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

# ═══════════ КРАСИВОЕ ОФОРМЛЕНИЕ ═══════════
LINE = "▬▬▬▬▬▬▬▬▬▬▬▬▬▬▬▬▬▬"

async def reply(u, text):
    if len(text) > 4000: text = text[:4000] + "\n…(обрезано)"
    await u.message.reply_text(text, parse_mode="HTML")

def only(fn):
    async def w(u,c):
        if u.effective_user.id != OWNER_ID: return
        return await fn(u,c)
    return w

@only
async def start(u,c):
    await reply(u,
        "✨ <b>USERNAME HUNTER</b> — умный подбор юзов\n"
        f"{LINE}\n"
        "➕ <code>/add username</code> — добавить в слежку\n"
        "➖ <code>/remove username</code> — убрать из слежки\n"
        "📋 <code>/list</code> — список слежки\n"
        "🔍 <code>/check</code> — проверить все сейчас\n"
        "🎲 <code>/gen [n]</code> — сгенерировать красивые варианты\n"
        "🚀 <code>/autostart</code> — включить автопоиск\n"
        "🛑 <code>/autostop</code> — выключить автопоиск\n"
        "💎 <code>/found</code> — найденные юзы\n"
        "🎯 <code>/claim username</code> — занять юз\n"
        f"{LINE}\n"
        "🤖 Генератор выдаёт читаемые имена типа <i>flouroo</i>, <i>falou</i> — не короче 5 букв.")

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
    if not usernames: return await reply(u, "📭 <b>Список пуст.</b> Добавь: <code>/add username</code>")
    body = "\n".join(f"• <code>@{x}</code>" for x in usernames)
    await reply(u, f"📋 <b>Слежка ({len(usernames)}):</b>\n{LINE}\n{body}")

async def check1(n, retries=3):
    for _ in range(retries):
        try: return await client(CheckUsernameRequest(username=n))
        except UsernameInvalidError: return None
        except FloodWaitError as e: await asyncio.sleep(e.seconds+1)
        except Exception: return None
    return None

@only
async def chk(u,c):
    if not usernames: return await reply(u, "📭 <b>Список пуст.</b> Добавь: <code>/add username</code>")
    m = await u.message.reply_text(f"🔍 <b>Проверяю {len(usernames)} юзов...</b>", parse_mode="HTML")
    res = []; free = busy = 0
    for n in usernames:
        f = await check1(n)
        if f:   res.append(f"🟢 <code>@{n}</code> — свободен!"); free += 1
        elif f is None: res.append(f"⚪️ <code>@{n}</code> — невалиден")
        else:   res.append(f"🔴 <code>@{n}</code> — занят"); busy += 1
        await asyncio.sleep(PAUSE)
    text = (f"🔍 <b>Отчёт проверки</b>\n{LINE}\n" + "\n".join(res) +
            f"\n{LINE}\n🟢 свободных: <b>{free}</b>  |  🔴 занятых: <b>{busy}</b>")
    if len(text) > 4000: text = text[:4000] + "\n…(обрезано)"
    await m.edit_text(text, parse_mode="HTML")

@only
async def gen(u,c):
    n = 10
    if c.args:
        try: n = max(1, min(30, int(c.args[0])))
        except ValueError: pass
    seen = []; guard = 0
    while len(seen) < n and guard < n*50:
        guard += 1
        w, ok = candidate()
        if ok and w not in seen: seen.append(w)
    body = "\n".join(f"• <code>{w}</code>  ·  {len(w)} букв" for w in seen)
    await reply(u, f"🎲 <b>Сгенерировано {len(seen)}:</b>\n{LINE}\n{body}")

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
    await reply(u, f"🛑 <b>Автопоиск выключен</b>\n{LINE}\n💎 Найдено за сессию: {len(found)}")

@only
async def shown(u,c):
    if not found: return await reply(u, f"💎 <b>Пока ничего не найдено.</b>\nВключи: <code>/autostart</code>")
    last = found[-30:]
    body = "\n".join(f"{i}. <code>@{w}</code>  ·  {len(w)} букв" for i,w in enumerate(last,1))
    await reply(u, f"💎 <b>Найдено всего: {len(found)}</b> (последние {len(last)})\n{LINE}\n{body}")

@only
async def claim(u,c):
    if not c.args: return await reply(u, "🎯 <b>Укажи юз:</b> <code>/claim username</code>")
    n = c.args[0].lstrip("@").lower()
    await reply(u, f"⏳ <b>Занимаю</b> <code>@{n}</code>...")
    try:
        rr = await client(CreateChannelRequest(title=n, about="", megagroup=False))
        ch = rr.chats[0]
        await client(UpdateUsernameRequest(channel=ch, username=n))
        await reply(u, f"🏆 <b>Готово!</b> <code>@{n}</code> теперь твой.\n{LINE}\nКанал создан и юз привязан.")
    except Exception as e:
        await reply(u, f"❌ <b>Не вышло:</b> <code>{e}</code>")

async def monitor(app):
    while True:
        for n in list(usernames):
            f = await check1(n)
            if f and n not in notified:
                notified.add(n)
                await app.bot.send_message(OWNER_ID,
                    f"🎉 <b>@{n} ОСВОБОДИЛСЯ!</b>\n{LINE}\n🎯 Забрать: <code>/claim {n}</code>",
                    parse_mode="HTML")
            await asyncio.sleep(PAUSE)
        await asyncio.sleep(CHECK_INTERVAL)

async def searcher(app):
    global auto_on, tried
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
                     f"{LINE}\n🎯 Забрать: <code>/claim {cand}</code>")
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
    app.add_handler(CommandHandler("add", add))
    app.add_handler(CommandHandler("remove", remove))
    app.add_handler(CommandHandler("list", lst))
    app.add_handler(CommandHandler("check", chk))
    app.add_handler(CommandHandler("gen", gen))
    app.add_handler(CommandHandler("autostart", autostart))
    app.add_handler(CommandHandler("autostop", autostop))
    app.add_handler(CommandHandler("found", shown))
    app.add_handler(CommandHandler("claim", claim))
    await app.initialize(); await app.start(); await app.updater.start_polling()
    print("Бот запущен")
    try:
        await asyncio.gather(monitor(app), searcher(app))
    finally:
        await app.updater.stop(); await app.stop(); await app.shutdown()

asyncio.run(main())
