import os
import requests
from flask import Flask, request
from dotenv import load_dotenv

load_dotenv()

app = Flask(__name__)

CLIENT_ID = os.getenv('CLIENT_ID')
CLIENT_SECRET = os.getenv('CLIENT_SECRET')
BOT_TOKEN = os.getenv('BOT_TOKEN')
REDIRECT_URI = os.getenv('REDIRECT_URI')
GUILD_ID = os.getenv('GUILD_ID')

@app.route('/')
def home():
    return "Bot Çalışıyor! Linke tıklamak için /callback kullanın."

@app.route('/callback')
def callback():
    code = request.args.get('code')
    if not code:
        return "Hata: Kod alınamadı."

    # 1. Kodu Token'a çevir
    data = {
        'client_id': CLIENT_ID,
        'client_secret': CLIENT_SECRET,
        'grant_type': 'authorization_code',
        'code': code,
        'redirect_uri': REDIRECT_URI
    }
    headers = {'Content-Type': 'application/x-www-form-urlencoded'}
    response = requests.post('https://discord.com/api/oauth2/token', data=data, headers=headers)

    if response.status_code != 200:
        return f"Yetkilendirme Başarısız! (Hata Kodu: {response.status_code}) - Detay: {response.text}"

    token_data = response.json()
    access_token = token_data['access_token']

    # 2. Kullanıcı Bilgilerini Al
    user_headers = {'Authorization': f'Bearer {access_token}'}
    user_response = requests.get('https://discord.com/api/users/@me', headers=user_headers)
    user_data = user_response.json()
    user_id = user_data['id']
    username = user_data['username']

    # 3. Kullanıcıyı Sunucuya Ekle (guilds.join)
    bot_headers = {
        'Authorization': f'Bot {BOT_TOKEN}',
        'Content-Type': 'application/json'
    }
    guild_payload = {'access_token': access_token}
    requests.put(
        f'https://discord.com/api/guilds/{GUILD_ID}/members/{user_id}',
        headers=bot_headers,
        json=guild_payload
    )

    # 4. DM Gönder
    dm_payload = {'recipient_id': user_id}
    dm_response = requests.post('https://discord.com/api/users/@me/channels', headers=bot_headers, json=dm_payload)
    
    if dm_response.status_code == 200:
        dm_channel_id = dm_response.json()['id']
        message_payload = {'content': f'Merhaba **{username}**! Sunucuya başarıyla eklendin. 🎉'}
        requests.post(f'https://discord.com/api/channels/{dm_channel_id}/messages', headers=bot_headers, json=message_payload)

    return f"<h1>Yetkilendirme Başarılı!</h1><p>Hoş geldin {username}. Sunucuya eklendin ve DM kutuna mesaj gönderildi.</p>"

if __name__ == '__main__':
    app.run(port=5000)
