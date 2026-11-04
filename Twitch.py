# language: Python 3.11, file: tfollow.py
import discord
from discord.ext import commands
import aiohttp
import asyncio
import os
import threading
import json
import base64
import random
import time
from flask import Flask, request, render_template_string

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
        tokens, sha = await read_github_tokens()
        for t in new_tokens:
            clean_t = t.strip()
            if clean_t and clean_t not in tokens:
                tokens.append(clean_t)
        return await write_github_tokens(tokens, sha)
# =========================================================

# ==================== ABİNİN KODU (TwitchFollower Sınıfı) ====================
class TwitchFollower:
    def __init__(self, log_callback=print):
        self.log_callback = log_callback
        self.followed_records = {}
        self.lock = threading.Lock()
        self.running = False
        self.proxies = self._load_proxies()

    def _log(self, message):
        self.log_callback(message)

    def _load_proxies(self):
        proxies = []
        if os.path.exists("proxies.txt"):
            with open("proxies.txt", "r") as f:
                for line in f:
                    line = line.strip()
                    if line and not line.isspace():
                        if '://' not in line:
                            line = f"http://{line}"
                        proxies.append(line)
        return proxies

    def get_user_id(self, user):
        headers = {
            "Client-Id": "kimne78kx3ncx6brgo4mv6wki5h1ko",
            "Content-Type": "application/json",
            "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36",
        }

        payload = json.dumps([{
            "operationName": "GetIDFromLogin",
            "variables": {"login": user},
            "extensions": {
                "persistedQuery": {
                    "version": 1,
                    "sha256Hash": "94e82a7b1e3c21e186daa73ee2afc4b8f23bade1fbbff6fe8ac133f50a2f58ca"
                }
            }
        }])

        try:
            loop = asyncio.new_event_loop()
            asyncio.set_event_loop(loop)
            id_result = loop.run_until_complete(self._fetch_user_id_async(user, headers, payload))
            loop.close()
            return id_result
        except Exception as e:
            self._log(f"Error getting user ID for {user}: {e}")
            return False

    async def _fetch_user_id_async(self, user, headers, payload):
        try:
            proxy_url = None
            if self.proxies:
                proxy_url = random.choice(self.proxies)
                self._log(f"Using proxy for user ID lookup: {proxy_url}")

            connector = aiohttp.TCPConnector(ssl=False)
            timeout = aiohttp.ClientTimeout(total=30)
            
            async with aiohttp.ClientSession(connector=connector, timeout=timeout) as session:
                async with session.post("https://gql.twitch.tv/gql", headers=headers, data=payload, proxy=proxy_url) as response:
                    if response.status == 200:
                        data = await response.json()
                        return data[0]["data"]["user"]["id"]
        except Exception as e:
            self._log(f"Network error getting ID for {user}: {e}")
        return False

    async def _execute_follow_request(self, target_id, token, target_username):
        try:
            headers = {
                "Accept": "application/json",
                "Accept-Language": "en-US",
                "Authorization": f"OAuth {token}",
                "Content-Type": "application/json",
                "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36"
            }

            payload = json.dumps([{
                "operationName": "FollowUserMutation",
                "variables": {
                    "targetId": str(target_id),
                    "disableNotifications": False
                },
                "extensions": {
                    "persistedQuery": {
                        "version": 1,
                        "sha256Hash": "cd112d9483ede85fa0da514a5657141c24396efbc7bac0ea3623e839206573b8"
                    }
                }
            }])

            proxy_url = None
            if self.proxies:
                proxy_url = random.choice(self.proxies)

            connector = aiohttp.TCPConnector(ssl=False)
            timeout = aiohttp.ClientTimeout(total=30)
            
            async with aiohttp.ClientSession(connector=connector, timeout=timeout) as session:
                async with session.post("https://gql.twitch.tv/gql", data=payload, headers=headers, proxy=proxy_url) as response:
                    result_text = await response.text()
                    if response.status in (200, 204):
                        if "errors" not in result_text.lower():
                            return True
                    return False
        except Exception as e:
            return False

    async def _follow_worker(self, target_id, tokens_list, target_username, max_follows, stats):
        while self.running and stats["completed"] < max_follows:
            available_token = None
            with self.lock:
                unused_tokens = [t for t in tokens_list if t not in self.followed_records or target_id not in self.followed_records[t]]
                if unused_tokens:
                    available_token = random.choice(unused_tokens)
                else:
                    break
            
            if not available_token:
                await asyncio.sleep(0.5)
                continue
            
            success = await self._execute_follow_request(target_id, available_token, target_username)
            
            if success:
                with self.lock:
                    stats["completed"] += 1
                    if available_token not in self.followed_records:
                        self.followed_records[available_token] = []
                    self.followed_records[available_token].append(target_id)
            
            await asyncio.sleep(random.uniform(0.1, 0.2))

    def execute_follows(self, target_id, follow_count, tokens_data, target_username):
        completion_event = threading.Event()
        
        def run_async_loop():
            loop = asyncio.new_event_loop()
            asyncio.set_event_loop(loop)
            
            async def main_async():
                stats = {"completed": 0, "active_workers": 0}
                tasks = []
                num_workers = min(100, follow_count, len(tokens_data))
                
                for _ in range(num_workers):
                    task = asyncio.create_task(self._follow_worker(target_id, tokens_data, target_username, follow_count, stats))
                    tasks.append(task)
                    stats["active_workers"] += 1
                    await asyncio.sleep(0.01)
                
                await asyncio.gather(*tasks, return_exceptions=True)
                completion_event.set()
            
            try:
                loop.run_until_complete(main_async())
            except Exception as e:
                pass
            finally:
                loop.close()
        
        threading.Thread(target=run_async_loop, daemon=True).start()
        return completion_event
