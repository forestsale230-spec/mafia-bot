"""
Mafiya Telegram boti (True Mafia kabi) - aiogram 3
O'rnatish:   pip install aiogram
Ishga tushirish:  BOT_TOKEN=123:ABC python mafia_bot.py

Guruhda:  /game  -> ro'yxatdan o'tish boshlanadi
Har bir o'yinchi "Qo'shilish" tugmasi orqali botga o'tib /start bosadi,
shundan keyin bot unga rolni SHAXSIY xabarda yuboradi.
"""
import asyncio
import os
import random
import time
from collections import Counter
from dataclasses import dataclass, field
from html import escape

from aiogram import Bot, Dispatcher, F
from aiogram.client.default import DefaultBotProperties
from aiogram.enums import ChatType, ParseMode
from aiogram.filters import Command, CommandObject
from aiogram.types import CallbackQuery, InlineKeyboardButton, InlineKeyboardMarkup, Message

TOKEN = os.getenv("BOT_TOKEN", "9124751414:AAGL0-Sj8Y2CksynJLEsiYdcIyv4PGdA2bQ")

# ---- Sozlamalar -------------------------------------------------------------
MIN_PLAYERS = 4
REG_TIME = 60      # ro'yxatdan o'tish (sekund)
NIGHT_TIME = 45    # tun
TALK_TIME = 30     # kunduzgi muhokama
VOTE_TIME = 45     # ovoz berish

# GIF: giphy/tenor to'g'ridan-to'g'ri .gif/.mp4 havolasi YOKI file_id.
# Bo'sh qoldirsangiz, bot oddiy matn yuboradi.
# Tavsiya: o'zingiz GIF'ni botga yuboring, file_id'ni oling (pastdagi /fileid).
GIFS = {
    "night": "",
    "day1": "",
    "day2": "",
    "day3": "",
    "win_mafia": "",
    "win_city": "",
    "kill": "",
}

ROLE_NAME = {
    "don": "🤵🏻 Don",
    "mafia": "🤵🏼 Mafia",
    "doctor": "👨🏼‍⚕️ Shifokor",
    "cop": "🕵🏼 Komissar",
    "civil": "👨🏼 Tinch axoli",
}
ROLE_DESC = {
    "don": "Siz - 🤵🏻 Donsiz!\nMafiyaga boshchilik qilasiz. Qurbonni tanlashda sizning ovozingiz hal qiluvchi.",
    "mafia": "Siz - 🤵🏼 Mafiasiz!\nDonga bo'ysunasiz va sizga qarshilik qilganlarni o'ldirasiz. Don o'lsa siz yangi Don bo'lishingiz mumkin.",
    "doctor": "Siz - 👨🏼‍⚕️ Shifokorsiz!\nHar tun bitta odamni davolab, o'limdan qutqarasiz.",
    "cop": "Siz - 🕵🏼 Komissarsiz!\nHar tun bitta odamning rolini tekshirasiz.",
    "civil": "Siz - 👨🏼 Tinch axolisiz!\nKunduzi ovoz berib mafiyani toping.",
}

bot: Bot
games: dict[int, "Game"] = {}      # chat_id -> Game
user_game: dict[int, int] = {}     # user_id -> chat_id


@dataclass
class Player:
    uid: int
    name: str
    role: str = "civil"
    alive: bool = True


@dataclass
class Game:
    chat_id: int
    players: dict[int, Player] = field(default_factory=dict)
    phase: str = "reg"             # reg / night / vote / end
    day: int = 0
    started_at: float = 0.0
    mafia_votes: dict[int, int] = field(default_factory=dict)
    heal: int | None = None
    check_done: bool = False
    day_votes: dict[int, int] = field(default_factory=dict)

    def alive(self):
        return [p for p in self.players.values() if p.alive]

    def mafia_alive(self):
        return [p for p in self.alive() if p.role in ("don", "mafia")]

    def by_role(self, role):
        return [p for p in self.alive() if p.role == role]


def mention(p: Player) -> str:
    return f'<a href="tg://user?id={p.uid}">{escape(p.name)}</a>'


def players_list(g: Game, only_alive=True) -> str:
    src = g.alive() if only_alive else list(g.players.values())
    return "\n".join(f"{i}. {mention(p)}" for i, p in enumerate(src, 1))


async def send_gif(chat_id, key, text, markup=None):
    gif = GIFS.get(key)
    if gif:
        try:
            return await bot.send_animation(chat_id, gif, caption=text, reply_markup=markup)
        except Exception:
            pass
    return await bot.send_message(chat_id, text, reply_markup=markup)


async def dm(uid, text, markup=None):
    try:
        return await bot.send_message(uid, text, reply_markup=markup)
    except Exception:
        return None


