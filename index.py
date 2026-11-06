# ============================================================
#   🔥 RIFAT LIKE API (FIREBASE INTEGRATED) 🔥
#   Free Fire Auto Like API — Vercel Ready
#   Author  : RIFAT
#   Version : 2.1
# ============================================================

from flask import Flask, request, jsonify
import asyncio
from Crypto.Cipher import AES
from Crypto.Util.Padding import pad
from google.protobuf.json_format import MessageToJson
import binascii
import aiohttp
import requests
import json
import like_pb2
import like_count_pb2
import uid_generator_pb2
import time
from collections import defaultdict
from datetime import datetime, timedelta
import random
import os
import urllib.parse
import jwt
import threading

app = Flask(__name__)

# ============================================================
#   ⚙️ CONFIG (RIFAT & FIREBASE)
# ============================================================
NORMAL_API_KEY   = "JIHADTEST"          # 🔴 আপনার গোপন key[span_4](start_span)[span_4](end_span)
INFO_API_ENDPOINT = "https://mahir-info-api.vercel.app/info?uid=1120167200"           # 🔴 আপনার info API[span_5](start_span)[span_5](end_span)

# 🔴 আপনার ফায়ারবেস রিয়েলটাইম ডাটাবেস ইউআরএল এখানে বসান (শেষে স্ল্যাশ ছাড়া)
FIREBASE_URL = "https://likeapi-db77c-default-rtdb.firebaseio.com"

JWT_API_URLS = [
    "https://jwt-brx-ob55.lovable.app/api/public/token",                         # 🔴 API #1[span_6](start_span)[span_6](end_span)[span_7](start_span)[span_7](end_span)
    "https://jwt-brx-ob55.lovable.app/api/public/token",                         # 🔴 API #2[span_8](start_span)[span_8](end_span)[span_9](start_span)[span_9](end_span)
]

# ============================================================
#   🌍 GLOBAL STATE & FIREBASE SYNC
# ============================================================
TOKEN_CACHE      = {}
FAILED_TOKENS    = {}
TOKEN_THREAD_LOCK = threading.Lock()
TOKEN_EXPIRY_TIME_HOURS = 3  # 3 ঘণ্টা পর টোকেন এক্সপায়ার ও রিনিউ হবে

KEY_LIMIT        = 999
tracker          = defaultdict(lambda: [0, 0])
liked_cache      = defaultdict(set)
TRACKER_LOCK     = threading.Lock()

BANGLADESH_OFFSET = 6 * 3600

# ============================================================
#   💾 FIREBASE PERSISTENT STORAGE HELPERS
# ============================================================
def save_to_firebase(path, data):
    if not FIREBASE_URL or "YOUR-DATABASE-NAME" in FIREBASE_URL:
        return
    try:
        url = f"{FIREBASE_URL}/{path}.json"
        # Set sets or dicts to lists for JSON compatibility
        if path == "liked_cache":
            serializable_data = {k: list(v) for k, v in data.items()}
        else:
            serializable_data = data
        requests.put(url, json=serializable_data, timeout=5)
    except Exception as e:
        print(f"❌ Firebase Save error ({path}): {e}")

def load_from_firebase(path):
    if not FIREBASE_URL or "YOUR-DATABASE-NAME" in FIREBASE_URL:
        return {}
    try:
        url = f"{FIREBASE_URL}/{path}.json"
        r = requests.get(url, timeout=5)
        if r.status_code == 200 and r.json():
            data = r.json()
            if path == "liked_cache":
                return defaultdict(set, {k: set(v) for k, v in data.items()})
            return data
    except Exception as e:
        print(f"❌ Firebase Load error ({path}): {e}")
    return {}

def save_data():
    with TRACKER_LOCK:
        save_to_firebase("tracker", dict(tracker))
        save_to_firebase("liked_cache", dict(liked_cache))
        # টোকেন সেভ করার সময় datetime অবজেক্টকে স্ট্রিং এ রূপান্তর করা হলো
        token_serializable = {}
        for uid, info in TOKEN_CACHE.items():
            token_serializable[uid] = {
                "token": info["token"],
                "expires_at": info["expires_at"].isoformat(),
                "api_used": info["api_used"]
            }
        save_to_firebase("token_cache", token_serializable)
        save_to_firebase("failed_tokens", dict(FAILED_TOKENS))