# =========================================================================

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
async def tfollow(interaction: discord.Interaction, twitch_ismi: str, adet: int = 10):
    if interaction.user.id != OWNER_ID:
        return await interaction.response.send_message("⛔ Owner only.", ephemeral=True)

    await interaction.response.defer()
    
    tokens_data = await read_github_tokens()
    current_tokens = [t.strip() for t in tokens_data[0] if t.strip()] 
    
    if not current_tokens:
        return await interaction.followup.send("❌ Panelden hiç Twitch token'ı eklenmemiş!")

    # Abinin sınıfını başlat
    follower = TwitchFollower()
    
    # Hedefin ID'sini al
    target_id = follower.get_user_id(twitch_ismi)
    if not target_id:
        return await interaction.followup.send(f"❌ **{twitch_ismi}** adında bir Twitch kanalı bulunamadı.")

    # İşlemi başlat
    follower.running = True
    completion_event = follower.execute_follows(target_id, adet, current_tokens, twitch_ismi)

    # Discord'un zaman aşımına uğramaması için bekleme mesajı at
    msg = await interaction.followup.send(f"⏳ **{twitch_ismi}** için {adet} takipçi gönderiliyor... (Proxiesiz çalışıyorsa yavaş olabilir)")

    # Thread bittiğinde Discord'u güncelle
    def wait_for_completion():
        completion_event.wait()
        follower.running = False
        # Asenkron Discord mesajını güncellemek için botun event loop'una gönder
        asyncio.run_coroutine_threadsafe(
            msg.edit(content=f"✅ İşlem tamamlandı!\n🎯 Hedef: **{twitch_ismi}**\n📊 Gönderilen: **{adet}**"),
            bot.loop
        )

    threading.Thread(target=wait_for_completion, daemon=True).start()

if __name__ == "__main__":
    if not TOKEN or not GITHUB_TOKEN or not GITHUB_REPO:
        print("❌ Eksik Environment!")
        exit()
    bot.run(TOKEN)
