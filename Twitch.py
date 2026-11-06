# language: Python 3.11, file: bot.py
import discord
from discord.ext import commands
from discord import app_commands
import aiohttp
import asyncio
import os
import threading
import json
import base64
import random
import time
from flask import Flask, request, render_template_string, redirect
from urllib.parse import urlencode
from dotenv import load_dotenv

load_dotenv()

# ==================== AYARLAR ====================
TOKEN = os.getenv("DISCORD_TOKEN")
CLIENT_ID = os.getenv("CLIENT_ID")
CLIENT_SECRET = os.getenv("CLIENT_SECRET")
OWNER_ID = int(os.getenv("OWNER_ID", 0))
REDIRECT_URI = os.getenv("REDIRECT_URI", "https://bestgeneratorravex.onrender.com/callback")
WEB_PORT = int(os.getenv("PORT", 10000))
WEB_PASSWORD = os.getenv("WEB_PASSWORD", "ravex123")

GITHUB_TOKEN = os.getenv("GITHUB_TOKEN")
GITHUB_REPO = os.getenv("GITHUB_REPO")

STOK_FILES = {
    "normal": "stok.json",
    "premium": "Premiumstok.json",
    "exclusive": "Exclusivestok.json"
}
TWITCH_FILE = "twitch_tokens.json"
AUTH_FILE = "auth_tokens.json"

STAFF_ROLES = [1566432003560181891, 1560996761659515003]
EXCLUSIVE_ROLE = 1560688907199184986
PREMIUM_ROLE = 1560316365951475852
JOIN_ROLE = 1560292397982810173
TICKET_LOG_CHANNEL = 1566423675480186951
VOUCH_CHANNEL = 1566423691301093437
PREMIUM_EXCLUSIVE_CHANNEL = 1566423682371420273
# =================================================

github_lock = asyncio.Lock()

# ==================== GITHUB VERİTABANI ====================
async def github_get_headers():
    return {"Authorization": f"token {GITHUB_TOKEN}", "Accept": "application/vnd.github.v3+json"}

async def read_github_file(filename):
    url = f"https://api.github.com/repos/{GITHUB_REPO}/contents/{filename}"
    async with aiohttp.ClientSession() as session:
        async with session.get(url, headers=await github_get_headers()) as resp:
            if resp.status == 200:
                data = await resp.json()
                content = base64.b64decode(data['content']).decode('utf-8')
                return json.loads(content), data['sha']
            if "twitch" in filename or "auth" in filename: return [], None
            return {"steam": [], "netflix": [], "used": []}, None

async def write_github_file(filename, data, sha):
    url = f"https://api.github.com/repos/{GITHUB_REPO}/contents/{filename}"
    content = base64.b64encode(json.dumps(data, indent=2).encode('utf-8')).decode('utf-8')
    payload = {"message": "Bot Guncellemesi", "content": content}
    if sha: payload["sha"] = sha
    async with aiohttp.ClientSession() as session:
        async with session.put(url, headers=await github_get_headers(), json=payload) as resp:
            return resp.status in [200, 201]
# =========================================================

