"""
FemWare Discord Bot
- кнопки в #get-keys: Redeem Key / Get Key / Reset HWID / Get Role
- REST API для сайта: POST /api/admin/keys  — генерация ключей
                      GET  /api/admin/keys  — список всех ключей
                      POST /api/admin/revoke — отозвать ключ

Ключ активен один раз: сайт создаёт со статусом "active",
бот меняет на "used" — повторный редим заблокирован на уровне asyncio.Lock.

Запуск:
  pip install -U discord.py aiohttp
  BOT_TOKEN=... API_SECRET=... python bot.py
"""

import discord
from discord.ext import commands
from discord import ui
from aiohttp import web
import asyncio, hmac, json, os, re, secrets, string, time
from datetime import datetime, timedelta

# ── config ───────────────────────────────────────────────────────────────
BOT_TOKEN     = os.environ.get("BOT_TOKEN", "MTU1ODk4NzAyNjQ1MDA5MjA0Mg.G7jHLK.41jNx-UTZptuv3wyi_oXljzWZNwUm6iDD4PaUQ")
API_SECRET    = os.environ.get("API_SECRET", "CHANGE_ME_32_CHARS_MIN")
API_PORT      = int(os.environ.get("API_PORT", "8080"))
SITE_ORIGIN   = "https://conneci.github.io"      # FILL: твой домен сайта
SCRIPT_LINK   = "https://yourlink.com"           # FILL: ссылка на скрипт
FUNPAY_LINK   = "https://funpay.com/"            # FILL: ссылка на лот FunPay
BUYER_ROLE    = "Buyer"
PANEL_CHANNEL = "get-keys"
KEYS_FILE     = "keys.json"
HWID_FILE     = "hwids.json"
# ─────────────────────────────────────────────────────────────────────────

KEY_RE   = re.compile(r'^[A-Z0-9]{4}-[A-Z0-9]{4}-[A-Z0-9]{4}-[A-Z0-9]{4}$')
KEY_LOCK = asyncio.Lock()

C_OK, C_ERR, C_ACCENT, C_NEUTRAL, C_WARN = 0x00dc82, 0xff3b6b, 0xb84aff, 0x1e1e2e, 0xffb400

# ── storage ───────────────────────────────────────────────────────────────
def _load(path):
    if not os.path.exists(path): return {}
    with open(path, encoding="utf-8") as f: return json.load(f)

def _save(path, data):
    tmp = path + ".tmp"
    with open(tmp, "w", encoding="utf-8") as f: json.dump(data, f, indent=2)
    os.replace(tmp, path)

def load_keys():   return _load(KEYS_FILE)
def save_keys(d):  _save(KEYS_FILE, d)
def load_hwids():  return _load(HWID_FILE)
def save_hwids(d): _save(HWID_FILE, d)
def ts():          return datetime.utcnow().strftime("%d/%m/%Y %H:%M UTC")
def emb(t, d, c):  return discord.Embed(title=t, description=d, color=c)

def gen_key():
    a = string.ascii_uppercase + string.digits
    return "-".join("".join(secrets.choice(a) for _ in range(4)) for _ in range(4))

def has_redeemed(uid: str) -> bool:
    return any(
        v.get("used_id") == uid and v.get("status") == "used"
        for v in load_keys().values()
    )

# ── redeem core (race-safe, one-time) ────────────────────────────────────
async def redeem_key(raw: str, user: discord.abc.User):
    """Returns (code, entry). code: ok | format | missing | used | mine | revoked | bad"""
    key = raw.strip().upper()
    if not KEY_RE.match(key):
        return "format", None
    async with KEY_LOCK:
        keys = load_keys()
        entry = keys.get(key)
        if entry is None:
            return "missing", None
        st = entry.get("status", "active")
        if st == "revoked":
            return "revoked", entry
        if st == "used":
            return ("mine" if entry.get("used_id") == str(user.id) else "used"), entry
        if st != "active":
            return "bad", entry
        entry.update(
            status="used",
            used_by=str(user),
            used_id=str(user.id),
            used_at=ts()
        )
        save_keys(keys)
        return "ok", entry

