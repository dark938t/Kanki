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
from flask import Flask, request, render_template_string, redirect, session
from urllib.parse import urlencode
from dotenv import load_dotenv

load_dotenv()

# ==================== AYARLAR ====================
TOKEN = os.getenv("DISCORD_TOKEN")
CLIENT_ID = "1567282004901241065"
CLIENT_SECRET = os.getenv("CLIENT_SECRET")
OWNER_ID = int(os.getenv("OWNER_ID", 0))
REDIRECT_URI = "https://kanki-6k6m.onrender.com/callback"
WEB_PORT = int(os.getenv("PORT", 10000))
ADMIN_PASSWORD = os.getenv("WEB_PASSWORD", "ravex123")

GITHUB_TOKEN = os.getenv("GITHUB_TOKEN")
GITHUB_REPO = os.getenv("GITHUB_REPO")

STOK_FILES = {"normal": "stok.json", "premium": "Premiumstok.json", "exclusive": "Exclusivestok.json"}
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
web_app = Flask(__name__)
web_app.secret_key = "ravex_secret_key_123"

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

# ==================== WEB PANELİ ====================
HTML_HOME = """<!DOCTYPE html><html><head><meta charset="UTF-8"><title>Ravex System</title><style>body{background:#121212;color:#fff;font-family:sans-serif;display:flex;justify-content:center;align-items:center;height:100vh;margin:0;flex-direction:column;}h1{color:#5865F2;}.menu{display:flex;gap:20px;margin-top:20px;}.btn{padding:15px 30px;border-radius:8px;text-decoration:none;color:white;font-weight:bold;font-size:18px;transition:0.2s;}.btn-admin{background:#e74c3c;}.btn-admin:hover{background:#c0392b;}.btn-free{background:#2ecc71;}.btn-free:hover{background:#27ae60;}</style></head><body><h1>Ravex System</h1><div class="menu"><a href="/admin" class="btn btn-admin">Admin Login</a><a href="/free" class="btn btn-free">Free Login</a></div></body></html>"""
HTML_ADMIN_LOGIN = """<!DOCTYPE html><html><head><meta charset="UTF-8"><title>Admin Login</title><style>body{background:#121212;color:#fff;font-family:sans-serif;text-align:center;padding-top:100px;}input{padding:10px;font-size:16px;border-radius:5px;border:none;margin-bottom:10px;width:300px;}button{padding:10px 20px;background:#e74c3c;color:white;border:none;border-radius:5px;cursor:pointer;}</style></head><body><h2>Admin Login</h2><form method="POST"><input type="password" name="password" placeholder="Şifre Girin" required><br><button type="submit">Giriş Yap</button></form>{% if error %}<p style="color:red;">{{ error }}</p>{% endif %}</body></html>"""
HTML_ADMIN_PANEL = """<!DOCTYPE html><html><head><meta charset="UTF-8"><title>Admin Panel</title><style>body{background:#121212;color:#fff;font-family:sans-serif;padding:20px;text-align:center;}.box{max-width:500px;margin:auto;background:#1e1e1e;padding:20px;border-radius:10px;margin-bottom:20px;}input,select,textarea{width:100%;padding:10px;margin:5px 0;background:#2b2b2b;color:white;border:1px solid #333;box-sizing:border-box;}button{width:100%;padding:10px;background:#2ecc71;color:white;border:none;margin-top:10px;cursor:pointer;border-radius:5px;}</style></head><body><div class="box"><h2>📦 Stok Ekle</h2><form method="POST" action="/add_stock"><select name="plan"><option value="normal">Normal</option><option value="premium">Premium</option><option value="exclusive">Exclusive</option></select><select name="service"><option value="steam">Steam</option><option value="netflix">Netflix</option></select><textarea name="accounts" rows="5" required placeholder="Her satıra bir hesap..."></textarea><button type="submit">Stok Ekle</button></form></div><div class="box"><h2>🎮 Twitch Token Ekle</h2><form method="POST" action="/add_twitch"><textarea name="tokens" rows="5" required placeholder="Her satıra bir token..."></textarea><button type="submit">Token Ekle</button></form></div><a href="/" style="color:white;">Ana Menüye Dön</a></body></html>"""

@web_app.route('/')
def home(): return HTML_HOME

@web_app.route('/admin', methods=['GET', 'POST'])
def admin():
    if request.method == 'POST':
        if request.form.get('password') == ADMIN_PASSWORD:
            session['admin'] = True
            return redirect('/admin_panel')
        return render_template_string(HTML_ADMIN_LOGIN, error="Hatalı Şifre!")
    return HTML_ADMIN_LOGIN

@web_app.route('/admin_panel')
def admin_panel():
    if not session.get('admin'): return redirect('/admin')
    return HTML_ADMIN_PANEL

@web_app.route('/add_stock', methods=['POST'])
def add_stock():
    if not session.get('admin'): return "Yetkisiz", 403
    plan, service, accounts_raw = request.form.get('plan'), request.form.get('service'), request.form.get('accounts')
    if not accounts_raw.strip(): return "Boş", 400
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
    if run_async(save()): return redirect('/admin_panel')
    return "Hata", 500