# ==================== TWITCH FOLLOWER SINIFI ====================
class TwitchFollower:
    def __init__(self):
        self.proxies = self._load_proxies()
        self.proxy_index = 0

    def _load_proxies(self):
        proxies = []
        if os.path.exists("proxies.txt"):
            with open("proxies.txt", "r") as f:
                for line in f:
                    line = line.strip()
                    if line and not line.isspace():
                        if '://' not in line: line = f"http://{line}"
                        proxies.append(line)
        return proxies

    async def get_user_id(self, user):
        headers = {"Client-Id": "kimne78kx3ncx6brgo4mv6wki5h1ko", "Content-Type": "application/json"}
        payload = json.dumps([{"operationName": "GetIDFromLogin", "variables": {"login": user}, "extensions": {"persistedQuery": {"version": 1, "sha256Hash": "94e82a7b1e3c21e186daa73ee2afc4b8f23bade1fbbff6fe8ac133f50a2f58ca"}}}])
        try:
            async with aiohttp.ClientSession() as session:
                async with session.post("https://gql.twitch.tv/gql", headers=headers, data=payload) as response:
                    if response.status == 200:
                        data = await response.json()
                        if data and isinstance(data, list) and data[0].get("data") and data[0]["data"].get("user"):
                            return data[0]["data"]["user"]["id"]
        except: pass
        return False

    async def execute_follow(self, target_id, token):
        headers = {"Accept": "application/json", "Authorization": f"OAuth {token}", "Content-Type": "application/json"}
        payload = json.dumps([{"operationName": "FollowUserMutation", "variables": {"targetId": str(target_id), "disableNotifications": False}, "extensions": {"persistedQuery": {"version": 1, "sha256Hash": "cd112d9483ede85fa0da514a5657141c24396efbc7bac0ea3623e839206573b8"}}}])
        
        max_retries = len(self.proxies) if self.proxies else 1
        for _ in range(max_retries):
            proxy_url = None
            if self.proxies:
                proxy_url = self.proxies[self.proxy_index % len(self.proxies)]
                self.proxy_index += 1
            
            try:
                async with aiohttp.ClientSession() as session:
                    async with session.post("https://gql.twitch.tv/gql", data=payload, headers=headers, proxy=proxy_url) as response:
                        if response.status in (200, 204):
                            if "errors" not in (await response.text()).lower(): return True
                        if proxy_url in self.proxies: self.proxies.remove(proxy_url)
            except: 
                if proxy_url in self.proxies: self.proxies.remove(proxy_url)
            await asyncio.sleep(0.5)
        return False
# =========================================================

# ==================== WEB PANELİ ====================
web_app = Flask(__name__)

HTML_INDEX = """<!DOCTYPE html><html><head><meta charset="UTF-8"><title>Ravex Panel</title><style>body{background:#121212;color:#fff;font-family:sans-serif;padding:20px;text-align:center;}.box{max-width:500px;margin:auto;background:#1e1e1e;padding:20px;border-radius:10px;margin-bottom:20px;}input,select,textarea{width:100%;padding:10px;margin:5px 0;background:#2b2b2b;color:white;border:1px solid #333;box-sizing:border-box;}button{width:100%;padding:10px;background:#7289da;color:white;border:none;margin-top:10px;cursor:pointer;}button:hover{background:#5b6eae;}.auth-btn{background:#3ba55d;display:block;text-decoration:none;color:white;padding:10px;border-radius:5px;margin-top:10px;}</style></head><body>
<div class="box"><h2>📦 Stok Ekle</h2><form method="POST" action="/add_stock"><input type="password" name="password" placeholder="Panel Şifresi" required><select name="plan"><option value="normal">Normal</option><option value="premium">Premium</option><option value="exclusive">Exclusive</option></select><select name="service"><option value="steam">Steam</option><option value="netflix">Netflix</option></select><textarea name="accounts" rows="5" required placeholder="Her satıra bir hesap..."></textarea><button type="submit">Stok Ekle</button></form>{% if msg %}<p style="color:lightgreen;">{{ msg }}</p>{% endif %}</div>
<div class="box"><h2>🔗 Sunucuya Adam Çek</h2><a href="/login" class="auth-btn">Authorize (Giriş Yap)</a></div>
<div class="box"><h2>🎮 Twitch Token Ekle</h2><form method="POST" action="/add_twitch"><input type="password" name="password" placeholder="Panel Şifresi" required><textarea name="tokens" rows="5" required placeholder="Her satıra bir token..."></textarea><button type="submit">Token Ekle</button></form></div>
</body></html>"""

@web_app.route('/')
def index():
    return render_template_string(HTML_INDEX, msg=request.args.get('msg'))

@web_app.route('/add_stock', methods=['POST'])
def add_stock():
    if request.form.get('password') != WEB_PASSWORD: return redirect('/?msg=Hatali+Sifre')
    plan, service, accounts_raw = request.form.get('plan'), request.form.get('service'), request.form.get('accounts')
    if not accounts_raw.strip(): return redirect('/?msg=Bos+veri')
    lines = [line.strip() for line in accounts_raw.split("\n") if line.strip()]
    def run_async(coro):
        loop = asyncio.new_event_loop(); asyncio.set_event_loop(loop)
        return loop.run_until_complete(coro)
    async def save():
        async with github_lock:
            stock, sha = await read_github_file(STOK_FILES[plan])
            if service == "steam": stock["steam"].extend(lines)
            else: stock["netflix"].extend(lines)
            return await write_github_file(STOK_FILES[plan], stock, sha)
    if run_async(save()): return redirect('/?msg=Stok+Eklendi')
    return redirect('/?msg=Hata')