def load_data():
    global tracker, liked_cache, TOKEN_CACHE, FAILED_TOKENS
    try:
        loaded_tracker = load_from_firebase("tracker")
        if loaded_tracker:
            tracker.update(loaded_tracker)

        loaded_liked = load_from_firebase("liked_cache")
        if loaded_liked:
            liked_cache.update(loaded_liked)

        loaded_tokens = load_from_firebase("token_cache")
        if loaded_tokens:
            for uid, info in loaded_tokens.items():
                TOKEN_CACHE[uid] = {
                    "token": info["token"],
                    "expires_at": datetime.fromisoformat(info["expires_at"]),
                    "api_used": info["api_used"]
                }

        loaded_failed = load_from_firebase("failed_tokens")
        if loaded_failed:
            FAILED_TOKENS.update(loaded_failed)

        print(f"✅ RIFAT Firebase Loaded: {len(TOKEN_CACHE)} tokens | {len(FAILED_TOKENS)} failed")
    except Exception as e:
        print(f"❌ Firebase Load error: {e}")


def get_bangladesh_midnight_timestamp():
    now_utc = datetime.utcnow()
    now_bd  = now_utc + timedelta(hours=BANGLADESH_OFFSET)
    midnight_bd = datetime(now_bd.year, now_bd.month, now_bd.day)
    midnight_utc = midnight_bd - timedelta(hours=BANGLADESH_OFFSET)
    return midnight_utc.timestamp()


# ============================================================
#   📂 ACCOUNT LOADER
# ============================================================
def load_accounts(server_name):
    try:
        if server_name in {"IND", "BR", "US", "SAC", "NA"}:
            filename = "account_ind.txt[span_10](start_span)"[span_10](end_span)
        else:
            filename = "account_bd.txt[span_11](start_span)"[span_11](end_span)

        if not os.path.exists(filename):
            print(f"⚠️ {filename} not found!")[span_12](start_span)[span_12](end_span)
            return []

        accounts = []
        seen = set()

        with open(filename, "r", encoding='utf-8') as f:
            for line in f:
                line = line.strip()
                if not line or line.startswith('#'):
                    continue

                if ':' in line:
                    parts = line.split(':', 1)
                    uid = parts[0].strip()
                    pwd = parts[1].strip()

                    if uid and pwd and uid.isdigit() and uid not in seen:
                        seen.add(uid)
                        accounts.append({"uid": uid, "password": pwd})

        print(f"📂 Loaded {len(accounts)} accounts from {filename}")[span_13](start_span)[span_13](end_span)
        return accounts

    except Exception as e:
        print(f"❌ Account load error: {e}")[span_14](start_span)[span_14](end_span)
        return []


# ============================================================
#   🔑 JWT TOKEN GENERATOR (3-HOUR EXPIRY & AUTO DELETE/REFRESH)
# ============================================================
async def generate_jwt_token_with_api(uid, password, api_url, retry_count=0):
    encoded_pwd = urllib.parse.quote(password, safe='')
    max_attempts = 3

    for attempt in range(retry_count, max_attempts):
        try:
            url = f"{api_url}?uid={uid}&password={encoded_pwd}"
            headers = {
                "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36"
            }

            async with aiohttp.ClientSession() as session:
                async with session.get(url, headers=headers, timeout=30) as response:
                    if response.status == 200:
                        data = await response.json()
                        token = None

                        if isinstance(data, dict):
                            if 'token' in data:
                                token = data['token']
                            elif 'access_token' in data:
                                token = data['access_token']
                            elif 'data' in data and isinstance(data['data'], dict):
                                if 'token' in data['data']:
                                    token = data['data']['token']

                        if token:
                            try:
                                payload = jwt.decode(token, options={"verify_signature": False})
                                # ৩ ঘণ্টার মেয়াদের হিসাব
                                exp = payload.get("exp", int(time.time()) + (TOKEN_EXPIRY_TIME_HOURS * 3600))
                            except Exception:
                                exp = int(time.time()) + (TOKEN_EXPIRY_TIME_HOURS * 3600)

                            # পুরনো টোকেন মুছে নতুন টোকেন ক্যাশ ও ফায়ারবেসে সেভ হবে
                            TOKEN_CACHE[uid] = {
                                "token": token,
                                "expires_at": datetime.utcnow() + timedelta(hours=TOKEN_EXPIRY_TIME_HOURS),
                                "api_used": api_url
                            }
                            FAILED_TOKENS.pop(uid, None)
                            print(f"✅ Token OK & Renewed (3h): {uid}")
                            return token
                        else:
                            print(f"⚠️ No token: {uid}")[span_15](start_span)[span_15](end_span)
                    else:
                        print(f"❌ API {response.status}: {uid}")[span_16](start_span)[span_16](end_span)

        except asyncio.TimeoutError:
            print(f"⏰ Timeout: {uid}")[span_17](start_span)[span_17](end_span)
        except Exception as e:
            print(f"❌ Error {uid}: {e}")[span_18](start_span)[span_18](end_span)

        if attempt < max_attempts - 1:
            await asyncio.sleep(2)

    FAILED_TOKENS[uid] = {'timestamp': time.time(), 'api_used': api_url}
    print(f"❌ Failed token: {uid}")[span_19](start_span)[span_19](end_span)
    return None