async def bot_link(start: str = "") -> str:
    me = await bot.get_me()
    return f"https://t.me/{me.username}" + (f"?start={start}" if start else "")


def choose_kb(prefix: str, g: Game, targets: list[Player]) -> InlineKeyboardMarkup:
    rows = [[InlineKeyboardButton(text=p.name, callback_data=f"{prefix}:{g.chat_id}:{p.uid}")] for p in targets]
    return InlineKeyboardMarkup(inline_keyboard=rows)


# ---- Buyruqlar ----------------------------------------------------------------
async def cmd_game(m: Message):
    if m.chat.type not in (ChatType.GROUP, ChatType.SUPERGROUP):
        return await m.answer("Bu buyruq faqat guruhda ishlaydi.")
    if m.chat.id in games:
        return await m.answer("Bu guruhda o'yin allaqachon boshlangan.")
    g = Game(chat_id=m.chat.id)
    games[m.chat.id] = g
    kb = InlineKeyboardMarkup(inline_keyboard=[[
        InlineKeyboardButton(text="➕ Qo'shilish", url=await bot_link(f"join_{m.chat.id}"))
    ]])
    await m.answer(
        f"🎮 <b>Mafia o'yini</b> boshlandi!\nRo'yxatdan o'tish: {REG_TIME} sekund.\n"
        f"Kamida {MIN_PLAYERS} o'yinchi kerak.", reply_markup=kb)
    asyncio.create_task(run_game(g))


async def cmd_start(m: Message, command: CommandObject):
    arg = command.args or ""
    if m.chat.type != ChatType.PRIVATE:
        return
    if not arg.startswith("join_"):
        return await m.answer("Salom! Meni guruhga qo'shing va guruhda /game yozing 🎮")
    chat_id = int(arg[5:])
    g = games.get(chat_id)
    if not g or g.phase != "reg":
        return await m.answer("Hozir bu guruhda ro'yxatdan o'tish yo'q.")
    if m.from_user.id in g.players:
        return await m.answer("Siz allaqachon ro'yxatdasiz.")
    if m.from_user.id in user_game:
        return await m.answer("Siz boshqa o'yinda qatnashyapsiz.")
    g.players[m.from_user.id] = Player(m.from_user.id, m.from_user.full_name)
    user_game[m.from_user.id] = chat_id
    chat = await bot.get_chat(chat_id)
    await m.answer(f"Siz o'yinga omadli qo'shildingiz <b>{escape(chat.title or '')}</b>")
    await bot.send_message(chat_id, f"➕ {escape(m.from_user.full_name)} qo'shildi. Jami: {len(g.players)}")


async def cmd_fileid(m: Message):
    """GIF'ni botga yuboring - file_id qaytaradi (GIFS lug'atiga qo'yish uchun)."""
    if m.animation:
        await m.answer(f"<code>{m.animation.file_id}</code>")


async def cmd_stop(m: Message):
    g = games.get(m.chat.id)
    if g:
        await finish(g, None, "O'yin to'xtatildi.")