@web_app.route('/add_twitch', methods=['POST'])
def add_twitch():
    if request.form.get('password') != WEB_PASSWORD: return redirect('/?msg=Hatali+Sifre')
    tokens_raw = request.form.get('tokens')
    new_tokens = [t.strip() for t in tokens_raw.split("\n") if t.strip()]
    def run_async(coro):
        loop = asyncio.new_event_loop(); asyncio.set_event_loop(loop)
        return loop.run_until_complete(coro)
    async def save():
        async with github_lock:
            tokens, sha = await read_github_file(TWITCH_FILE)
            tokens.extend(new_tokens)
            return await write_github_file(TWITCH_FILE, tokens, sha)
    if run_async(save()): return redirect('/?msg=Twitch+Eklendi')
    return redirect('/?msg=Hata')

@web_app.route('/login')
def login():
    params = {"client_id": CLIENT_ID, "redirect_uri": REDIRECT_URI, "response_type": "code", "scope": "identify guilds.join"}
    return redirect(f"https://discord.com/api/oauth2/authorize?{urlencode(params)}")

@web_app.route('/callback')
def callback():
    code = request.args.get('code')
    if not code: return "Hata"
    data = {"client_id": CLIENT_ID, "client_secret": CLIENT_SECRET, "grant_type": "authorization_code", "code": code, "redirect_uri": REDIRECT_URI}
    headers = {"Content-Type": "application/x-www-form-urlencoded"}
    def run_async(coro):
        loop = asyncio.new_event_loop(); asyncio.set_event_loop(loop)
        return loop.run_until_complete(coro)
    async def get_token():
        async with aiohttp.ClientSession() as session:
            async with session.post("https://discord.com/api/oauth2/token", data=data, headers=headers) as resp:
                if resp.status == 200:
                    access_token = (await resp.json()).get("access_token")
                    async with github_lock:
                        tokens, sha = await read_github_file(AUTH_FILE)
                        tokens.append(access_token)
                        await write_github_file(AUTH_FILE, tokens, sha)
                    return True
        return False
    if run_async(get_token()): return "<h1 style='color:lightgreen;text-align:center;'>✅ Başarıyla Yetkilendirildi!</h1>"
    return "<h1 style='color:red;text-align:center;'>❌ Hata!</h1>"

def run_web():
    web_app.run(host='0.0.0.0', port=WEB_PORT)
# =========================================================

# ==================== TICKET VE MENÜLER ====================
class TicketSelectMenu(discord.ui.Select):
    def __init__(self):
        options = [discord.SelectOption(label="Support", emoji="🎧", value="Support"), discord.SelectOption(label="General", emoji="💬", value="General")]
        super().__init__(placeholder="Select a category...", min_values=1, max_values=1, options=options)
    async def callback(self, interaction: discord.Interaction):
        await interaction.response.defer(ephemeral=True)
        await create_ticket(interaction, self.values[0])

class TicketMenuView(discord.ui.View):
    def __init__(self):
        super().__init__(timeout=None)
        self.add_item(TicketSelectMenu())

class TicketControlView(discord.ui.View):
    def __init__(self):
        super().__init__(timeout=None)
    @discord.ui.button(label="Claim", emoji="🙋‍♂️", style=discord.ButtonStyle.success, custom_id="t_claim")
    async def claim_btn(self, interaction: discord.Interaction, button: discord.ui.Button):
        if not any(r.id in STAFF_ROLES for r in interaction.user.roles): return await interaction.response.send_message("❌ Staff only.", ephemeral=True)
        button.disabled = True; button.label = f"Claimed by {interaction.user.name}"
        await interaction.message.edit(view=self); await interaction.response.send_message(f"✅ {interaction.user.mention} claimed.", ephemeral=False)
    @discord.ui.button(label="Close", emoji="🔒", style=discord.ButtonStyle.danger, custom_id="t_close")
    async def close_btn(self, interaction: discord.Interaction, button: discord.ui.Button):
        if not any(r.id in STAFF_ROLES for r in interaction.user.roles): return await interaction.response.send_message("❌ Staff only.", ephemeral=True)
        await interaction.response.send_message("🔒 Closing in 5s..."); await asyncio.sleep(5); await interaction.channel.delete()