# ── redeem modal ──────────────────────────────────────────────────────────
class RedeemModal(ui.Modal, title="Redeem your FemWare key"):
    key_input = ui.TextInput(
        label="Your Key",
        placeholder="XXXX-XXXX-XXXX-XXXX",
        min_length=19, max_length=19
    )

    async def on_submit(self, interaction: discord.Interaction):
        code, entry = await redeem_key(self.key_input.value, interaction.user)
        key = self.key_input.value.strip().upper()

        if code == "format":
            e = emb("❌ Неверный формат",
                    "Ключ должен выглядеть так: `XXXX-XXXX-XXXX-XXXX`.\n"
                    "Проверь, правильно ли скопировал.", C_ERR)

        elif code == "missing":
            e = emb("❌ Ключ не найден",
                    "Такого ключа нет в системе.\n\n"
                    "Скопируй ключ из чата заказа на FunPay и попробуй снова.", C_ERR)

        elif code == "revoked":
            e = emb("❌ Ключ отозван",
                    "Этот ключ был деактивирован. Обратись в поддержку.", C_ERR)

        elif code == "mine":
            e = emb("ℹ️ Ты уже активировал этот ключ",
                    f"Активирован **{entry.get('used_at')}**.\n\n"
                    f"Нажми **Get Role** чтобы получить @{BUYER_ROLE}.\n"
                    f"Нажми **Reset HWID** если сменил железо.", C_WARN)

        elif code == "used":
            e = emb("❌ Ключ уже использован",
                    f"Этот ключ активировал `{entry.get('used_by')}` — **{entry.get('used_at')}**.\n\n"
                    "Если считаешь, что это ошибка — обратись в поддержку.", C_ERR)

        elif code == "bad":
            e = emb("❌ Ключ недействителен",
                    f"Статус ключа: `{entry.get('status')}`. Обратись в поддержку.", C_ERR)

        else:  # ok
            e = emb("✅ Ключ принят — FemWare",
                    f"Добро пожаловать, {interaction.user.mention}!\n\n"
                    f"**Продукт:** {entry.get('product', 'FemWare — Script')}\n"
                    f"**Срок:** {entry.get('duration', 'Lifetime')}\n\n"
                    f"**Твой скрипт:**\n> [Скачать здесь]({SCRIPT_LINK})\n\n"
                    f"⚠️ Не делись ссылкой — ключ привязан к твоему аккаунту.\n"
                    f"Нажми **Get Role** чтобы получить @{BUYER_ROLE}.", C_OK)
            e.set_footer(text="FemWare • поддержка в #support")

        await interaction.response.send_message(embed=e, ephemeral=True)

        if code == "ok" and interaction.guild:
            ch = discord.utils.get(interaction.guild.text_channels, name="key-logs")
            if ch:
                await ch.send(embed=discord.Embed(
                    title="🔑 Ключ активирован",
                    description=(
                        f"**Пользователь:** {interaction.user} (`{interaction.user.id}`)\n"
                        f"**Ключ:** ||{key}||\n"
                        f"**Продукт:** {entry.get('product', 'FemWare')}\n"
                        f"**Срок:** {entry.get('duration', 'Lifetime')}"
                    ),
                    color=C_ACCENT,
                    timestamp=datetime.utcnow()
                ))

# ── panel ─────────────────────────────────────────────────────────────────
def panel_embed():
    e = discord.Embed(
        title="FemWare",
        description=(
            "**Скрипты для Project Delta.**\n"
            "Стабильно, мощно, актуально после каждого патча.\n\n"
            "🔑 **Redeem Key** — ввести ключ и получить скрипт\n"
            "🛒 **Get Key** — купить на FunPay, ключ придёт в чате заказа\n"
            "🔄 **Reset HWID** — сбросить железо (раз в 7 дней)\n"
            "👤 **Get Role** — получить роль @Buyer после активации"
        ),
        color=C_ACCENT
    )
    e.set_footer(text="FemWare")
    return e

