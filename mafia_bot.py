import asyncio, json, os, random
from dataclasses import dataclass, field
from aiogram import Bot, Dispatcher, F
from aiogram.filters import Command
from aiogram.types import (Message, CallbackQuery,
                           InlineKeyboardMarkup, InlineKeyboardButton)

TOKEN = os.getenv("BOT_TOKEN", "9124751414:AAGL0-Sj8Y2CksynJLEsiYdcIyv4PGdA2bQ")
OWNER_ID = int(os.getenv("OWNER_ID", "8707797093"))
DB_FILE = "rewards.json"

DON_COINS, MAFIA_COINS, CIV_COINS = 100, 50, 30
DON_GIFTS = ["🎁 Oltin shlyapa", "💎 Olmos uzuk", "🏆 Don kubogi", "🥃 Premium viski", "🚗 Qora limuzin"]
MAFIA_GIFTS = ["🔫 Kumush to'pponcha", "🎩 Qora shlyapa", "💵 Pul dasta"]

ROLE_NAMES = {"don": "👑 Don", "mafia": "🕴 Mafiya", "doctor": "👨‍⚕️ Doktor",
              "com": "🕵️ Komissar", "civ": "👤 Tinch aholi"}
MAFIA_TEAM = {"don", "mafia"}

db = json.load(open(DB_FILE)) if os.path.exists(DB_FILE) else {}


def save_db():
    json.dump(db, open(DB_FILE, "w"), ensure_ascii=False, indent=1)


def reward(uid, name, coins, gift=None):
    u = db.setdefault(str(uid), {"name": name, "coins": 0, "wins": 0, "gifts": []})
    u["name"] = name
    u["coins"] += coins
    u["wins"] += 1
    if gift:
        u["gifts"].append(gift)
    save_db()


@dataclass
class Game:
    chat_id: int
    admin: int
    players: dict = field(default_factory=dict)
    roles: dict = field(default_factory=dict)
    alive: set = field(default_factory=set)
    phase: str = "lobby"
    kill: int = None
    save: int = None
    check: int = None
    done: set = field(default_factory=set)
    need: set = field(default_factory=set)
    votes: dict = field(default_factory=dict)
    admin_plays: bool = True


games: dict[int, Game] = {}
bot = Bot(TOKEN)
dp = Dispatcher()


def name(g, uid):
    return g.players[uid]


def kb(rows):
    return InlineKeyboardMarkup(inline_keyboard=rows)


def target_kb(g, kind, uids):
    return kb([[InlineKeyboardButton(text=name(g, u), callback_data=f"{kind}:{g.chat_id}:{u}")] for u in uids])


# ---------------- LOBBY ----------------
@dp.message(Command("newgame"), F.chat.type.in_({"group", "supergroup"}))
async def newgame(m: Message):
    if m.chat.id in games:
        return await m.answer("Bu guruhda o'yin allaqachon bor. /stopgame")
    g = Game(m.chat.id, m.from_user.id)
    g.players[m.from_user.id] = m.from_user.full_name
    games[m.chat.id] = g
    await m.answer(f"📢 RO'YXATGA OLISH BOSHLANDI!\n🎭 Mafiya o'yini ochildi.\n👮 Admin: {m.from_user.full_name}\n\n"
                   "Qo'shilish uchun pastdagi tugmani bosing. Kamida 4 kishi kerak.\n"
                   "Admin tayyor bo'lganda /oyin yozadi.",
                   reply_markup=kb([[InlineKeyboardButton(text="➕ Qo'shilish", callback_data="join")]]))


@dp.callback_query(F.data == "join")
async def join(c: CallbackQuery):
    g = games.get(c.message.chat.id)
    if not g or g.phase != "lobby":
        return await c.answer("O'yin yo'q yoki boshlangan", show_alert=True)
    g.players[c.from_user.id] = c.from_user.full_name
    await c.answer("Qo'shildingiz!")
    lst = "\n".join(f"{i+1}. {n}" for i, n in enumerate(g.players.values()))
    await c.message.answer(f"✅ {c.from_user.full_name} ro'yxatga qo'shildi.\n\n📋 Ro'yxat ({len(g.players)}):\n{lst}")