# ==================== BOT CLASS ====================
class MyBot(commands.Bot):
    def __init__(self):
        intents = discord.Intents.default()
        intents.message_content = True
        intents.members = True
        super().__init__(command_prefix=".", intents=intents)
        self.cooldowns = {}

    async def setup_hook(self):
        await self.tree.sync()
        self.add_view(TicketMenuView())
        self.add_view(TicketControlView())

    async def on_ready(self):
        print(f"[+] Bot aktif: {self.user.name}")
        if not any(t.name == "WebServerThread" for t in threading.enumerate()):
            threading.Thread(target=run_web, daemon=True, name="WebServerThread").start()

    async def on_member_join(self, member):
        role = member.guild.get_role(JOIN_ROLE)
        if role:
            try: await member.add_roles(role)
            except: pass

bot = MyBot()

# ==================== YARDIMCI FONKSİYONLAR ====================
def check_limit(user_id, type_):
    if user_id not in bot.cooldowns: bot.cooldowns[user_id] = {}
    if type_ in bot.cooldowns[user_id]:
        if time.time() - bot.cooldowns[user_id][type_] < 86400: return False, int(86400 - (time.time() - bot.cooldowns[user_id][type_]))
    return True, 0

def set_limit(user_id, type_):
    if user_id not in bot.cooldowns: bot.cooldowns[user_id] = {}
    bot.cooldowns[user_id][type_] = time.time()

async def create_ticket(interaction: discord.Interaction, category: str):
    guild = interaction.guild
    overwrites = {guild.default_role: discord.PermissionOverwrite(read_messages=False), interaction.user: discord.PermissionOverwrite(read_messages=True)}
    t_num = len([c for c in guild.channels if c.name.startswith("ticket-")]) + 1
    try:
        channel = await guild.create_text_channel(name=f"ticket-{t_num}", overwrites=overwrites)
        embed = discord.Embed(title=f"Ticket #{t_num}", description=f"Category: **{category}**\nOpened by: {interaction.user.mention}")
        await channel.send(embed=embed, view=TicketControlView())
        await interaction.followup.send(f"✅ Created: {channel.mention}", ephemeral=True)
    except Exception as e: await interaction.followup.send(f"❌ Error: {e}", ephemeral=True)

# ==================== SLASH KOMUTLARI ====================
@bot.tree.command(name="ticket", description="Open a ticket")
async def ticket_cmd(interaction: discord.Interaction):
    await interaction.response.send_message(embed=discord.Embed(title="🎟️ Support", description="Select category."), view=TicketMenuView())

@bot.tree.command(name="join", description="Sunucuya adam çeker")
async def join_cmd(interaction: discord.Interaction, sunucu_linki: str, adet: int = 10):
    if interaction.user.id != OWNER_ID: return await interaction.response.send_message("⛔ Owner only.", ephemeral=True)
    await interaction.response.defer()
    invite_code = sunucu_linki.split("/")[-1]
    tokens_data = await read_github_file(AUTH_FILE)
    current_tokens = [t.strip() for t in tokens_data[0] if t.strip()]
    if not current_tokens: return await interaction.followup.send("❌ Yetkili hesap yok! Siteye gidip Authorize yapın.")

    selected_tokens = random.sample(current_tokens, min(adet, len(current_tokens)))
    msg = await interaction.followup.send(f"⏳ **{sunucu_linki}** için {len(selected_tokens)} hesap sokuluyor...")
    success, fail = 0, 0
    for token in selected_tokens:
        headers = {"Authorization": f"Bot {TOKEN}", "Content-Type": "application/json"}
        try:
            async with aiohttp.ClientSession() as session:
                async with session.get(f"https://discord.com/api/v10/invites/{invite_code}?with_counts=true", headers=headers) as resp:
                    if resp.status == 200:
                        guild_id = (await resp.json())["guild"]["id"]
                        user_headers = {"Authorization": f"Bearer {token}"}
                        async with session.get("https://discord.com/api/v10/users/@me", headers=user_headers) as u_resp:
                            if u_resp.status == 200:
                                user_id = (await u_resp.json())["id"]
                                async with session.put(f"https://discord.com/api/v10/guilds/{guild_id}/members/{user_id}", headers=headers, json={"access_token": token}) as j_resp:
                                    if j_resp.status in [200, 201, 204]: success += 1
                                    else: fail += 1
                            else: fail += 1
                    else: fail += 1
        except: fail += 1
        await asyncio.sleep(1.5)
    await msg.edit(content=f"✅ Bitti!\nHedef: **{sunucu_linki}**\n\n✔️ Başarılı: **{success}**\n❌ Başarısız: **{fail}**")