class FemWarePanel(ui.View):
    def __init__(self): super().__init__(timeout=None)

    @ui.button(label="Redeem Key", emoji="🔑", style=discord.ButtonStyle.primary, custom_id="fw_redeem")
    async def redeem(self, interaction: discord.Interaction, button: ui.Button):
        await interaction.response.send_modal(RedeemModal())

    @ui.button(label="Shop", emoji="🛒", style=discord.ButtonStyle.secondary, custom_id="fw_getkey")
    async def getkey(self, interaction: discord.Interaction, button: ui.Button):
        e = emb(
            "🛒 Купить FemWare",
            f"[**→ Наш лот на FunPay**]({FUNPAY_LINK})\n\n"
            "1. Купи лот на FunPay\n"
            "2. Ключ придёт прямо в чате заказа FunPay\n"
            "3. Вернись сюда и нажми **Redeem Key**\n"
            "4. Нажми **Get Role** чтобы открыть каналы для покупателей",
            C_ACCENT
        )
        await interaction.response.send_message(embed=e, ephemeral=True)

    @ui.button(label="Reset HWID", emoji="🔄", style=discord.ButtonStyle.secondary, custom_id="fw_hwid")
    async def reset_hwid(self, interaction: discord.Interaction, button: ui.Button):
        uid = str(interaction.user.id)
        if not has_redeemed(uid):
            return await interaction.response.send_message(
                embed=emb("❌ Нет активной лицензии", "Сначала активируй ключ.", C_ERR),
                ephemeral=True
            )
        hwids = load_hwids()
        last = hwids.get(uid, {}).get("last_reset")
        if last:
            passed = datetime.utcnow() - datetime.strptime(last, "%d/%m/%Y %H:%M UTC")
            if passed < timedelta(days=7):
                left = timedelta(days=7) - passed
                h, m = divmod(left.seconds // 60, 60)
                return await interaction.response.send_message(
                    embed=emb("⏳ Кулдаун", f"Следующий сброс через **{left.days}д {h}ч {m}м**.", C_WARN),
                    ephemeral=True
                )
        hwids[uid] = {"last_reset": ts(), "user": str(interaction.user)}
        save_hwids(hwids)
        await interaction.response.send_message(
            embed=emb("🔄 HWID сброшен",
                      "Готово. Перезапусти лоадер чтобы зарегистрировать новое железо.\n"
                      "*Следующий сброс через 7 дней.*", C_OK),
            ephemeral=True
        )
        ch = discord.utils.get(interaction.guild.text_channels, name="key-logs")
        if ch:
            await ch.send(embed=discord.Embed(
                title="🔄 HWID сброшен",
                description=f"**Пользователь:** {interaction.user} (`{interaction.user.id}`)",
                color=C_NEUTRAL,
                timestamp=datetime.utcnow()
            ))

    @ui.button(label="Get Role", emoji="👤", style=discord.ButtonStyle.success, custom_id="fw_role")
    async def get_role(self, interaction: discord.Interaction, button: ui.Button):
        if not has_redeemed(str(interaction.user.id)):
            return await interaction.response.send_message(
                embed=emb("❌ Нет активной лицензии",
                          "Сначала активируй ключ через **Redeem Key**, потом жми **Get Role**.", C_ERR),
                ephemeral=True
            )
        role = discord.utils.get(interaction.guild.roles, name=BUYER_ROLE)
        if not role:
            return await interaction.response.send_message(
                f"❌ Роль `{BUYER_ROLE}` не найдена на сервере. Попроси админа создать её.",
                ephemeral=True
            )
        if role in interaction.user.roles:
            return await interaction.response.send_message(
                embed=emb("✅ Уже есть роль", f"У тебя уже есть **@{BUYER_ROLE}**.", C_OK),
                ephemeral=True
            )
        await interaction.user.add_roles(role, reason="FemWare key redeemed")
        await interaction.response.send_message(
            embed=emb("✅ Роль выдана",
                      f"Ты получил **@{BUYER_ROLE}**. Каналы для покупателей теперь открыты.", C_OK),
            ephemeral=True
        )

# ── admin API (вызывается с сайта) ────────────────────────────────────────
_FAILS: dict = {}

def check_auth(request: web.Request):
    ip = request.headers.get("CF-Connecting-IP") or request.remote or "?"
    n, t = _FAILS.get(ip, (0, 0))
    if n and time.time() - t > 900: n = 0
    if n >= 5:
        raise web.HTTPTooManyRequests(text="too many failed attempts, try in 15min")
    if not hmac.compare_digest(request.headers.get("X-Api-Secret", ""), API_SECRET):
        _FAILS[ip] = (n + 1, time.time())
        raise web.HTTPUnauthorized(text="bad secret")
    _FAILS.pop(ip, None)

async def body_json(request: web.Request):
    try: return await request.json()
    except Exception: raise web.HTTPBadRequest(text="bad json")

async def api_gen(request: web.Request):
    """POST /api/admin/keys {"count": 1-200, "duration": "Lifetime"} → {"keys": [...]}"""
    check_auth(request)
    b = await body_json(request)
    try: count = max(1, min(int(b.get("count", 1)), 200))
    except (TypeError, ValueError): raise web.HTTPBadRequest(text="count must be int")
    duration = str(b.get("duration", "Lifetime"))[:32]
    new = []
    async with KEY_LOCK:
        keys = load_keys()
        attempts = 0
        while len(new) < count:
            k = gen_key()
            if k in keys:
                attempts += 1
                if attempts > 10_000: break   # keyspace collision guard
                continue
            keys[k] = {
                "status":   "active",
                "product":  "FemWare — Script",
                "duration": duration,
                "created":  ts(),
                "provider": "site",
                "used_by":  None,
                "used_id":  None,
                "used_at":  None,
            }
            new.append(k)
        save_keys(keys)
    return web.json_response({"keys": new})

async def api_list(request: web.Request):
    """GET /api/admin/keys → {"keys": {key: entry}}"""
    check_auth(request)
    return web.json_response({"keys": load_keys()})

async def api_revoke(request: web.Request):
    """POST /api/admin/revoke {"key": "XXXX-XXXX-XXXX-XXXX"} → {"key": ..., "status": "revoked"}"""
    check_auth(request)
    key = str((await body_json(request)).get("key", "")).strip().upper()
    async with KEY_LOCK:
        keys = load_keys()
        if key not in keys:
            raise web.HTTPNotFound(text="key not found")
        keys[key]["status"] = "revoked"
        save_keys(keys)
    return web.json_response({"key": key, "status": "revoked"})

@web.middleware
async def cors(request: web.Request, handler):
    try:
        resp = web.Response() if request.method == "OPTIONS" else await handler(request)
    except web.HTTPException as e:
        resp = e
    resp.headers.update({
        "Access-Control-Allow-Origin":  SITE_ORIGIN,
        "Access-Control-Allow-Headers": "Content-Type, X-Api-Secret",
        "Access-Control-Allow-Methods": "GET, POST, OPTIONS",
    })
    return resp

async def start_api():
    app = web.Application(middlewares=[cors])
    app.add_routes([
        web.post  ("/api/admin/keys",   api_gen),
        web.get   ("/api/admin/keys",   api_list),
        web.post  ("/api/admin/revoke", api_revoke),
        web.route ("OPTIONS", "/{tail:.*}", lambda r: web.Response()),
    ])
    runner = web.AppRunner(app)
    await runner.setup()
    await web.TCPSite(runner, "0.0.0.0", API_PORT).start()
    print(f"[FemWare] admin API running on :{API_PORT}")

# ── bot ───────────────────────────────────────────────────────────────────
intents = discord.Intents.default()
intents.members = True

class FemBot(commands.Bot):
    async def setup_hook(self):
        self.add_view(FemWarePanel())   # persistent view survives restarts
        await start_api()

bot = FemBot(command_prefix="!", intents=intents)
_panel_sent = False

@bot.event
async def on_ready():
    global _panel_sent
    print(f"[FemWare] online as {bot.user}")
    if _panel_sent: return          # не спамить при реконнекте
    _panel_sent = True
    for guild in bot.guilds:
        ch = discord.utils.get(guild.text_channels, name=PANEL_CHANNEL)
        if not ch:
            print(f"[FemWare] #{PANEL_CHANNEL} not found in {guild.name}")
            continue
        async for msg in ch.history(limit=50):
            if msg.author == bot.user: await msg.delete()
        await ch.send(embed=panel_embed(), view=FemWarePanel())
        print(f"[FemWare] panel sent to #{PANEL_CHANNEL} in {guild.name}")

bot.run(BOT_TOKEN)