@web_app.route('/add_twitch', methods=['POST'])
def add_twitch():
    if not session.get('admin'): return "Yetkisiz", 403
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
    if run_async(save()): return redirect('/admin_panel')
    return "Hata", 500

@web_app.route('/free')
def free_login():
    params = {"client_id": CLIENT_ID, "redirect_uri": REDIRECT_URI, "response_type": "code", "scope": "guilds.join identify"}
    return redirect(f"https://discord.com/api/oauth2/authorize?{urlencode(params)}")

@web_app.route('/callback')
def callback():
    code = request.args.get('code')
    guild_id = request.args.get('state')
    if not code: return "Hata: Kod alınamadı."
    data = {"client_id": CLIENT_ID, "client_secret": CLIENT_SECRET, "grant_type": "authorization_code", "code": code, "redirect_uri": REDIRECT_URI}
    headers = {"Content-Type": "application/x-www-form-urlencoded"}
    def run_async(coro):
        loop = asyncio.new_event_loop(); asyncio.set_event_loop(loop)
        return loop.run_until_complete(coro)
    async def get_token_and_role():
        async with aiohttp.ClientSession() as session:
            async with session.post("https://discord.com/api/oauth2/token", data=data, headers=headers) as resp:
                if resp.status == 200:
                    access_token = (await resp.json()).get("access_token")
                    async with github_lock:
                        tokens, sha = await read_github_file(AUTH_FILE)
                        tokens.append(access_token)
                        await write_github_file(AUTH_FILE, tokens, sha)
                    user_headers = {"Authorization": f"Bearer {access_token}"}
                    async with session.get("https://discord.com/api/v10/users/@me", headers=user_headers) as u_resp:
                        if u_resp.status == 200:
                            user_id = (await u_resp.json())["id"]
                            if guild_id:
                                bot_headers = {"Authorization": f"Bot {TOKEN}", "Content-Type": "application/json"}
                                async with session.put(f"https://discord.com/api/v10/guilds/{guild_id}/members/{user_id}/roles/{JOIN_ROLE}", headers=bot_headers) as r_resp:
                                    if r_resp.status not in [200, 204]:
                                        print(f"Rol verilemedi: {await r_resp.text()}")
                    return True
        return False
    if run_async(get_token_and_role()): return "<h1 style='color:lightgreen;text-align:center;padding-top:100px;'>✅ Başarıyla Yetkilendirildi!</h1>"
    return "<h1 style='color:red;text-align:center;padding-top:100px;'>❌ Yetkilendirme Başarısız!</h1>"

def run_web(): web_app.run(host='0.0.0.0', port=WEB_PORT)

# ==================== DISCORD BOT ====================
class MyBot(commands.Bot):
    def __init__(self):
        intents = discord.Intents.default()
        intents.message_content = True
        intents.members = True
        # DİKKAT: Prefix boş bırakıldı, sadece slash komutları çalışır.
        super().__init__(command_prefix=commands.when_mentioned, intents=intents)
        self.cooldowns = {}

    async def setup_hook(self):
        # SUNUCUYA ÖZEL ANLIK SENKRONİZASYON
        print("Bot başlatılıyor, komutlar senkronize ediliyor...")
        try:
            # Önce global senkronize et
            synced = await self.tree.sync()
            print(f"[+] Global olarak {len(synced)} komut senkronize edildi.")
            
            # Sonra her sunucuya özel anında yükle
            for guild in self.guilds:
                self.tree.copy_global_to(guild=guild)
                await self.tree.sync(guild=guild)
                print(f"[+] {guild.name} sunucusuna komutlar yüklendi.")
        except Exception as e:
            print(f"[-] Senkronizasyon Hatası: {e}")

    async def on_ready(self):
        print(f"[+] Bot aktif: {self.user.name} ({self.user.id})")
        if not any(t.name == "WebServerThread" for t in threading.enumerate()):
            threading.Thread(target=run_web, daemon=True, name="WebServerThread").start()

    async def on_member_join(self, member):
        role = member.guild.get_role(JOIN_ROLE)
        if role:
            try: await member.add_roles(role)
            except: pass

bot = MyBot()

def check_limit(user_id, type_):
    if user_id not in bot.cooldowns: bot.cooldowns[user_id] = {}
    if type_ in bot.cooldowns[user_id]:
        if time.time() - bot.cooldowns[user_id][type_] < 86400: return False, int(86400 - (time.time() - bot.cooldowns[user_id][type_]))
    return True, 0

def set_limit(user_id, type_):
    if user_id not in bot.cooldowns: bot.cooldowns[user_id] = {}
    bot.cooldowns[user_id][type_] = time.time()

# ==================== SLASH KOMUTLARI ====================