# ============================================================
#   🚀 PARALLEL TOKEN GENERATION
# ============================================================
async def generate_tokens_batch_parallel(accounts, api_urls):
    if not accounts:
        return {}

    total = len(accounts)
    split = total // len(api_urls)

    api1_accs = accounts[:split]
    api2_accs = accounts[split:]

    print(f"📊 API1: {len(api1_accs)} | API2: {len(api2_accs)}")[span_20](start_span)[span_20](end_span)

    async def gen(idx, accs):
        if not accs:
            return {}
        tokens = {}
        sem = asyncio.Semaphore(100)

        async def worker(acc):
            async with sem:
                t = await generate_jwt_token_with_api(acc['uid'], acc['password'], api_urls[idx])
                if t:
                    tokens[acc['uid']] = t

        await asyncio.gather(*[worker(a) for a in accs], return_exceptions=True)
        return tokens

    start = time.time()
    results = await asyncio.gather(
        gen(0, api1_accs),
        gen(1, api2_accs) if len(api_urls) > 1 else asyncio.sleep(0),
        return_exceptions=True
    )

    all_tokens = {}
    for r in results:
        if isinstance(r, dict):
            all_tokens.update(r)

    print(f"✅ Total: {len(all_tokens)} tokens | {round(time.time()-start,2)}s")[span_21](start_span)[span_21](end_span)
    return all_tokens


# ============================================================
#   ❤️ LIKE SENDING
# ============================================================
async def send_like(encrypted_uid, token, url):
    try:
        edata = bytes.fromhex(encrypted_uid)
        headers = {
            'User-Agent': "Dalvik/2.1.0 (Linux; U; Android 9; ASUS_Z01QD Build/PI)",
            'Authorization': f"Bearer {token}",
            'Content-Type": "application/x-www-form-urlencoded",
            'X-GA': "v1 1",
            'ReleaseVersion': "OB55"
        }
        async with aiohttp.ClientSession() as session:
            async with session.post(url, data=edata, headers=headers, timeout=5) as response:
                return response.status
    except Exception:
        return 500


async def send_likes_batch(target_uid, encrypted_uid, accounts_with_tokens, url):
    if not accounts_with_tokens:
        return 0, 0

    sem = asyncio.Semaphore(100)
    success = 0
    failed = 0

    async def worker(acc, token):
        nonlocal success, failed
        async with sem:
            status = await send_like(encrypted_uid, token, url)
            if status == 200:
                with TRACKER_LOCK:
                    liked_cache[target_uid].add(acc['uid'])
                success += 1
            else:
                failed += 1

    await asyncio.gather(*[worker(a, t) for a, t in accounts_with_tokens], return_exceptions=True)
    return success, failed


