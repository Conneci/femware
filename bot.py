"""
FemWare Discord Bot — button UI
Commands:
  /panel  — sends the main button panel (admin only, use in a channel)
  /addkey — admin: add a key manually

Buttons:
  🔑 Redeem Key  — user enters key, gets script link, key marked used
  🛒 Get Key     — sends link to the shop
  🔄 Reset HWID  — resets HWID for user (stub — wire to your loader)
  👤 Get Role    — gives @Buyer role if user has a valid redeemed key

Setup:
  pip install discord.py
  python femware_bot.py
"""

import discord
from discord.ext import commands
from discord import app_commands, ui
import json, os, re
from datetime import datetime

# ── config ──────────────────────────────────────────────────────────────
BOT_TOKEN    = "MTU1ODk4NzAyNjQ1MDA5MjA0Mg.GWXoOq.YZHSBAQ-6nnfqjck8fZ3H8UzSvNvy3q9uoCBLU"
ADMIN_IDS    = [1488535363655045373]               # your Discord user ID
SCRIPT_LINK  = "https://yourlink.com"   # script download link
SHOP_LINK    = "https://femware.vercel.app"
BUYER_ROLE   = "Buyer"                  # exact role name in your server
KEYS_FILE    = "keys.json"
HWID_FILE    = "hwids.json"
# ────────────────────────────────────────────────────────────────────────

KEY_RE = re.compile(r'^[A-Z0-9]{4}-[A-Z0-9]{4}-[A-Z0-9]{4}-[A-Z0-9]{4}$')

def load_keys():
    if not os.path.exists(KEYS_FILE): return {}
    with open(KEYS_FILE) as f: return json.load(f)

def save_keys(data):
    with open(KEYS_FILE, "w") as f: json.dump(data, f, indent=2)

def load_hwids():
    if not os.path.exists(HWID_FILE): return {}
    with open(HWID_FILE) as f: return json.load(f)

def save_hwids(data):
    with open(HWID_FILE, "w") as f: json.dump(data, f, indent=2)

def ts(): return datetime.utcnow().strftime("%d/%m/%Y %H:%M UTC")

# ── color palette ────────────────────────────────────────────────────────
C_OK      = 0x00dc82
C_ERR     = 0xff3b6b
C_ACCENT  = 0xb84aff
C_NEUTRAL = 0x1e1e2e

# ── modals ───────────────────────────────────────────────────────────────
class RedeemModal(ui.Modal, title="Redeem your FemWare key"):
    key_input = ui.TextInput(
        label="Your Key",
        placeholder="XXXX-XXXX-XXXX-XXXX",
        min_length=19, max_length=19,
        style=discord.TextStyle.short
    )

    async def on_submit(self, interaction: discord.Interaction):
        key = self.key_input.value.strip().upper()

        if not KEY_RE.match(key):
            embed = discord.Embed(title="❌ Invalid format",
                description="Key must be `XXXX-XXXX-XXXX-XXXX`.", color=C_ERR)
            await interaction.response.send_message(embed=embed, ephemeral=True)
            return

        keys = load_keys()

        if key not in keys:
            embed = discord.Embed(title="❌ Key not found",
                description="This key doesn't exist. Check your profile on the site.", color=C_ERR)
            await interaction.response.send_message(embed=embed, ephemeral=True)
            return

        entry = keys[key]

        if entry["status"] == "used":
            embed = discord.Embed(title="❌ Already used",
                description=f"This key was already redeemed by `{entry.get('used_by','unknown')}`.\nContact support if this is an error.",
                color=C_ERR)
            await interaction.response.send_message(embed=embed, ephemeral=True)
            return

        if entry["status"] == "revoked":
            embed = discord.Embed(title="❌ Key revoked",
                description="This key has been revoked. Contact support.", color=C_ERR)
            await interaction.response.send_message(embed=embed, ephemeral=True)
            return

        # ✅ mark used
        keys[key]["status"]  = "used"
        keys[key]["used_by"] = str(interaction.user)
        keys[key]["used_id"] = str(interaction.user.id)
        keys[key]["used_at"] = ts()
        save_keys(keys)

        embed = discord.Embed(
            title="✅ Key Redeemed — FemWare",
            description=(
                f"Welcome, **{interaction.user.mention}**!\n\n"
                f"**Product:** {entry.get('product','FemWare — Script')}\n"
                f"**Duration:** {entry.get('duration','Lifetime')}\n\n"
                f"**Your script:**\n> [Download here]({SCRIPT_LINK})\n\n"
                f"⚠️ Do **not** share this link — key is now locked to your account.\n"
                f"Use the **Get Role** button below to receive your @{BUYER_ROLE} role."
            ),
            color=C_OK
        )
        embed.set_footer(text="FemWare • support in #support")
        await interaction.response.send_message(embed=embed, ephemeral=True)

        # log
        log_ch = discord.utils.get(interaction.guild.text_channels, name="key-logs")
        if log_ch:
            log = discord.Embed(
                title="Key redeemed",
                description=f"**User:** {interaction.user} (`{interaction.user.id}`)\n**Key:** ||{key}||\n**Product:** {entry.get('product','FemWare')}",
                color=C_ACCENT, timestamp=datetime.utcnow()
            )
            await log_ch.send(embed=log)


