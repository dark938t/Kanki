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
from playwright.async_api import async_playwright

# ==================== AYARLAR ====================
TOKEN = os.getenv("DISCORD_TOKEN")
OWNER_ID = int(os.getenv("OWNER_ID", 0))
WEB_PASSWORD = os.getenv("WEB_PASSWORD", "ravex123")
WEB_PORT = int(os.getenv("PORT", 10000))

GITHUB_TOKEN = os.getenv("GITHUB_TOKEN")
GITHUB_REPO = os.getenv("GITHUB_REPO")
GITHUB_FILE = "twitch_tokens.json"
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
            for t in new_tokens:
                clean_t = t.strip()
                if clean_t and clean_t not in tokens:
                    tokens.append(clean_t)
            if await write_github_tokens(tokens, sha): return True
            await asyncio.sleep(1)
        return False
# =========================================================

# ==================== WEB PANELİ ====================
web_app = Flask(__name__)
HTML_PAGE = """<!DOCTYPE html><html><head><meta charset="UTF-8"><title>Panel</title><style>body{background:#18181b;color:#fff;font-family:sans-serif;padding:20px;text-align:center;}input,textarea{width:80%;padding:10px;margin:10px 0;background:#2b2b2b;color:#fff;border:1px solid #444;}button{padding:10px 20px;background:#9147ff;color:#fff;border:none;cursor:pointer;}</style></head><body><h2>Twitch Token Ekle</h2><p>Toplam Token: <b>{{ count }}</b></p><form method="POST"><input type="password" name="password" placeholder="Şifre" required><br><textarea name="tokens" rows="6" required></textarea><br><button type="submit">Ekle</button></form>{% if message %}<h3 style="color:lightgreen;">{{ message }}</h3>{% endif %}</body></html>"""

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
            return render_template_string(HTML_PAGE, message="Eklendi!", count=len(TWITCH_TOKENS))
        return render_template_string(HTML_PAGE, message="Hata!", count=len(TWITCH_TOKENS))
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

    async def on_ready(self):
        global TWITCH_TOKENS
        TWITCH_TOKENS = (await read_github_tokens())[0]
        print(f"[+] Bot aktif: {self.user.name} | Token: {len(TWITCH_TOKENS)}")
        if not any(t.name == "WebServerThread" for t in threading.enumerate()):
            threading.Thread(target=run_web, daemon=True, name="WebServerThread").start()

bot = MyBot()

@bot.tree.command(name="tfollow", description="Takipçi gönder")
async def tfollow(interaction: discord.Interaction, twitch_ismi: str):
    if interaction.user.id != OWNER_ID:
        return await interaction.response.send_message("⛔ Owner only.", ephemeral=True)

    await interaction.response.defer()
    tokens_data = await read_github_tokens()
    current_tokens = [t.strip() for t in tokens_data[0] if t.strip()] 
    
    if not current_tokens:
        return await interaction.followup.send("❌ Token yok!")

    success = 0
    fail = 0
    error_message = ""

    # PLAYWRIGHT İLE GERÇEK TARAYICI AÇIYORUZ
    async with async_playwright() as p:
        browser = await p.chromium.launch(headless=True)
        
        for token in current_tokens:
            try:
                context = await browser.new_context()
                # Token'ı çerez olarak tarayıcıya ekle
                await context.add_cookies([{
                    "name": "auth-token",
                    "value": token,
                    "domain": ".twitch.tv",
                    "path": "/"
                }])
                
                page = await context.new_page()
                # Hedef kanalın sayfasına git
                await page.goto(f"https://www.twitch.tv/{twitch_ismi}", wait_until="domcontentloaded", timeout=15000)
                await asyncio.sleep(3) # Sayfanın yüklenmesini bekle

                # "Takip Et" (Follow) butonunu bul ve tıkla
                follow_btn = page.locator('[data-a-target="follow-button"]')
                
                if await follow_btn.count() > 0:
                    # Butonda "Takip Et" yazıyorsa tıkla
                    await follow_btn.click(timeout=5000)
                    success += 1
                else:
                    # Buton yoksa ya zaten takip ediyordur ya da başka bir sorun vardır
                    fail += 1
                
                await context.close()
            except Exception as e:
                fail += 1
                error_message = str(e)
            
            await asyncio.sleep(2) # Ban yememek için bekle

        await browser.close()

    msg = f"✅ Bitti!\n🎯 Hedef: **{twitch_ismi}**\n\n✔️ Başarılı: **{success}**\n❌ Başarısız: **{fail}**"
    if fail > 0 and error_message:
        msg += f"\n\n⚠️ Hata: `{error_message}`"
    await interaction.followup.send(msg)

if __name__ == "__main__":
    if not TOKEN or not GITHUB_TOKEN or not GITHUB_REPO:
        exit()
    bot.run(TOKEN)