async def send_all_likes(target_uid, server_name, url, accounts, encrypted_uid):
    if not accounts:
        return {'success': 0, 'failed': 0, 'total': 0, 'already_liked': 0}

    with TRACKER_LOCK:
        already = liked_cache.get(target_uid, set())
        fresh = [a for a in accounts if a['uid'] not in already]

    print(f"📊 Total: {len(accounts)} | Fresh: {len(fresh)} | Already: {len(already)}")[span_22](start_span)[span_22](end_span)

    if not fresh:
        return {'success': 0, 'failed': 0, 'total': len(accounts),
                'already_liked': len(already), 'fresh_used': 0}

    random.shuffle(fresh)

    need_tokens = []
    have_tokens = []

    for acc in fresh:
        cached = TOKEN_CACHE.get(acc['uid'])
        # ৩ ঘণ্টা পার হয়ে গেলে টোকেন বাদ দিয়ে নতুন জেনারেট করার চেক
        if cached and (cached["expires_at"] - datetime.utcnow()).total_seconds() > 0:
            have_tokens.append((acc, cached["token"]))
        else:
            need_tokens.append(acc)

    tokens_dict = {}
    tok_time = 0

    if need_tokens:
        start = time.time()
        tokens_dict = await generate_tokens_batch_parallel(need_tokens, JWT_API_URLS)
        tok_time = time.time() - start
        save_data()

    all_pairs = list(have_tokens)
    for acc in fresh:
        t = tokens_dict.get(acc['uid'])
        if t:
            all_pairs.append((acc, t))

    if not all_pairs:
        return {'success': 0, 'failed': len(fresh), 'total': len(accounts)}

    start = time.time()
    success, failed = await send_likes_batch(target_uid, encrypted_uid, all_pairs, url)
    like_time = time.time() - start

    save_data()

    return {
        'success': success,
        'failed': failed,
        'total': len(accounts),
        'already_liked': len(already),
        'fresh_used': len(all_pairs),
        'token_gen_time': round(tok_time, 2),
        'like_send_time': round(like_time, 2),
        'total_time': round(tok_time + like_time, 2)
    }


# ============================================================
#   🔐 HELPERS
# ============================================================
def get_valid_token_sync(uid):
    cached = TOKEN_CACHE.get(uid)
    if cached and (cached["expires_at"] - datetime.utcnow()).total_seconds() > 0:
        return cached["token"]
    return None


def encrypt_message(plaintext):
    key = b'Yg&tc%DEuh6%Zc^8'
    iv  = b'6oyZDr22E3ychjM%'
    cipher = AES.new(key, AES.MODE_CBC, iv)
    padded = pad(plaintext, AES.block_size)
    return binascii.hexlify(cipher.encrypt(padded)).decode('utf-8')


def enc(uid):
    msg = uid_generator_pb2.uid_generator()
    msg.krishna_ = int(uid)
    msg.teamXdarks = 1
    return encrypt_message(msg.SerializeToString())


def decode_protobuf(binary):
    try:
        items = like_count_pb2.Info()
        items.ParseFromString(binary)
        return items
    except Exception:
        return None


def get_player_info(encrypted_uid, server_name, token):
    if server_name == "IND":
        url = "https://client.ind.freefiremobile.com/GetPlayerPersonalShow"
    elif server_name in {"BR", "US", "SAC", "NA"}:
        url = "https://client.us.freefiremobile.com/GetPlayerPersonalShow"
    else:
        url = "https://clientbp.ggpolarbear.com/GetPlayerPersonalShow"

    edata = bytes.fromhex(encrypted_uid)
    headers = {
        'User-Agent': "Dalvik/2.1.0 (Linux; U; Android 9; ASUS_Z01QD Build/PI)",
        'Authorization': f"Bearer {token}",
        'Content-Type': "application/x-www-form-urlencoded",
        'X-GA': "v1 1",
        'ReleaseVersion': "OB55"
    }

    try:
        r = requests.post(url, data=edata, headers=headers, verify=False, timeout=10)
        return decode_protobuf(r.content)
    except Exception:
        return None


def get_player_level_from_info(uid):
    try:
        url = f"{INFO_API_ENDPOINT}?uid={uid}[span_23](start_span)"[span_23](end_span)
        r = requests.get(url, timeout=10)
        if r.status_code == 200:
            data = r.json()
            if 'basicInfo' in data and 'level' in data['basicInfo']:
                return data['basicInfo']['level']
        return None
    except Exception:
        return None