# ---- O'yin jarayoni -----------------------------------------------------------
def assign_roles(g: Game):
    ps = list(g.players.values())
    random.shuffle(ps)
    n = len(ps)
    mafia_total = max(1, n // 4)
    roles = ["don"] + ["mafia"] * (mafia_total - 1)
    roles.append("doctor")
    if n >= 5:
        roles.append("cop")
    roles += ["civil"] * (n - len(roles))
    for p, r in zip(ps, roles):
        p.role = r


async def send_roles(g: Game):
    mafia = g.mafia_alive()
    for p in g.players.values():
        text = ROLE_DESC[p.role]
        if p.role in ("don", "mafia") and len(mafia) > 1:
            team = "\n".join(f"{mention(x)} - {ROLE_NAME[x.role]}" for x in mafia if x.uid != p.uid)
            text += f"\n\n<b>Sheriklaringizni eslab qoling:</b>\n{team}"
        await dm(p.uid, text)


def win_check(g: Game):
    m = len(g.mafia_alive())
    others = len(g.alive()) - m
    if m == 0:
        return "city"
    if m >= others:
        return "mafia"
    return None


async def finish(g: Game, winner: str | None, note: str = ""):
    g.phase = "end"
    games.pop(g.chat_id, None)
    for uid in g.players:
        user_game.pop(uid, None)
    if winner is None:
        return await bot.send_message(g.chat_id, note)
    win_roles = ("don", "mafia") if winner == "mafia" else ("doctor", "cop", "civil")
    winners = [p for p in g.players.values() if p.role in win_roles]
    losers = [p for p in g.players.values() if p.role not in win_roles]
    dur = int(time.time() - g.started_at)
    title = "Mafia g'alaba qozondi" if winner == "mafia" else "Tinch axoli g'alaba qozondi"
    text = (
        f"<b>O'yin tugadi!</b>\n{title}\n\n"
        f"<b>G'oliblar:</b>\n" + "\n".join(f"  {mention(p)} - {ROLE_NAME[p.role]}" for p in winners) +
        f"\n\n<b>Qolgan o'yinchilar:</b>\n" + "\n".join(f"  {mention(p)} - {ROLE_NAME[p.role]}" for p in losers) +
        f"\n\nO'yin: {dur // 60} min. {dur % 60} sek. davom etdi"
    )
    await send_gif(g.chat_id, "win_mafia" if winner == "mafia" else "win_city", text)


async def wait_until(seconds: int, cond):
    for _ in range(seconds):
        if cond():
            return
        await asyncio.sleep(1)


async def run_game(g: Game):
    await asyncio.sleep(REG_TIME)
    if len(g.players) < MIN_PLAYERS:
        games.pop(g.chat_id, None)
        for uid in g.players:
            user_game.pop(uid, None)
        return await bot.send_message(g.chat_id, "O'yinni boshlash uchun o'yinchilar yetarli emas...")
    g.started_at = time.time()
    assign_roles(g)
    await send_roles(g)
    await bot.send_message(g.chat_id, "<b>O'yin boshlandi!</b>\nBir necha soniya ichida bot sizga rol va uning tavsifi bilan shaxsiy xabar yuboradi.")
    await asyncio.sleep(3)

    while True:
        g.day += 1
        # ---------------- TUN ----------------
        g.phase = "night"
        g.mafia_votes.clear()
        g.heal = None
        g.check_done = False
        kb = InlineKeyboardMarkup(inline_keyboard=[[InlineKeyboardButton(text="Botga o'tish", url=await bot_link())]])
        await send_gif(g.chat_id, "night",
                       "🌃 <b>Tun</b>\nKo'chaga faqat jasur va qo'rqmas odamlar chiqishdi. Ertalab tirik qolganlarni sanaymiz...", kb)
        await bot.send_message(g.chat_id, f"<b>Tirik o'yinchilar:</b>\n{players_list(g)}\n\nTonggacha {NIGHT_TIME} sek. qoldi")

        mafia = g.mafia_alive()
        for p in mafia:
            targets = [x for x in g.alive() if x.role not in ("don", "mafia")]
            await dm(p.uid, "<b>Mafia keyingi qurboni uchun ovoz berish o'tkazyapti:</b>", choose_kb("k", g, targets))
        for p in g.by_role("doctor"):
            await dm(p.uid, "Kimni davolamoqchisiz?", choose_kb("d", g, g.alive()))
        for p in g.by_role("cop"):
            await dm(p.uid, "Kimni tekshirmoqchisiz?", choose_kb("c", g, [x for x in g.alive() if x.uid != p.uid]))

        def night_done():
            return (all(p.uid in g.mafia_votes for p in g.mafia_alive())
                    and (not g.by_role("doctor") or g.heal is not None)
                    and (not g.by_role("cop") or g.check_done))
        await wait_until(NIGHT_TIME, night_done)

        # tun natijasi
        victim = None
        if g.mafia_votes:
            don = next((p for p in g.mafia_alive() if p.role == "don"), None)
            if don and don.uid in g.mafia_votes:
                victim = g.mafia_votes[don.uid]
            else:
                c = Counter(g.mafia_votes.values()).most_common()
                top = [u for u, n in c if n == c[0][1]]
                victim = random.choice(top)
        g.phase = "day"
        await send_gif(g.chat_id, f"day{min(g.day, 3)}",
                       f"🏙 <b>{g.day}-kun</b>\nQuyosh chiqib, tunda to'kilgan qonlarni quritdi...")
        if victim is not None and victim != g.heal:
            v = g.players[victim]
            v.alive = False
            await send_gif(g.chat_id, "kill", f"Tunda {ROLE_NAME[v.role]} {mention(v)} vahshiylarcha o'ldirildi...")
            await dm(v.uid, "Sizni o'ldirishdi :(")
        else:
            await bot.send_message(g.chat_id, "Ishonish qiyin, lekin bu tunda hech kim o'lmadi 😮")
        w = win_check(g)
        if w:
            return await finish(g, w)

        # ---------------- KUNDUZ ----------------
        alive = g.alive()
        counts = Counter(ROLE_NAME[p.role] for p in alive if p.role in ("doctor", "cop", "don"))
        civ = sum(1 for p in alive if p.role in ("civil", "mafia"))
        roles_txt = ", ".join(counts.keys()) + (f", {civ} ta boshqa" if civ else "")
        await bot.send_message(
            g.chat_id,
            f"<b>Tirik o'yinchilar:</b>\n{players_list(g)}\n\n<b>Ulardan kimlar:</b>\n{roles_txt}\n"
            f"Jami: {len(alive)} kishi.\n\nTunda bo'lgan xodisalarni muxokama qilishning ayni vaqti... ({TALK_TIME} sek.)")
        await asyncio.sleep(TALK_TIME)

        # ---------------- OVOZ BERISH ----------------
        g.phase = "vote"
        g.day_votes.clear()
        kb = InlineKeyboardMarkup(inline_keyboard=[[InlineKeyboardButton(text="Ovoz berish", url=await bot_link())]])
        await bot.send_message(
            g.chat_id, f"⚖️ Aybdorlarni aniqlash va jazolash vaqti keldi.\nOvoz berish uchun {VOTE_TIME} sekund", reply_markup=kb)
        for p in g.alive():
            await dm(p.uid, "Kimni osmoqchisiz? Ovoz bering:", choose_kb("v", g, [x for x in g.alive() if x.uid != p.uid]))
        await wait_until(VOTE_TIME, lambda: len(g.day_votes) >= len(g.alive()))

        if g.day_votes:
            c = Counter(g.day_votes.values()).most_common()
            if len(c) == 1 or c[0][1] > c[1][1]:
                v = g.players[c[0][0]]
                v.alive = False
                await bot.send_message(g.chat_id, f"{mention(v)} - {ROLE_NAME[v.role]} edi. Xalq uni osdi ⚰️")
                await dm(v.uid, "Sizni osishdi :(")
            else:
                await bot.send_message(g.chat_id, "Fikrlar bo'linib ketdi... Hech kim osilmadi.")
        else:
            await bot.send_message(g.chat_id, "Hech kim ovoz bermadi. Hech kim osilmadi.")
        w = win_check(g)
        if w:
            return await finish(g, w)


# ---- Tugmalar (shaxsiy chatda) ----------------------------------------------------
async def on_choice(c: CallbackQuery):
    prefix, chat_id, target = c.data.split(":")
    g = games.get(int(chat_id))
    me = g.players.get(c.from_user.id) if g else None
    if not g or not me or not me.alive:
        return await c.answer("Siz bu o'yinda emassiz yoki o'lgansiz.", show_alert=True)
    t = g.players.get(int(target))
    if not t or not t.alive:
        return await c.answer("Bu o'yinchi tirik emas.", show_alert=True)

    if prefix == "k" and g.phase == "night" and me.role in ("don", "mafia"):
        g.mafia_votes[me.uid] = t.uid
        await c.message.edit_text(f"Siz <b>{escape(t.name)}</b> ni tanladingiz")
        for p in g.mafia_alive():     # sheriklarga ko'rinadi (Don ... uchun ovoz berdi)
            if p.uid != me.uid:
                await dm(p.uid, f"{ROLE_NAME[me.role]} {mention(me)} - {escape(t.name)} uchun ovoz berdi")
    elif prefix == "d" and g.phase == "night" and me.role == "doctor":
        g.heal = t.uid
        await c.message.edit_text(f"Siz <b>{escape(t.name)}</b> ni davolashni tanladingiz")
    elif prefix == "c" and g.phase == "night" and me.role == "cop" and not g.check_done:
        g.check_done = True
        shown = "🤵 Mafiya a'zosi" if t.role in ("don", "mafia") else "🙂 Tinch (mafiya emas)"
        await c.message.edit_text(f"<b>{escape(t.name)}</b> - {shown}")
    elif prefix == "v" and g.phase == "vote":
        g.day_votes[me.uid] = t.uid
        await c.message.edit_text(f"Siz <b>{escape(t.name)}</b> ga ovoz berdingiz")
        await bot.send_message(g.chat_id, f"{mention(me)} {mention(t)} uchun ovoz berdi")
    else:
        return await c.answer("Hozir bu amalni bajarib bo'lmaydi.", show_alert=True)
    await c.answer()


async def main():
    global bot
    bot = Bot(TOKEN, default=DefaultBotProperties(parse_mode=ParseMode.HTML))
    dp = Dispatcher()
    dp.message.register(cmd_game, Command("game"))
    dp.message.register(cmd_stop, Command("stop"))
    dp.message.register(cmd_start, Command("start"))
    dp.message.register(cmd_fileid, F.animation)
    dp.callback_query.register(on_choice, F.data.regexp(r"^[kdcv]:-?\d+:\d+$"))
    await dp.start_polling(bot)


if __name__ == "__main__":
    asyncio.run(main())