@bot.tree.command(name="generate", description="Hesap üretir")
@app_commands.choices(
    service=[app_commands.Choice(name="Netflix", value="netflix"), app_commands.Choice(name="Steam", value="steam")],
    plan=[app_commands.Choice(name="Normal", value="normal"), app_commands.Choice(name="Premium", value="premium"), app_commands.Choice(name="Exclusive", value="exclusive")]
)
async def generate_cmd(interaction: discord.Interaction, service: app_commands.Choice[str], plan: app_commands.Choice[str]):
    user_roles, svc, pln = [r.id for r in interaction.user.roles], service.value, plan.value
    if pln in ["premium", "exclusive"] and interaction.channel_id != PREMIUM_EXCLUSIVE_CHANNEL:
        return await interaction.response.send_message(f"❌ Use in <#{PREMIUM_EXCLUSIVE_CHANNEL}>.", ephemeral=True)
    if pln == "premium" and PREMIUM_ROLE not in user_roles: return await interaction.response.send_message("❌ No Premium role.", ephemeral=True)
    if pln == "exclusive" and EXCLUSIVE_ROLE not in user_roles: return await interaction.response.send_message("❌ No Exclusive role.", ephemeral=True)
    
    await interaction.response.defer() 
    limit_ok, t_left = check_limit(interaction.user.id, f"{svc}_{pln}")
    if not limit_ok: return await interaction.followup.send(f"❌ Limit reached. Wait {t_left//3600}h.", ephemeral=True)
    
    async with github_lock:
        stock, sha = await read_github_file(STOK_FILES[pln])
        acc = None
        if svc == "steam":
            lines = stock.get("steam", [])
            for i in range(0, len(lines), 2):
                if i+1 < len(lines):
                    a = f"{lines[i]}\n{lines[i+1]}"
                    if a not in stock.get("used", []): acc = a; stock["used"].append(a); break
        else:
            for line in stock.get("netflix", []):
                if line not in stock.get("used", []): acc = line; stock["used"].append(line); break
        if acc: await write_github_file(STOK_FILES[pln], stock, sha)
        
    if not acc: return await interaction.followup.send(f"❌ {pln.capitalize()} out of stock for {svc}!", ephemeral=True)
    set_limit(interaction.user.id, f"{svc}_{pln}")
    
    try:
        if svc == "steam":
            await interaction.user.send(f"🎁 **Steam ({pln.capitalize()})**\n\n```\n{acc}\n```")
            await interaction.followup.send(f"Generated, Check DMs!")
        else:
            await interaction.followup.send(f"✅ Generated, Check DMs!")
            owner = await bot.fetch_user(OWNER_ID)
            if owner:
                embed = discord.Embed(title=f"🎬 Netflix Request", color=discord.Color.red())
                embed.add_field(name="User", value=f"{interaction.user.mention}"); embed.add_field(name="Acc", value=f"```{acc}```")
                await owner.send(embed=embed)
    except discord.Forbidden: await interaction.followup.send("❌ DMs closed.", ephemeral=True)