# ============================================================
#   📌 MAIN REQUEST PROCESSOR
# ============================================================
def process_like_request(uid, server_name, client_ip, require_key=True, api_key=None):
    total_start = time.time()

    if require_key and api_key != NORMAL_API_KEY:
        return jsonify({"error": "Invalid API Key"}), 403

    if not uid or not server_name:
        return jsonify({"error": "UID and server_name required"}), 400

    valid = ["IND", "BR", "US", "SAC", "NA", "BD", "RU", "ME", "ID"]
    if server_name not in valid:
        return jsonify({"error": f"Invalid server. Use: {valid}"}), 400

    player_level = get_player_level_from_info(uid)

    accounts = load_accounts(server_name)
    if not accounts:
        return jsonify({"error": f"No accounts for {server_name}"}), 500

    bd_midnight = get_bangladesh_midnight_timestamp()

    with TRACKER_LOCK:
        count, last = tracker[client_ip]
        if last < bd_midnight:
            tracker[client_ip] = [0, bd_midnight]
            count = 0
        if count >= KEY_LIMIT:
            return jsonify({
                "error": "Daily limit reached",
                "remains": f"(0/{KEY_LIMIT})",
                "reset_time": "4:00 AM BD Time"
            }), 429

    check_token = None
    for acc in accounts[:5]:
        check_token = get_valid_token_sync(acc['uid'])
        if check_token:
            break

    if not check_token:
        for acc in accounts[:5]:
            try:
                loop = asyncio.new_event_loop()
                asyncio.set_event_loop(loop)
                check_token = loop.run_until_complete(
                    generate_jwt_token_with_api(acc['uid'], acc['password'], JWT_API_URLS[0])
                )
                loop.close()
                if check_token:
                    break
            except Exception:
                continue

    if not check_token:
        return jsonify({"error": "Token generation failed"}), 500

    encrypted_uid = enc(uid)

    before = get_player_info(encrypted_uid, server_name, check_token)
    if before is None:
        return jsonify({"error": "Invalid UID or server"}), 200

    try:
        bd = json.loads(MessageToJson(before))
        before_like = int(bd['AccountInfo'].get('Likes', 0))
    except Exception:
        return jsonify({"error": "Parse failed"}), 200

    if server_name == "IND":
        like_url = "https://client.ind.freefiremobile.com/LikeProfile"
    elif server_name in {"BR", "US", "SAC", "NA"}:
        like_url = "https://client.us.freefiremobile.com/LikeProfile"
    else:
        like_url = "https://clientbp.ggpolarbear.com/LikeProfile"

    asyncio.run(send_all_likes(uid, server_name, like_url, accounts, encrypted_uid))

    after = get_player_info(encrypted_uid, server_name, check_token)
    if after is None:
        return jsonify({"error": "Verify failed"}), 200

    try:
        ad = json.loads(MessageToJson(after))
        after_like = int(ad['AccountInfo']['Likes'])
        player_id  = int(ad['AccountInfo']['UID'])
        player_name = str(ad['AccountInfo']['PlayerNickname'])

        given = after_like - before_like

        if given > 0:
            with TRACKER_LOCK:
                tracker[client_ip][0] += 1
                count = tracker[client_ip][0]
            status = 1
        else:
            status = 2

        remains = KEY_LIMIT - count
        save_data()

        resp = {
            "success": True,
            "LikesGivenByAPI": given,
            "LikesafterCommand": after_like,
            "LikesbeforeCommand": before_like,
            "PlayerNickname": player_name,
            "UID": player_id,
            "status": status,
            "remains": f"({remains}/{KEY_LIMIT})",
            "powered_by": "RIFAT"
        }

        if player_level is not None:
            resp["Level"] = player_level

        return jsonify(resp)

    except Exception as e:
        return jsonify({"error": str(e), "status": 0}), 500


# ============================================================
#   🌐 ROUTES
# ============================================================
@app.route('/like', methods=['GET'])
def handle_like():
    return process_like_request(
        request.args.get("uid"),
        request.args.get("server_name", "").upper(),
        request.remote_addr,
        True,
        request.args.get("key")
    )


@app.route('/', methods=['GET'])
def home():
    return jsonify({
        "status": "online",
        "api": "RIFAT LIKE API",
        "owner": "RIFAT",
        "version": "2.1",
        "endpoint": "/like?uid=<UID>&server_name=<SERVER>&key=<API_KEY>",
        "servers": ["IND", "BR", "US", "SAC", "NA", "BD", "RU", "ME", "ID"]
    })


# Load data on startup from Firebase
load_data()

# Vercel handler
handler = app
