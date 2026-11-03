# language: Python 3.11, file: tfollow.py
import discord
from discord.ext import commands
import aiohttp
import asyncio
import os
import threading
import json
import base64
from flask import Flask, request, render_template_string

# ==================== AYARLAR ====================
TOKEN = os.getenv("DISCORD_TOKEN")
OWNER_ID = int(os.getenv("OWNER_ID", 0))
WEB_PASSWORD = os.getenv("WEB_PASSWORD", "ravex123")
WEB_PORT = int(os.getenv("PORT", 10000))

GITHUB_TOKEN = os.getenv("GITHUB_TOKEN")
GITHUB_REPO = os.getenv("GITHUB_REPO")
GITHUB_FILE = "twitch_tokens.json"
TWITCH_CLIENT_ID = "kimne78kx3ncx6brgo4mv6wki5h1ko" 
# =================================================

TWITCH_TOKENS = []
github_lock = asyncio.Lock()

# ==================== GITHUB VERİTABANI ====================
async def github_get_headers():
    return {"Authorization": f"token {GITHUB_TOKEN}", "Accept": "application/vnd.github.v3+json"}

async def read_github_tokens():
    url = f"https://api.github.com/repos/{GITHUB_REPO}/contents/{GITHUB_FILE}"
    async with aiohttp.ClientSession() as session:
        async with session.get(url, headers=await github_get_headers()) as resp:
            if resp.status == 200:
                data = await resp.json()
                content = base64.b64decode(data['content']).decode('utf-8')
                return json.loads(content), data['sha']
            return [], None

async def write_github_tokens(tokens_list, sha):
    url = f"https://api.github.com/repos/{GITHUB_REPO}/contents/{GITHUB_FILE}"
    content = base64.b64encode(json.dumps(tokens_list, indent=2).encode('utf-8')).decode('utf-8')
    payload = {"message": "Twitch Token Guncellemesi", "content": content}
    if sha: payload["sha"] = sha
        
    async with aiohttp.ClientSession() as session:
        async with session.put(url, headers=await github_get_headers(), json=payload) as resp:
            return resp.status in [200, 201]

async def add_tokens_safely(new_tokens):
    async with github_lock:
        for _ in range(3):
            tokens, sha = await read_github_tokens()
            # Sadece olmayanları ekle (tekrarları önle)
            for t in new_tokens:
                if t not in tokens:
                    tokens.append(t)
            if await write_github_tokens(tokens, sha): return True
            await asyncio.sleep(1)
        return False
# =========================================================

# ==================== WEB PANELİ ====================
web_app = Flask(__name__)

HTML_PAGE = """<!DOCTYPE html>
<html>
<head><meta charset="UTF-8"><title>Twitch Token Panel</title>
<style>body{background:#18181b;color:#fff;font-family:sans-serif;padding:20px;text-align:center;} input,textarea{width:80%;padding:10px;margin:10px 0;background:#2b2b2b;color:#fff;border:1px solid #444;} button{padding:10px 20px;background:#9147ff;color:#fff;border:none;cursor:pointer;} .count{color:#9147ff; font-weight:bold;}</style>
</head>
<body>
    <h2>Twitch Token Ekle</h2>
    <p>Kasadaki Toplam Token: <span class="count">{{ count }}</span></p>
    <form method="POST">
        <input type="password" name="password" placeholder="Panel Şifresi" required><br>
        <textarea name="tokens" rows="6" placeholder="Her satıra bir token yapıştırın..." required></textarea><br>
        <button type="submit">Tokenleri Ekle</button>
    </form>
    {% if message %}<h3 style="color:lightgreen;">{{ message }}</h3>{% endif %}
</body>
</html>"""

def run_async(coro):
    loop = asyncio.new_event_loop()
    asyncio.set_event_loop(loop)
    return loop.run_until_complete(coro)