# ── main panel view ──────────────────────────────────────────────────────
class FemWarePanel(ui.View):
    def __init__(self):
        super().__init__(timeout=None)  # persistent

    @ui.button(label="Redeem Key", emoji="🔑", style=discord.ButtonStyle.primary, custom_id="fw_redeem")
    async def redeem(self, interaction: discord.Interaction, button: ui.Button):
        await interaction.response.send_modal(RedeemModal())

    @ui.button(label="Get Key", emoji="🛒", style=discord.ButtonStyle.secondary, custom_id="fw_getkey")
    async def getkey(self, interaction: discord.Interaction, button: ui.Button):
        embed = discord.Embed(
            title="🛒 Get FemWare",
            description=(
                f"Purchase FemWare Script for **$3.00 (Lifetime)**\n\n"
                f"[**→ Go to shop**]({SHOP_LINK})\n\n"
                f"After purchase, your key appears in your profile on the site.\n"
                f"Come back here and press **Redeem Key**."
            ),
            color=C_ACCENT
        )
        embed.set_footer(text="FemWare • Project Delta Script")
        await interaction.response.send_message(embed=embed, ephemeral=True)

    @ui.button(label="Reset HWID", emoji="🔄", style=discord.ButtonStyle.secondary, custom_id="fw_hwid")
    async def reset_hwid(self, interaction: discord.Interaction, button: ui.Button):
        keys   = load_keys()
        uid    = str(interaction.user.id)

        # check if user has a valid redeemed key
        has_key = any(
            v.get("used_id") == uid and v.get("status") == "used"
            for v in keys.values()
        )
        if not has_key:
            embed = discord.Embed(
                title="❌ No active license",
                description="You need a redeemed key to reset HWID.",
                color=C_ERR
            )
            await interaction.response.send_message(embed=embed, ephemeral=True)
            return

        hwids = load_hwids()
        last  = hwids.get(uid, {}).get("last_reset")

        # 1 reset per 7 days
        if last:
            from datetime import timedelta
            last_dt = datetime.strptime(last, "%d/%m/%Y %H:%M UTC")
            if datetime.utcnow() - last_dt < timedelta(days=7):
                remaining = timedelta(days=7) - (datetime.utcnow() - last_dt)
                h, m = divmod(int(remaining.total_seconds()) // 60, 60)
                d    = remaining.days
                embed = discord.Embed(
                    title="⏳ Reset cooldown",
                    description=f"You can reset HWID again in **{d}d {h}h {m}m**.",
                    color=C_ERR
                )
                await interaction.response.send_message(embed=embed, ephemeral=True)
                return

        hwids[uid] = {"last_reset": ts(), "user": str(interaction.user)}
        save_hwids(hwids)

        embed = discord.Embed(
            title="🔄 HWID Reset",
            description=(
                "Your HWID has been reset successfully.\n"
                "Restart the loader and it will register your new hardware.\n\n"
                f"*Next reset available in 7 days.*"
            ),
            color=C_OK
        )
        await interaction.response.send_message(embed=embed, ephemeral=True)

    @ui.button(label="Get Role", emoji="👤", style=discord.ButtonStyle.success, custom_id="fw_role")
    async def get_role(self, interaction: discord.Interaction, button: ui.Button):
        keys = load_keys()
        uid  = str(interaction.user.id)

        has_key = any(
            v.get("used_id") == uid and v.get("status") == "used"
            for v in keys.values()
        )
        if not has_key:
            embed = discord.Embed(
                title="❌ No active license",
                description="Redeem your key first, then press **Get Role**.",
                color=C_ERR
            )
            await interaction.response.send_message(embed=embed, ephemeral=True)
            return

        role = discord.utils.get(interaction.guild.roles, name=BUYER_ROLE)
        if not role:
            await interaction.response.send_message(
                f"❌ Role `{BUYER_ROLE}` not found on this server. Ask an admin to create it.",
                ephemeral=True
            )
            return

        if role in interaction.user.roles:
            embed = discord.Embed(
                title="✅ Already a Buyer",
                description=f"You already have the **@{BUYER_ROLE}** role.",
                color=C_OK
            )
            await interaction.response.send_message(embed=embed, ephemeral=True)
            return

        await interaction.user.add_roles(role, reason="FemWare key redeemed")
        embed = discord.Embed(
            title="✅ Role granted",
            description=f"You've been given the **@{BUYER_ROLE}** role!\nYou now have access to all buyer channels.",
            color=C_OK
        )
        embed.set_footer(text="FemWare • thank you for your purchase")
        await interaction.response.send_message(embed=embed, ephemeral=True)


# ── bot setup ────────────────────────────────────────────────────────────
intents = discord.Intents.default()
intents.members = True
bot = commands.Bot(command_prefix="!", intents=intents)

PANEL_CHANNEL = "get-script"   # channel name — change if different

@bot.event
async def on_ready():
    bot.add_view(FemWarePanel())
    await bot.tree.sync()
    print(f"[FemWare] online as {bot.user}")

    for guild in bot.guilds:
        ch = discord.utils.get(guild.text_channels, name=PANEL_CHANNEL)
        if not ch:
            print(f"[FemWare] #{PANEL_CHANNEL} not found in {guild.name}, skipping")
            continue

        # delete old bot messages in that channel so there's only one panel
        async for msg in ch.history(limit=50):
            if msg.author == bot.user:
                await msg.delete()

        embed = discord.Embed(
            title="FemWare",
            description=(
                "**The best script for Project Delta.**\n"
                "Dominate every match — powerful, stable, undetected.\n\n"
                "🔑 **Redeem Key** — enter your key and receive the script\n"
                "🛒 **Get Key** — visit the shop to purchase ($3 lifetime)\n"
                "🔄 **Reset HWID** — reset your hardware ID (7d cooldown)\n"
                "👤 **Get Role** — claim your @Buyer role after redeeming"
            ),
            color=C_ACCENT
        )
        embed.set_footer(text="FemWare • femware.vercel.app")
        await ch.send(embed=embed, view=FemWarePanel())
        print(f"[FemWare] panel sent to #{PANEL_CHANNEL} in {guild.name}")

# ── /panel ───────────────────────────────────────────────────────────────
@bot.tree.command(name="panel", description="Send the FemWare button panel")
async def panel(interaction: discord.Interaction):
    if interaction.user.id not in ADMIN_IDS:
        await interaction.response.send_message("❌ Admins only.", ephemeral=True)
        return

    embed = discord.Embed(
        title="<:femware:0> FemWare",
        description=(
            "**The best script for Project Delta.**\n"
            "Dominate every match — powerful, stable, undetected.\n\n"
            "🔑 **Redeem Key** — enter your key and receive the script\n"
            "🛒 **Get Key** — visit the shop to purchase ($3 lifetime)\n"
            "🔄 **Reset HWID** — reset your hardware ID (7d cooldown)\n"
            "👤 **Get Role** — claim your @Buyer role after redeeming"
        ),
        color=C_ACCENT
    )
    embed.set_footer(text="FemWare • femware.vercel.app")
    await interaction.response.send_message(embed=embed, view=FemWarePanel())

# ── /addkey (admin) ──────────────────────────────────────────────────────
@bot.tree.command(name="addkey", description="[Admin] Add a key manually")
@app_commands.describe(key="XXXX-XXXX-XXXX-XXXX", duration="Lifetime / 30 days / etc")
async def addkey(interaction: discord.Interaction, key: str, duration: str = "Lifetime"):
    if interaction.user.id not in ADMIN_IDS:
        await interaction.response.send_message("❌ Admins only.", ephemeral=True)
        return
    key = key.strip().upper()
    if not KEY_RE.match(key):
        await interaction.response.send_message("❌ Invalid format.", ephemeral=True)
        return
    keys = load_keys()
    if key in keys:
        await interaction.response.send_message(f"❌ Key `{key}` already exists.", ephemeral=True)
        return
    keys[key] = {"status":"active","product":"FemWare — Script","duration":duration,"created":ts(),"used_by":None,"used_id":None,"used_at":None}
    save_keys(keys)
    await interaction.response.send_message(f"✅ Key `{key}` added ({duration}).", ephemeral=True)

# ── /revokekey (admin) ───────────────────────────────────────────────────
@bot.tree.command(name="revokekey", description="[Admin] Revoke a key")
@app_commands.describe(key="Key to revoke")
async def revokekey(interaction: discord.Interaction, key: str):
    if interaction.user.id not in ADMIN_IDS:
        await interaction.response.send_message("❌ Admins only.", ephemeral=True)
        return
    keys = load_keys()
    key = key.strip().upper()
    if key not in keys:
        await interaction.response.send_message("❌ Key not found.", ephemeral=True)
        return
    keys[key]["status"] = "revoked"
    save_keys(keys)
    await interaction.response.send_message(f"✅ Key `{key}` revoked.", ephemeral=True)
  
bot.run("MTU1ODk4NzAyNjQ1MDA5MjA0Mg.GWXoOq.YZHSBAQ-6nnfqjck8fZ3H8UzSvNvy3q9uoCBLU")