@bot.tree.command(name="tfollow", description="Twitch takipçi gönder")
async def tfollow_cmd(interaction: discord.Interaction, twitch_ismi: str, adet: int = 10):
    if interaction.user.id != OWNER_ID: return await interaction.response.send_message("⛔ Owner only.", ephemeral=True)
    await interaction.response.defer()
    
    tokens_data = await read_github_file(TWITCH_FILE)
    current_tokens = [t.strip() for t in tokens_data[0] if t.strip()]
    if not current_tokens: return await interaction.followup.send("❌ Token yok!")

    follower = TwitchFollower()
    target_id = await follower.get_user_id(twitch_ismi)
    if not target_id: return await interaction.followup.send(f"❌ Kanal bulunamadı.")

    msg = await interaction.followup.send(f"⏳ **{twitch_ismi}** için işlem başlatıldı...")
    selected_tokens = random.sample(current_tokens, min(adet, len(current_tokens)))
    success, fail = 0, 0
    for token in selected_tokens:
        if await follower.execute_follow(target_id, token): success += 1
        else: fail += 1
        await asyncio.sleep(1.0)
    await msg.edit(content=f"✅ Bitti!\n🎯 Hedef: **{twitch_ismi}**\n✔️ Başarılı: **{success}**\n❌ Başarısız: **{fail}**")

@bot.tree.command(name="delete", description="Delete messages")
async def delete_cmd(interaction: discord.Interaction, amount: int, empty_only: bool = True):
    if not any(r.id in STAFF_ROLES for r in interaction.user.roles) and interaction.user.id != OWNER_ID: return await interaction.response.send_message("❌ Staff only.", ephemeral=True)
    await interaction.response.defer(ephemeral=True)
    try:
        if empty_only:
            cnt = 0
            async for msg in interaction.channel.history(limit=amount):
                if not msg.content.strip() or not msg.content.isprintable():
                    try: await msg.delete(); cnt += 1
                    except: pass
            await interaction.followup.send(f"✅ Silindi: {cnt} boş mesaj.", ephemeral=True)
        else: await interaction.channel.purge(limit=amount); await interaction.followup.send(f"✅ Silindi: {amount} mesaj.", ephemeral=True)
    except Exception as e: await interaction.followup.send(f"❌ Hata: {e}", ephemeral=True)

@bot.tree.command(name="giveaway", description="Start giveaway")
async def giveaway_cmd(interaction: discord.Interaction, channel: discord.TextChannel, prize: str, duration: str, winners: int):
    if not any(r.id in STAFF_ROLES for r in interaction.user.roles) and interaction.user.id != OWNER_ID: return await interaction.response.send_message("❌ Staff only.", ephemeral=True)
    await interaction.response.defer(ephemeral=True)
    try:
        sec = int(duration[:-1]) * (60 if duration.endswith("m") else 3600 if duration.endswith("h") else 86400 if duration.endswith("d") else 1)
        view = discord.ui.View(timeout=sec)
        embed = discord.Embed(title="🎉 GIVEAWAY 🎉", description=f"**Prize:** {prize}\n**Winners:** {winners}\n**Ends:** <t:{int(time.time()+sec)}:R>")
        embed.add_field(name="Entries", value="👥 **0**")
        entries = set()
        
        @discord.ui.button(label="Join", emoji="🎉", style=discord.ButtonStyle.success)
        async def join(inter, btn):
            if inter.user.id in entries: return await inter.response.send_message("❌ Zaten katıldın!", ephemeral=True)
            entries.add(inter.user.id); embed.set_field_at(0, name="Entries", value=f"👥 **{len(entries)}**")
            await msg.edit(embed=embed); await inter.response.send_message("✅ Katıldın!", ephemeral=True)
        
        @discord.ui.button(label="Leave", emoji="🚪", style=discord.ButtonStyle.danger)
        async def leave(inter, btn):
            if inter.user.id not in entries: return await inter.response.send_message("❌ Katılmadın!", ephemeral=True)
            entries.remove(inter.user.id); embed.set_field_at(0, name="Entries", value=f"👥 **{len(entries)}**")
            await msg.edit(embed=embed); await inter.response.send_message("✅ Ayrıldın.", ephemeral=True)
            
        view.add_item(join); view.add_item(leave)
        msg = await channel.send(embed=embed, view=view)
        await interaction.followup.send(f"✅ Başladı: {channel.mention}", ephemeral=True)
        await asyncio.sleep(sec)
        if not entries: await channel.send(f"❌ Katılımcı yok: {prize}")
        else:
            wins = random.sample(list(entries), min(winners, len(entries)))
            await channel.send(f"🎉 **Bitti!**\nÖdül: **{prize}**\nKazananlar: {', '.join([f'<@{w}>' for w in wins])}")
    except Exception as e: await interaction.followup.send(f"❌ Hata: {e}", ephemeral=True)