@web_app.route('/', methods=['GET', 'POST'])
def index():
    global TWITCH_TOKENS
    if request.method == 'POST':
        if request.form.get('password') != WEB_PASSWORD:
            return render_template_string(HTML_PAGE, message="Hatalı Şifre!", count=len(TWITCH_TOKENS))
        
        tokens_raw = request.form.get('tokens')
        new_tokens = [t.strip() for t in tokens_raw.split("\n") if t.strip()]
        
        success = run_async(add_tokens_safely(new_tokens))
        if success:
            TWITCH_TOKENS = run_async(read_github_tokens())[0]
            return render_template_string(HTML_PAGE, message=f"{len(new_tokens)} token işlendi!", count=len(TWITCH_TOKENS))
        else:
            return render_template_string(HTML_PAGE, message="GitHub'a kaydedilemedi!", count=len(TWITCH_TOKENS))
    
    # Sayfa her yenilendiğinde GitHub'dan güncel sayıyı çek
    TWITCH_TOKENS = run_async(read_github_tokens())[0]
    return render_template_string(HTML_PAGE, count=len(TWITCH_TOKENS))

def run_web():
    web_app.run(host='0.0.0.0', port=WEB_PORT)
# =========================================================

# ==================== DISCORD BOT ====================
class MyBot(commands.Bot):
    def __init__(self):
        intents = discord.Intents.default()
        super().__init__(command_prefix=".", intents=intents)

    async def setup_hook(self):
        await self.tree.sync()
        print("[+] Slash komutları hazır.")

    async def on_ready(self):
        global TWITCH_TOKENS
        TWITCH_TOKENS = await read_github_tokens()
        TWITCH_TOKENS = TWITCH_TOKENS[0]
        print(f"[+] Bot aktif: {self.user.name}")
        print(f"[+] GitHub'dan Yüklenen Token Sayısı: {len(TWITCH_TOKENS)}")
        
        if not any(t.name == "WebServerThread" for t in threading.enumerate()):
            threading.Thread(target=run_web, daemon=True, name="WebServerThread").start()

bot = MyBot()

@bot.tree.command(name="tfollow", description="Belirtilen Twitch kanalına takipçi gönderir")
async def tfollow(interaction: discord.Interaction, twitch_ismi: str):
    if interaction.user.id != OWNER_ID:
        return await interaction.response.send_message("⛔ Bu komutu sadece Owner kullanabilir.", ephemeral=True)

    await interaction.response.defer()
    
    # Komut kullanıldığında en güncel listeyi çek
    tokens_data = await read_github_tokens()
    current_tokens = tokens_data[0]
    
    if not current_tokens:
        return await interaction.followup.send("❌ Panelden hiç Twitch token'ı eklenmemiş!")

    headers = {"Client-ID": TWITCH_CLIENT_ID, "Content-Type": "application/json"}
    
    gql_query = {
        "query": "query($login: String!) { user(login: $login) { id } }",
        "variables": {"login": twitch_ismi}
    }
    
    async with aiohttp.ClientSession() as session:
        async with session.post("https://gql.twitch.tv/gql", json=gql_query, headers=headers) as resp:
            data = await resp.json()
            if not data.get("data") or not data["data"].get("user"):
                return await interaction.followup.send(f"❌ **{twitch_ismi}** adında bir Twitch kanalı bulunamadı.")
            target_id = data["data"]["user"]["id"]

    success = 0
    fail = 0
    follow_mutation = {
        "query": "mutation($targetId: ID!) { followUser(input: { targetID: $targetId }) { follow { user { id } } } }",
        "variables": {"targetId": target_id}
    }

    for token in current_tokens:
        t_headers = {
            "Client-ID": TWITCH_CLIENT_ID,
            "Authorization": f"OAuth {token}",
            "Content-Type": "application/json"
        }
        
        async with aiohttp.ClientSession() as session:
            async with session.post("https://gql.twitch.tv/gql", json=follow_mutation, headers=t_headers) as resp:
                if resp.status == 200:
                    res_data = await resp.json()
                    if not res_data.get("errors"): success += 1
                    else: fail += 1
                else: fail += 1
        await asyncio.sleep(1.2) # Ban yememek için bekleme

    await interaction.followup.send(f"✅ İşlem tamamlandı!\n🎯 Hedef: **{twitch_ismi}**\n\n✔️ Başarılı Takip: **{success}**\n❌ Başarısız Token: **{fail}**")

if __name__ == "__main__":
    if not TOKEN or not GITHUB_TOKEN or not GITHUB_REPO:
        print("❌ Eksik Environment değişkeni!")
        exit()
    bot.run(TOKEN)