@dp.message(Command("setadmin"), F.chat.type.in_({"group", "supergroup"}))
async def setadmin(m: Message):
    g = games.get(m.chat.id)
    if not g or m.from_user.id != g.admin or not m.reply_to_message:
        return await m.answer("Admin yangi adminning xabariga reply qilib yozsin.")
    new = m.reply_to_message.from_user
    g.admin = new.id
    g.players.setdefault(new.id, new.full_name)
    await m.answer(f"👮 Yangi admin: {new.full_name}")


@dp.message(Command("stopgame"), F.chat.type.in_({"group", "supergroup"}))
async def stopgame(m: Message):
    g = games.get(m.chat.id)
    if g and m.from_user.id == g.admin:
        del games[m.chat.id]
        await m.answer("🛑 O'yin to'xtatildi.")


# ---------------- START ----------------
@dp.message(Command("startgame"), F.chat.type.in_({"group", "supergroup"}))
async def startgame(m: Message):
    g = games.get(m.chat.id)
    if g and m.from_user.id == g.admin:
        await begin(g)


async def begin(g: Game):
    if g.phase != "lobby":
        return
    if not g.admin_plays:
        g.players.pop(g.admin, None)
    n = len(g.players)
    if n < 4:
        return await bot.send_message(g.chat_id, "Kamida 4 o'yinchi kerak.")
    ids = list(g.players)
    random.shuffle(ids)
    mafia_count = max(1, n // 4)
    g.roles[ids[0]] = "don"
    for u in ids[1:mafia_count]:
        g.roles[u] = "mafia"
    rest = ids[mafia_count:]
    g.roles[rest[0]] = "doctor"
    if n >= 5:
        g.roles[rest[1]] = "com"
    for u in ids:
        g.roles.setdefault(u, "civ")
    g.alive = set(ids)
    failed = []
    for u in ids:
        try:
            text = f"Sizning rolingiz: {ROLE_NAMES[g.roles[u]]}"
            if g.roles[u] in MAFIA_TEAM:
                mates = [name(g, x) for x in ids if g.roles[x] in MAFIA_TEAM]
                text += "\nMafiya jamoasi: " + ", ".join(mates)
            await bot.send_message(u, text)
        except Exception:
            failed.append(name(g, u))
    if failed:
        del games[g.chat_id]
        return await bot.send_message(g.chat_id, "❌ Botga shaxsiy chatda /start bosmaganlar: " + ", ".join(failed))
    await bot.send_message(g.chat_id, "🔒 Ro'yxatga olish yopildi.")
    await bot.send_message(g.chat_id, f"🎬 O'yin boshlandi! {n} o'yinchi, {mafia_count} mafiya.")
    await start_night(g)


# ---------------- NIGHT ----------------
async def start_night(g: Game):
    g.phase = "night"
    g.kill = g.save = g.check = None
    g.done = set()
    alive = list(g.alive)
    mafia_alive = [u for u in alive if g.roles[u] in MAFIA_TEAM]
    killer = next((u for u in mafia_alive if g.roles[u] == "don"), mafia_alive[0])
    g.need = {killer}
    await bot.send_message(g.chat_id, "🌙 Tun tushdi. Maxsus rollar shaxsiy chatda tanlov qilsin...")
    others = [u for u in alive if g.roles[u] not in MAFIA_TEAM]
    await bot.send_message(killer, "🔪 Kimni o'ldirasiz?", reply_markup=target_kb(g, "k", others))
    for u in alive:
        if g.roles[u] == "doctor":
            g.need.add(u)
            await bot.send_message(u, "💉 Kimni davolaysiz?", reply_markup=target_kb(g, "s", alive))
        if g.roles[u] == "com":
            g.need.add(u)
            await bot.send_message(u, "🔍 Kimni tekshirasiz?",
                                   reply_markup=target_kb(g, "c", [x for x in alive if x != u]))


@dp.callback_query(F.data.regexp(r"^[ksc]:-?\d+:\d+$"))
async def night_action(c: CallbackQuery):
    kind, chat, target = c.data.split(":")
    g = games.get(int(chat))
    uid, target = c.from_user.id, int(target)
    if not g or g.phase != "night" or uid not in g.need or uid in g.done:
        return await c.answer("Hozir mumkin emas", show_alert=True)
    if kind == "k":
        g.kill = target
    elif kind == "s":
        g.save = target
    else:
        g.check = target
        res = "MAFIYA 🕴" if g.roles[target] in MAFIA_TEAM else "mafiya emas ✅"
        await bot.send_message(uid, f"{name(g, target)} — {res}")
    g.done.add(uid)
    await c.message.edit_text(f"Tanlandi: {name(g, target)}")
    if g.done == g.need:
        await morning(g)


async def morning(g: Game):
    if g.kill is not None and g.kill != g.save:
        g.alive.discard(g.kill)
        text = f"☀️ Tong otdi. Kecha {name(g, g.kill)} o'ldirildi! ({ROLE_NAMES[g.roles[g.kill]]})"
    else:
        text = "☀️ Tong otdi. Kecha hech kim o'lmadi."
    await bot.send_message(g.chat_id, text)
    if await check_win(g):
        return
    g.phase = "day"
    g.votes = {}
    alive = list(g.alive)
    await bot.send_message(
        g.chat_id, "🗳 Ovoz berish: kimni osamiz?",
        reply_markup=kb([[InlineKeyboardButton(text=name(g, u), callback_data=f"v:{g.chat_id}:{u}")] for u in alive]))


# ---------------- DAY ----------------
@dp.callback_query(F.data.regexp(r"^v:-?\d+:\d+$"))
async def vote(c: CallbackQuery):
    _, chat, target = c.data.split(":")
    g = games.get(int(chat))
    if not g or g.phase != "day" or c.from_user.id not in g.alive:
        return await c.answer("Siz ovoz bera olmaysiz", show_alert=True)
    g.votes[c.from_user.id] = int(target)
    await c.answer("Ovoz qabul qilindi")
    if len(g.votes) == len(g.alive):
        await tally(g)


@dp.message(Command("endvote"), F.chat.type.in_({"group", "supergroup"}))
async def endvote(m: Message):
    g = games.get(m.chat.id)
    if g and g.phase == "day" and m.from_user.id == g.admin:
        await tally(g)


async def tally(g: Game):
    g.phase = "tallying"
    counts = {}
    for t in g.votes.values():
        counts[t] = counts.get(t, 0) + 1
    if counts:
        top = max(counts.values())
        winners = [u for u, v in counts.items() if v == top]
    else:
        winners = []
    if len(winners) == 1:
        v = winners[0]
        g.alive.discard(v)
        await bot.send_message(g.chat_id, f"⚖️ {name(g, v)} osildi! U {ROLE_NAMES[g.roles[v]]} edi.")
    else:
        await bot.send_message(g.chat_id, "⚖️ Ovozlar teng — hech kim osilmadi.")
    if not await check_win(g):
        await start_night(g)


# ---------------- WIN / REWARDS ----------------
async def check_win(g: Game) -> bool:
    mafia = [u for u in g.alive if g.roles[u] in MAFIA_TEAM]
    civ = [u for u in g.alive if g.roles[u] not in MAFIA_TEAM]
    if mafia and len(mafia) < len(civ):
        return False
    lines = []
    if mafia:
        lines.append("🏴 MAFIYA YUTDI!\n")
        for u, r in g.roles.items():
            if r == "don":
                gift = random.choice(DON_GIFTS)
                reward(u, name(g, u), DON_COINS, gift)
                lines.append(f"👑 Don {name(g, u)}: +{DON_COINS} 🪙 va sovg'a {gift}")
            elif r == "mafia":
                gift = random.choice(MAFIA_GIFTS)
                reward(u, name(g, u), MAFIA_COINS, gift)
                lines.append(f"🕴 {name(g, u)}: +{MAFIA_COINS} 🪙 va sovg'a {gift}")
    else:
        lines.append("🏳️ TINCH AHOLI YUTDI!\n")
        for u, r in g.roles.items():
            if r not in MAFIA_TEAM:
                reward(u, name(g, u), CIV_COINS)
                lines.append(f"{name(g, u)}: +{CIV_COINS} 🪙")
    roles_txt = "\n".join(f"{ROLE_NAMES[r]} — {name(g, u)}" for u, r in g.roles.items())
    await bot.send_message(g.chat_id, "\n".join(lines) + "\n\n📋 Rollar:\n" + roles_txt)
    games.pop(g.chat_id, None)
    return True


# ---------------- CHATGA YOZIB BOSHLASH / TUGATISH ----------------
GROUP = F.chat.type.in_({"group", "supergroup"})


@dp.message(Command("oyin", "oyini"), GROUP)
async def oyin(m: Message):
    g = games.get(m.chat.id)
    if not g:
        return await newgame(m)
    if m.from_user.id != g.admin:
        return await m.answer("O'yinni faqat admin boshlaydi.")
    if g.phase == "lobby":
        await begin(g)
    else:
        await m.answer("O'yin allaqachon boshlangan. Tugatish uchun: game over")


@dp.message(GROUP, F.text.func(lambda t: t.strip().lower() in {"game over", "gameover", "o'yin tugadi"}))
async def game_over(m: Message):
    g = games.get(m.chat.id)
    if not g:
        return
    if m.from_user.id != g.admin:
        return await m.answer("O'yinni faqat admin tugata oladi.")
    roles = "\n".join(f"{ROLE_NAMES[r]} — {name(g, u)}" for u, r in g.roles.items())
    games.pop(m.chat.id, None)
    await m.answer("🏁 GAME OVER! O'yin tugatildi." + (f"\n\n📋 Rollar:\n{roles}" if roles else ""))


# ---------------- ADMIN PANEL (o'yin admini) ----------------
def panel_kb(g: Game):
    plays = "✅ Ha" if g.admin_plays else "❌ Yo'q"
    return kb([
        [InlineKeyboardButton(text="▶️ Boshlash", callback_data="p:start"),
         InlineKeyboardButton(text="🛑 To'xtatish", callback_data="p:stop")],
        [InlineKeyboardButton(text="🗳 Ovozni tugatish", callback_data="p:endvote"),
         InlineKeyboardButton(text="👥 Ro'yxat", callback_data="p:list")],
        [InlineKeyboardButton(text="🚫 O'yinchini chiqarish", callback_data="p:kick")],
        [InlineKeyboardButton(text=f"🎭 Admin o'ynaydi: {plays}", callback_data="p:toggle")],
    ])


@dp.message(Command("panel"), F.chat.type.in_({"group", "supergroup"}))
async def panel_cmd(m: Message):
    g = games.get(m.chat.id)
    if not g:
        return await m.answer("Avval /newgame yozing.")
    if m.from_user.id != g.admin:
        return await m.answer("Panel faqat admin uchun.")
    await m.answer(f"🛠 Admin paneli\nHolat: {g.phase}\nO'yinchilar: {len(g.players)}", reply_markup=panel_kb(g))


@dp.callback_query(F.data.startswith("p:"))
async def panel_action(c: CallbackQuery):
    g = games.get(c.message.chat.id)
    if not g or c.from_user.id != g.admin:
        return await c.answer("Faqat admin uchun", show_alert=True)
    act = c.data[2:]
    if act == "start":
        await c.answer()
        await begin(g)
    elif act == "stop":
        games.pop(g.chat_id, None)
        await c.message.edit_text("🛑 O'yin to'xtatildi.")
    elif act == "endvote":
        if g.phase != "day":
            return await c.answer("Hozir ovoz berish yo'q", show_alert=True)
        await c.answer()
        await tally(g)
    elif act == "list":
        txt = "\n".join(("✅ " if (g.phase == "lobby" or u in g.alive) else "💀 ") + n for u, n in g.players.items())
        await c.answer()
        await c.message.answer("👥 O'yinchilar:\n" + (txt or "yo'q"))
    elif act == "kick":
        if g.phase != "lobby":
            return await c.answer("Faqat o'yin boshlanishidan oldin", show_alert=True)
        rows = [[InlineKeyboardButton(text=n, callback_data=f"pk:{u}")] for u, n in g.players.items() if u != g.admin]
        if not rows:
            return await c.answer("Chiqaradigan odam yo'q", show_alert=True)
        await c.answer()
        await c.message.answer("Kimni chiqaramiz?", reply_markup=kb(rows))
    elif act == "toggle":
        g.admin_plays = not g.admin_plays
        await c.answer("O'zgartirildi")
        await c.message.edit_reply_markup(reply_markup=panel_kb(g))


@dp.callback_query(F.data.startswith("pk:"))
async def panel_kick(c: CallbackQuery):
    g = games.get(c.message.chat.id)
    if not g or c.from_user.id != g.admin or g.phase != "lobby":
        return await c.answer("Mumkin emas", show_alert=True)
    u = int(c.data[3:])
    n = g.players.pop(u, None)
    await c.message.edit_text(f"🚫 {n} o'yindan chiqarildi.")


# ---------------- BOT EGASI PANELI (shaxsiy chat) ----------------
def owner_only(m):
    return m.from_user.id == OWNER_ID


@dp.message(Command("admin"), F.chat.type == "private")
async def owner_panel(m: Message):
    if not owner_only(m):
        return await m.answer("⛔ Ruxsat yo'q.")
    await m.answer("🛠 Bot egasi paneli\n\nBuyruqlar:\n/broadcast matn — hammaga xabar\n"
                   "/give user_id tanga — tanga berish\n/reset user_id — foydalanuvchini tozalash",
                   reply_markup=kb([[InlineKeyboardButton(text="📊 Statistika", callback_data="o:stats"),
                                     InlineKeyboardButton(text="🏆 Reyting", callback_data="o:top")],
                                    [InlineKeyboardButton(text="🎮 Faol o'yinlar", callback_data="o:games")]]))


@dp.callback_query(F.data.startswith("o:"))
async def owner_action(c: CallbackQuery):
    if c.from_user.id != OWNER_ID:
        return await c.answer("⛔", show_alert=True)
    act = c.data[2:]
    if act == "stats":
        coins = sum(u["coins"] for u in db.values())
        gifts = sum(len(u["gifts"]) for u in db.values())
        txt = f"📊 Foydalanuvchilar: {len(db)}\n🪙 Jami tanga: {coins}\n🎁 Berilgan sovg'alar: {gifts}\n🎮 Faol o'yinlar: {len(games)}"
    elif act == "top":
        best = sorted(db.values(), key=lambda x: x["coins"], reverse=True)[:10]
        txt = "🏆 Top 10:\n" + ("\n".join(f"{i+1}. {u['name']} — {u['coins']} 🪙" for i, u in enumerate(best)) or "Bo'sh")
    else:
        txt = "🎮 Faol o'yinlar:\n" + ("\n".join(f"chat {g.chat_id}: {g.phase}, {len(g.players)} kishi" for g in games.values()) or "yo'q")
    await c.answer()
    await c.message.answer(txt)


@dp.message(Command("broadcast"), F.chat.type == "private")
async def broadcast(m: Message):
    if not owner_only(m):
        return
    text = m.text.partition(" ")[2].strip()
    if not text:
        return await m.answer("Ishlatish: /broadcast matn")
    ok = 0
    for uid in list(db):
        try:
            await bot.send_message(int(uid), text)
            ok += 1
        except Exception:
            pass
    await m.answer(f"✅ {ok} ta foydalanuvchiga yuborildi.")


@dp.message(Command("give"), F.chat.type == "private")
async def give(m: Message):
    if not owner_only(m):
        return
    try:
        _, uid, amount = m.text.split()
        u = db[uid]
        u["coins"] += int(amount)
        save_db()
        await m.answer(f"✅ {u['name']} ga {amount} 🪙 berildi.")
    except Exception:
        await m.answer("Ishlatish: /give user_id tanga (foydalanuvchi avval o'ynagan bo'lishi kerak)")


@dp.message(Command("reset"), F.chat.type == "private")
async def reset(m: Message):
    if not owner_only(m):
        return
    uid = m.text.partition(" ")[2].strip()
    if db.pop(uid, None):
        save_db()
        await m.answer("🗑 Tozalandi.")
    else:
        await m.answer("Topilmadi.")


@dp.message(Command("profile"))
async def profile(m: Message):
    u = db.get(str(m.from_user.id))
    if not u:
        return await m.answer("Hali yutuq yo'q.")
    gifts = "\n".join(u["gifts"]) or "yo'q"
    await m.answer(f"👤 {u['name']}\n🪙 Tanga: {u['coins']}\n🏆 G'alabalar: {u['wins']}\n🎁 Sovg'alar:\n{gifts}")


@dp.message(Command("top"))
async def top(m: Message):
    best = sorted(db.values(), key=lambda x: x["coins"], reverse=True)[:10]
    await m.answer("🏆 Reyting:\n" + "\n".join(f"{i+1}. {u['name']} — {u['coins']} 🪙" for i, u in enumerate(best)) or "Bo'sh")


@dp.message(Command("start"), F.chat.type == "private")
async def start(m: Message):
    await m.answer("Salom! Men Mafiya o'yini botiman. Meni guruhga qo'shing va /newgame yozing.")


async def web_server():
    from aiohttp import web
    app = web.Application()
    app.router.add_get("/", lambda r: web.Response(text="Mafiya boti ishlayapti"))
    runner = web.AppRunner(app)
    await runner.setup()
    await web.TCPSite(runner, "0.0.0.0", int(os.getenv("PORT", "10000"))).start()


async def main():
    await web_server()
    await dp.start_polling(bot)


if __name__ == "__main__":
    asyncio.run(main())