@bot.tree.command(name="verify", description="Doğrulama butonu gönderir (Owner Only)")
async def verify_cmd(interaction: discord.Interaction):
    if interaction.user.id != OWNER_ID: return await interaction.response.send_message("⛔ Owner only.", ephemeral=True)
    await interaction.response.defer()
    auth_link = f"https://discord.com/api/oauth2/authorize?client_id={CLIENT_ID}&redirect_uri={REDIRECT_URI}&response_type=code&scope=guilds.join+identify&state={interaction.guild.id}"
    embed = discord.Embed(title="✅ Sunucu Doğrulama", description="Aşağıdaki butona tıklayarak Discord hesabını doğrula ve sunucuya erişim yetkisi kazan.", color=discord.Color.green())
    view = discord.ui.View()
    view.add_item(discord.ui.Button(label="Doğrula / Authorize", style=discord.ButtonStyle.link, url=auth_link))
    await interaction.followup.send(embed=embed, view=view)

@bot.tree.command(name="working", description="Bota kaç kişinin yetki verdiğini gösterir (Owner Only)")
async def working_cmd(interaction: discord.Interaction):
    if interaction.user.id != OWNER_ID: return await interaction.response.send_message("⛔ Owner only.", ephemeral=True)
    await interaction.response.defer(ephemeral=True)
    tokens_data = await read_github_file(AUTH_FILE)
    count = len([t for t in tokens_data[0] if t.strip()])
    embed = discord.Embed(title="📊 Bot Durumu", description=f"Şu an bota **{count}** kişi yetki vermiş durumda.", color=discord.Color.blue())
    await interaction.followup.send(embed=embed, ephemeral=True)

@bot.tree.command(name="join", description="İzin veren hesapları Sunucu ID'si ile sunucuya sokar")
@app_commands.describe(sunucu_id="Sunucunun ID'si", kac_adam="Kaç adam çekilecek")
async def join_cmd(interaction: discord.Interaction, sunucu_id: str, kac_adam: int = 10):
    if interaction.user.id != OWNER_ID: return await interaction.response.send_message("⛔ Owner only.", ephemeral=True)
    await interaction.response.defer()
    guild_id = sunucu_id.strip()
    tokens_data = await read_github_file(AUTH_FILE)
    current_tokens = [t.strip() for t in tokens_data[0] if t.strip()]
    if not current_tokens: return await interaction.followup.send("❌ Kimse izin vermemiş!")
    selected_tokens = random.sample(current_tokens, min(kac_adam, len(current_tokens)))
    msg = await interaction.followup.send(f"⏳ **{guild_id}** ID'li sunucuya {len(selected_tokens)} hesap sokuluyor...")
    success, fail = 0, 0
    for token in selected_tokens:
        headers = {"Authorization": f"Bot {TOKEN}", "Content-Type": "application/json"}
        try:
            async with aiohttp.ClientSession() as session:
                user_headers = {"Authorization": f"Bearer {token}"}
                async with session.get("https://discord.com/api/v10/users/@me", headers=user_headers) as u_resp:
                    if u_resp.status == 200:
                        user_id = (await u_resp.json())["id"]
                        async with session.put(f"https://discord.com/api/v10/guilds/{guild_id}/members/{user_id}", headers=headers, json={"access_token": token}) as j_resp:
                            if j_resp.status in [200, 201, 204]: success += 1
                            else: fail += 1
                    else: fail += 1
        except: fail += 1
        await asyncio.sleep(1.5)
    await msg.edit(content=f"✅ Bitti!\nHedef Sunucu ID: **{guild_id}**\n\n✔️ Başarılı: **{success}**\n❌ Başarısız: **{fail}**")

@bot.tree.command(name="ekle", description="Stok ekler (Owner Only)")
@app_commands.describe(plan="Plan türü", service="Servis türü", hesaplar="Hesapları alt alta yapıştır")
@app_commands.choices(
    plan=[app_commands.Choice(name="Normal", value="normal"), app_commands.Choice(name="Premium", value="premium"), app_commands.Choice(name="Exclusive", value="exclusive")],
    service=[app_commands.Choice(name="Steam", value="steam"), app_commands.Choice(name="Netflix", value="netflix")]
)
async def ekle_cmd(interaction: discord.Interaction, plan: app_commands.Choice[str], service: app_commands.Choice[str], hesaplar: str):
    if interaction.user.id != OWNER_ID: return await interaction.response.send_message("⛔ Owner only.", ephemeral=True)
    await interaction.response.defer(ephemeral=True)
    lines = [line.strip() for line in hesaplar.split("\n") if line.strip()]
    if not lines: return await interaction.followup.send("❌ Boş hesap listesi.", ephemeral=True)
    async with github_lock:
        stock, sha = await read_github_file(STOK_FILES[plan.value])
        if service.value == "steam": stock["steam"].extend(lines)
        else: stock["netflix"].extend(lines)
        success = await write_github_file(STOK_FILES[plan.value], stock, sha)
    if success: await interaction.followup.send(f"✅ **{len(lines)}** adet hesap **{plan.name} / {service.name}** stoklarına eklendi!", ephemeral=True)
    else: await interaction.followup.send("❌ Stok eklenirken hata oluştu.", ephemeral=True)

# ==================== BOTU BAŞLATMA ====================
if __name__ == "__main__":
    if not TOKEN:
        print("❌ HATA: DISCORD_TOKEN bulunamadı! .env dosyasını kontrol et.")
    else:
        bot.run(TOKEN)