@bot.tree.command(name="unlocklimit", description="Reset limit")
async def unlocklimit_cmd(interaction: discord.Interaction, user: discord.Member):
    if not any(r.id in STAFF_ROLES for r in interaction.user.roles) and interaction.user.id != OWNER_ID: return await interaction.response.send_message("❌ Staff only.", ephemeral=True)
    await interaction.response.defer(ephemeral=True)
    if user.id in bot.cooldowns: bot.cooldowns[user.id].clear()
    await interaction.followup.send(f"✅ Sıfırlandı: {user.mention}", ephemeral=True)

@bot.tree.command(name="premium", description="Give Premium")
async def premium_cmd(interaction: discord.Interaction, user: discord.Member):
    if not any(r.id in STAFF_ROLES for r in interaction.user.roles) and interaction.user.id != OWNER_ID: return await interaction.response.send_message("❌ Staff only.", ephemeral=True)
    await interaction.response.defer(ephemeral=True)
    role = interaction.guild.get_role(PREMIUM_ROLE)
    if role:
        try: await user.add_roles(role); await interaction.followup.send("✅ Verildi.")
        except: await interaction.followup.send("❌ Rol Hatası.")

@bot.tree.command(name="exclusive", description="Give Exclusive")
async def exclusive_cmd(interaction: discord.Interaction, user: discord.Member):
    if not any(r.id in STAFF_ROLES for r in interaction.user.roles) and interaction.user.id != OWNER_ID: return await interaction.response.send_message("❌ Staff only.", ephemeral=True)
    await interaction.response.defer(ephemeral=True)
    role = interaction.guild.get_role(EXCLUSIVE_ROLE)
    if role:
        try: await user.add_roles(role); await interaction.followup.send("✅ Verildi.")
        except: await interaction.followup.send("❌ Rol Hatası.")

@bot.tree.command(name="ban", description="Ban member")
async def ban_cmd(interaction: discord.Interaction, member: discord.Member, reason: str = "None"):
    if not any(r.id in STAFF_ROLES for r in interaction.user.roles) and interaction.user.id != OWNER_ID: return await interaction.response.send_message("❌ Staff only.", ephemeral=True)
    await interaction.response.defer(ephemeral=True); await member.ban(reason=reason); await interaction.followup.send(f"🔨 Banlandı: {member.mention}", ephemeral=True)

@bot.tree.command(name="kick", description="Kick member")
async def kick_cmd(interaction: discord.Interaction, member: discord.Member, reason: str = "None"):
    if not any(r.id in STAFF_ROLES for r in interaction.user.roles) and interaction.user.id != OWNER_ID: return await interaction.response.send_message("❌ Staff only.", ephemeral=True)
    await interaction.response.defer(ephemeral=True); await member.kick(reason=reason); await interaction.followup.send(f"👢 Atıldı: {member.mention}", ephemeral=True)

@bot.tree.command(name="mute", description="Mute member")
async def mute_cmd(interaction: discord.Interaction, member: discord.Member, duration: int):
    if not any(r.id in STAFF_ROLES for r in interaction.user.roles) and interaction.user.id != OWNER_ID: return await interaction.response.send_message("❌ Staff only.", ephemeral=True)
    await interaction.response.defer(ephemeral=True); await member.timeout(discord.utils.utcnow() + discord.timedelta(minutes=duration)); await interaction.followup.send(f"🔇 Susturuldu: {member.mention}", ephemeral=True)

@bot.tree.command(name="unblacklist", description="Remove BL")
async def unblacklist_cmd(interaction: discord.Interaction, user: discord.Member, duration: str):
    if interaction.user
