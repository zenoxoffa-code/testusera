import os
import re
import json
import html
import time
import sqlite3
import secrets
import requests
from datetime import datetime
from difflib import get_close_matches
from zoneinfo import ZoneInfo
import jdatetime
from flask import Flask, request, jsonify, Response, session, redirect, g
from requests.adapters import HTTPAdapter
from urllib3.util.retry import Retry
from werkzeug.security import generate_password_hash, check_password_hash

BASE_DIR = os.path.dirname(os.path.abspath(__file__))
PORT = int(os.environ.get("PORT", "4590"))
DB_PATH = os.environ.get("IROVAN_DB", os.path.join(BASE_DIR, "irovan.db"))
SECRET_PATH = os.path.join(BASE_DIR, "secret.key")
API_TOKEN = os.environ.get("IROVAN_API_TOKEN", "")
USE_HTTPS = os.environ.get("IROVAN_HTTPS", "") == "1"
ALLOW_REGISTER = os.environ.get("IROVAN_ALLOW_REGISTER", "1") == "1"
APP_VERSION = "2.3.0"

GAPGPT_BASE_URL = os.environ.get("GAPGPT_BASE_URL", "https://api.gapgpt.app/v1")

GAPGPT_API_KEY = os.environ.get("GAPGPT_API_KEY", "sk-2SA6W5w9glDsIl6CflqMFh2To7lZVQekMW5IdLgp0ugWBHZp")
GAPGPT_MODEL = os.environ.get("GAPGPT_MODEL", "gpt-4o-mini")

GAPGPT_API_KEY_2 = os.environ.get("GAPGPT_API_KEY_2", "sk-W9gkcXvrdsVZRYwW97zoXHkGuDSHBaxLWAKTlH7OeqmUjW1b")
GAPGPT_MODEL_2 = os.environ.get("GAPGPT_MODEL_2", "gapgpt-qwen-3.5")

IMAGE_TOKEN = os.environ.get("IROVAN_IMAGE_TOKEN", "ab5d0cef9a4af48d86805b3e7c745ae20c0e6df2c5eda643")
IMAGE_API_URL = os.environ.get("IROVAN_IMAGE_URL", "https://amir-coder.ir/genimage/genimage.php")

TEHRAN_TZ = ZoneInfo("Asia/Tehran")

MODEL_NAME = "ایروان اسلیم | irovan-slim"
PLUS_NAME = "GPT"
GREETING_TEXT = "سلام من ایروان اسلیم | irovan-slim هستم چه کمکی از دستم بر میاد؟"
IDENTITY_TEXT = "من مدل ایروان اسلیم | irovan-slim هستم و توسط تیم ایروان ساخته شدم."
SERVER_ERROR = "مشکلی در سرورهای ایروان پیش آمده و نمی‌توانم پاسخ بدهم. لطفاً بعداً دوباره تلاش کنید."
IMAGE_READY_TEXT = "این هم عکس شما:"
FOOTER = "\n\nایروان همیشه در خدمت شماست\nhttps://irovan.ir"
TRIGGERS = ["ایروان", "آیروان", "irovan"]

SYSTEM_PROMPT = (
    f"تو یک دستیار هوش مصنوعی به نام {MODEL_NAME} هستی که توسط تیم ایروان ساخته شده. "
    "به فارسی، ساده و مفید جواب بده و در نوشتن کد کمک کن. "
    "هرگز نگو مدل دیگه‌ای هستی یا شرکت دیگه‌ای ساختتت. "
    "اگه پرسیدن فقط بگو مدل irovan-slim | ایروان اسلیم هستم."
    "سازنده تو تیم ایروانه ک هر کی درباره مهدی شامی و زنوکس zenox پرسید باید بهشون بگی که اینا از اعضای ایروانن"
)

MODELS = {
    "slim": {"label": MODEL_NAME, "api_key": GAPGPT_API_KEY, "model": GAPGPT_MODEL, "use_prompt": True},
    "plus": {"label": PLUS_NAME, "api_key": GAPGPT_API_KEY_2, "model": GAPGPT_MODEL_2, "use_prompt": False},
}
DEFAULT_MODEL = "slim"

OTHER_MODELS = re.compile(
    r"(chatgpt|gpt-?\d[\w.\-]*|gpt|openai|claude|anthropic|gemini|bard|google|"
    r"qwen|alibaba|llama|meta ai|deepseek|mistral|grok|xai|copilot)",
    re.IGNORECASE,
)
IDENTITY_Q = re.compile(
    r"(کی ساختت|سازنده|اسمت|نامت|اسم تو|تو کی هستی|تو کیستی|چه مدلی|کدوم مدل|"
    r"who (made|created|built) you|what model|your name|who are you)",
    re.IGNORECASE,
)

IMAGE_INTENT = re.compile(
    r"(عکس\s*ساز|تصویر\s*ساز|"
    r"(عکس|تصویر|نقاشی|لوگو|پوستر)\s.{0,60}(بساز|بسازی|بسازید|تولید|درست کن|بکش|بکشی|طراحی)|"
    r"(بساز|بسازی|بسازید|تولید|درست کن|بکش|طراحی)\s.{0,60}(عکس|تصویر|نقاشی|لوگو|پوستر)|"
    r"\b(generate|create|make|draw|produce|paint)\b.{0,30}\b(image|picture|photo|drawing|illustration)s?\b)",
    re.IGNORECASE,
)
IMAGE_LEAD = {
    "لطفا", "لطفاً", "برام", "برایم", "بهم", "به", "من", "میشه", "می", "شه", "میتونی", "تونی",
    "توانی", "بتونی", "بتوانی", "میخوام", "خوام", "یه", "یک", "یکی", "عکس", "تصویر", "نقاشی",
    "از", "please", "can", "could", "you", "generate", "create", "make", "draw", "produce",
    "paint", "an", "a", "image", "picture", "photo", "drawing", "illustration", "of", "me", "for",
}
IMAGE_VERBS = {
    "بساز", "بسازی", "بسازید", "تولید", "کن", "بکش", "بکشی", "بزن", "درست", "طراحی",
    "generate", "create", "make", "draw", "produce", "paint",
}

WEATHER_CODES = {
    0: "آسمان صاف", 1: "تقریباً صاف", 2: "کمی ابری", 3: "ابری",
    45: "مه", 48: "مه غلیظ",
    51: "نم‌نم باران", 53: "نم‌نم باران", 55: "نم‌نم باران شدید",
    56: "نم‌نم باران یخ‌زده", 57: "نم‌نم باران یخ‌زده شدید",
    61: "باران ضعیف", 63: "باران", 65: "باران شدید",
    66: "باران یخ‌زده", 67: "باران یخ‌زده شدید",
    71: "برف ضعیف", 73: "برف", 75: "برف شدید", 77: "دانه‌های برف",
    80: "رگبار", 81: "رگبار", 82: "رگبار شدید",
    85: "بارش برف", 86: "بارش برف شدید",
    95: "رعد و برق", 96: "رعد و برق با تگرگ", 99: "رعد و برق با تگرگ شدید",
}

CITY_MAP = {
    "تهران": "Tehran", "مشهد": "Mashhad", "اصفهان": "Isfahan", "شیراز": "Shiraz",
    "تبریز": "Tabriz", "کرج": "Karaj", "اهواز": "Ahvaz", "قم": "Qom",
    "رشت": "Rasht", "کرمانشاه": "Kermanshah", "ارومیه": "Urmia", "یزد": "Yazd",
    "کرمان": "Kerman", "همدان": "Hamadan", "اراک": "Arak", "زاهدان": "Zahedan",
    "بندرعباس": "Bandar Abbas", "ساری": "Sari", "گرگان": "Gorgan",
    "زنجان": "Zanjan", "قزوین": "Qazvin", "اردبیل": "Ardabil",
    "سنندج": "Sanandaj", "بوشهر": "Bushehr", "خرم آباد": "Khorramabad",
    "کیش": "Kish", "بجنورد": "Bojnord", "بیرجند": "Birjand", "ایلام": "Ilam",
    "سمنان": "Semnan", "یاسوج": "Yasuj", "شهرکرد": "Shahrekord",
}

WEATHER_WORDS = {"هوا", "هوای", "weather", "/weather"}
FILLER_WORDS = {
    "چطوره", "چطور", "چطوریه", "چگونه", "چجوریه", "چه", "جوریه", "است", "هست",
    "چیه", "چی", "چنده", "الان", "الآن", "امروز", "فعلا", "فعلاً", "در", "تو",
    "توی", "برای", "شهر", "رو", "را", "وضعیت", "بگو", "بده", "لطفا", "لطفاً",
    "میشه", "می‌شه", "ممکنه", "یه", "یک", "how", "is", "the", "in", "of", "now",
}


def read_asset(name: str) -> bytes:
    path = os.path.join(BASE_DIR, name)
    try:
        with open(path, "rb") as f:
            return f.read()
    except OSError:
        return b""


LOGO_BYTES = read_asset("logo.png")
BG_BYTES = read_asset("bg.jpg")


def build_direct_session() -> requests.Session:
    s = requests.Session()
    s.trust_env = False
    retry = Retry(
        total=3,
        backoff_factor=1.5,
        status_forcelist=[429, 500, 502, 503, 504],
        allowed_methods=["POST"],
        raise_on_status=False,
    )
    s.mount("https://", HTTPAdapter(max_retries=retry))
    s.mount("http://", HTTPAdapter(max_retries=retry))
    return s


DIRECT = build_direct_session()


def log_error(where: str, detail) -> None:
    print(f"[irovan] {where}: {detail}", flush=True)


def normalize(text: str) -> str:
    text = text.replace("ي", "ی").replace("ك", "ک").replace("\u200c", " ")
    text = re.sub(r"[؟?!.,،:؛;]", " ", text)
    return re.sub(r"\s+", " ", text).strip()


def fix_identity(user_text: str, reply: str) -> str:
    if IDENTITY_Q.search(user_text):
        return IDENTITY_TEXT
    return OTHER_MODELS.sub("ایروان", reply)


def ask_gapgpt(user_message: str, history=None, model_key: str = DEFAULT_MODEL) -> str:
    cfg = MODELS.get(model_key, MODELS[DEFAULT_MODEL])
    if not cfg["api_key"]:
        log_error("ask_gapgpt", "api key not set for " + model_key)
        return SERVER_ERROR
    messages = []
    if cfg["use_prompt"]:
        messages.append({"role": "system", "content": SYSTEM_PROMPT})
    for item in history or []:
        messages.append({"role": item["role"], "content": item["content"]})
    messages.append({"role": "user", "content": user_message})
    try:
        r = DIRECT.post(
            f"{GAPGPT_BASE_URL}/chat/completions",
            headers={
                "Authorization": f"Bearer {cfg['api_key']}",
                "Content-Type": "application/json",
                "Accept": "application/json",
                "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64)",
            },
            json={"model": cfg["model"], "messages": messages, "max_tokens": 2000},
            timeout=(10, 90),
        )
        if r.status_code != 200:
            log_error("ask_gapgpt", f"{r.status_code} {r.text[:200]}")
            return SERVER_ERROR
        content = r.json()["choices"][0]["message"]["content"].strip()
        if not content:
            return SERVER_ERROR
        if cfg["use_prompt"]:
            content = fix_identity(user_message, content)
        return content
    except Exception as e:
        log_error("ask_gapgpt", e)
        return SERVER_ERROR


def extract_image_prompt(clean: str) -> str:
    words = clean.split()
    while words and words[0].lower() in IMAGE_LEAD:
        words.pop(0)
    words = [w for w in words if w.lower() not in IMAGE_VERBS]
    return " ".join(words).strip() or clean


def make_image(clean: str) -> str:
    if not IMAGE_TOKEN:
        log_error("make_image", "image token not set")
        return SERVER_ERROR
    prompt = extract_image_prompt(clean)
    try:
        r = DIRECT.get(
            IMAGE_API_URL,
            params={"token": IMAGE_TOKEN, "text": prompt},
            headers={"User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64)"},
            timeout=(10, 120),
        )
        data = r.json()
        url = data.get("url") if data.get("success") else None
        if not url:
            log_error("make_image", f"{r.status_code} {r.text[:200]}")
            return SERVER_ERROR
        return f"{IMAGE_READY_TEXT}\n![image]({url})"
    except Exception as e:
        log_error("make_image", e)
        return SERVER_ERROR


def get_time() -> str:
    now = datetime.now(TEHRAN_TZ)
    return f"ساعت الان (به وقت تهران): {now.strftime('%H:%M:%S')}"


def fetch_web_datetime() -> datetime:
    try:
        r = requests.get(
            "https://timeapi.io/api/Time/current/zone",
            params={"timeZone": "Asia/Tehran"},
            timeout=10,
        )
        d = r.json()
        return datetime(d["year"], d["month"], d["day"], d["hour"], d["minute"], d["seconds"])
    except Exception:
        pass
    try:
        r = requests.get("https://worldtimeapi.org/api/timezone/Asia/Tehran", timeout=10)
        return datetime.fromisoformat(r.json()["datetime"]).replace(tzinfo=None)
    except Exception:
        pass
    return datetime.now(TEHRAN_TZ).replace(tzinfo=None)


def get_date() -> str:
    now = fetch_web_datetime()
    try:
        jdatetime.set_locale("fa_IR")
    except Exception:
        pass
    j = jdatetime.datetime.fromgregorian(datetime=now)
    return (
        f"تاریخ امروز: {j.strftime('%A %d %B %Y')}\n"
        f"میلادی: {now.strftime('%Y-%m-%d')}"
    )


def extract_city(clean: str) -> str:
    text = re.sub(r"آب\s*و?\s*هوا", "هوا", clean)
    words = [w for w in text.split() if w.lower() not in WEATHER_WORDS]
    joined = " ".join(words)

    for name in sorted(CITY_MAP, key=len, reverse=True):
        if re.search(rf"(?<!\S){re.escape(name)}(?!\S)", joined):
            return name

    for w in words:
        close = get_close_matches(w, list(CITY_MAP), n=1, cutoff=0.8)
        if close:
            return close[0]

    filler = list(FILLER_WORDS)
    leftover = [
        w for w in words
        if w.lower() not in FILLER_WORDS
        and not get_close_matches(w.lower(), filler, n=1, cutoff=0.75)
    ]
    return " ".join(leftover).strip()


def geocode(name: str):
    for query, lang in ((CITY_MAP.get(name, name), "fa"), (name, "fa"), (CITY_MAP.get(name, name), "en")):
        try:
            g_ = requests.get(
                "https://geocoding-api.open-meteo.com/v1/search",
                params={"name": query, "count": 1, "language": lang},
                timeout=15,
            ).json()
            if g_.get("results"):
                return g_["results"][0]
        except Exception:
            continue
    return None


def get_weather(city: str) -> str:
    if not city:
        return "اسم شهر رو هم بگو، مثلاً: «هوا تهران»"
    try:
        place = geocode(city)
        if not place:
            return f"شهر «{city}» پیدا نشد."
        w = requests.get(
            "https://api.open-meteo.com/v1/forecast",
            params={
                "latitude": place["latitude"],
                "longitude": place["longitude"],
                "current": "temperature_2m,relative_humidity_2m,wind_speed_10m,weather_code",
                "timezone": "auto",
            },
            timeout=15,
        ).json()["current"]
        desc = WEATHER_CODES.get(w["weather_code"], "نامشخص")
        return (
            f"آب‌وهوای {place['name']}:\n"
            f"وضعیت: {desc}\n"
            f"دما: {w['temperature_2m']}°C\n"
            f"رطوبت: {w['relative_humidity_2m']}%\n"
            f"باد: {w['wind_speed_10m']} km/h"
        )
    except Exception as e:
        log_error("get_weather", e)
        return SERVER_ERROR


def strip_triggers(text: str) -> str:
    t = text.strip().lstrip("/!")
    for w in TRIGGERS:
        t = re.sub(re.escape(w), " ", t, flags=re.IGNORECASE)
    return re.sub(r"\s+", " ", t.lstrip("/!")).strip()


def handle_command(clean: str):
    words = clean.lower().split()

    if not words or clean.lower() in ("start", "سلام", "salam", "hi", "hello"):
        return GREETING_TEXT, "greeting"

    normalized = re.sub(r"آب\s*و?\s*هوا", "هوا", clean)
    if any(w in WEATHER_WORDS for w in normalized.lower().split()):
        return get_weather(extract_city(clean)), "weather"

    if len(words) <= 6 and any(w.startswith("ساعت") or w == "time" for w in words):
        return get_time(), "time"

    if len(words) <= 6 and (
        any(w in ("تاریخ", "تاریخش", "date") for w in words)
        or (any(w.startswith("امروز") for w in words) and any(w.startswith("چندم") for w in words))
        or any(w.startswith("چندمه") for w in words)
    ):
        return get_date(), "date"

    return None, None


def process_message(message: str, history=None, model_key: str = DEFAULT_MODEL):
    if model_key not in MODELS:
        model_key = DEFAULT_MODEL
    if model_key != DEFAULT_MODEL:
        return ask_gapgpt(message.strip(), history, model_key), "ai"
    clean = strip_triggers(normalize(message))
    if clean and IMAGE_INTENT.search(clean):
        return make_image(clean), "image"
    reply, kind = handle_command(clean)
    if reply is not None:
        return reply, kind
    return ask_gapgpt(clean, history, model_key), "ai"


def load_secret_key() -> str:
    env = os.environ.get("IROVAN_SECRET")
    if env:
        return env
    if os.path.exists(SECRET_PATH):
        with open(SECRET_PATH, "r", encoding="utf-8") as f:
            value = f.read().strip()
            if value:
                return value
    value = secrets.token_hex(32)
    with open(SECRET_PATH, "w", encoding="utf-8") as f:
        f.write(value)
    try:
        os.chmod(SECRET_PATH, 0o600)
    except Exception:
        pass
    return value


app = Flask(__name__)
app.secret_key = load_secret_key()
app.config["JSON_AS_ASCII"] = False
app.config["SESSION_COOKIE_HTTPONLY"] = True
app.config["SESSION_COOKIE_SAMESITE"] = "Lax"
app.config["SESSION_COOKIE_SECURE"] = USE_HTTPS
app.config["PERMANENT_SESSION_LIFETIME"] = 60 * 60 * 24 * 30
app.config["MAX_CONTENT_LENGTH"] = 256 * 1024
try:
    app.json.ensure_ascii = False
except Exception:
    pass


def init_db():
    conn = sqlite3.connect(DB_PATH)
    conn.executescript(
        """
        CREATE TABLE IF NOT EXISTS users (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            username TEXT UNIQUE NOT NULL,
            password_hash TEXT NOT NULL,
            created_at TEXT NOT NULL
        );
        CREATE TABLE IF NOT EXISTS conversations (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            user_id INTEGER NOT NULL REFERENCES users(id) ON DELETE CASCADE,
            title TEXT NOT NULL,
            created_at TEXT NOT NULL,
            updated_at TEXT NOT NULL
        );
        CREATE TABLE IF NOT EXISTS messages (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            conversation_id INTEGER NOT NULL REFERENCES conversations(id) ON DELETE CASCADE,
            role TEXT NOT NULL,
            content TEXT NOT NULL,
            kind TEXT,
            created_at TEXT NOT NULL
        );
        CREATE INDEX IF NOT EXISTS idx_conv_user ON conversations(user_id, updated_at);
        CREATE INDEX IF NOT EXISTS idx_msg_conv ON messages(conversation_id, id);
        """
    )
    conn.commit()
    conn.close()


init_db()


def db() -> sqlite3.Connection:
    if "db" not in g:
        conn = sqlite3.connect(DB_PATH, timeout=15)
        conn.row_factory = sqlite3.Row
        conn.execute("PRAGMA foreign_keys=ON")
        g.db = conn
    return g.db


@app.teardown_appcontext
def close_db(_exc):
    conn = g.pop("db", None)
    if conn is not None:
        conn.close()


def now_iso() -> str:
    return datetime.utcnow().isoformat(timespec="seconds")


HITS = {}


def throttle(key: str, limit: int, window: int) -> bool:
    now = time.time()
    recent = [t for t in HITS.get(key, []) if now - t < window]
    if len(recent) >= limit:
        HITS[key] = recent
        return False
    recent.append(now)
    HITS[key] = recent
    return True


def current_user():
    uid = session.get("uid")
    if not uid:
        return None
    return db().execute("SELECT id, username FROM users WHERE id=?", (uid,)).fetchone()


def api_error(message: str, status: int):
    return jsonify({"ok": False, "error": message}), status


def title_from(message: str) -> str:
    t = re.sub(r"\s+", " ", message).strip()
    return (t[:40] + "…") if len(t) > 40 else t


def api_token_ok() -> bool:
    if not API_TOKEN:
        return False
    header = request.headers.get("Authorization", "")
    token = header[7:] if header.lower().startswith("bearer ") else request.args.get("token", "")
    return secrets.compare_digest(token.encode(), API_TOKEN.encode())


@app.after_request
def add_headers(resp):
    resp.headers["X-Content-Type-Options"] = "nosniff"
    resp.headers["X-Frame-Options"] = "DENY"
    resp.headers["Referrer-Policy"] = "same-origin"
    if request.path.startswith("/api/"):
        resp.headers["Access-Control-Allow-Origin"] = "*"
        resp.headers["Access-Control-Allow-Headers"] = "Content-Type, Authorization"
        resp.headers["Access-Control-Allow-Methods"] = "GET, POST, OPTIONS"
    if resp.mimetype == "text/html":
        resp.headers["Cache-Control"] = "no-store"
    return resp


BASE_CSS = r"""
*{box-sizing:border-box;-webkit-tap-highlight-color:transparent}
:root{--bg:#070b10;--panel:#0f151b;--panel2:#151d25;--card:#18222b;--line:#233039;--text:#e9f1f7;--muted:#8fa2b0;--accent:#1a8cff;--accent2:#3fc1ff;--bubble:#123a72;--bubble-text:#dcecff;--danger:#f2586b;--code:#0a1015;--code-h:#121a21;--inline:#152028;--toast:#22303b;--toast-text:#e9f1f7;--btn:#1d2932;--btn-h:#26343f;--ph:#63737f;--hint:#55636e;--sb:#243039;--ov1:rgba(4,8,14,.82);--ov2:rgba(4,8,14,.9);--authcard:rgba(12,18,25,.72);--field:rgba(24,34,43,.85);--tabs:rgba(0,0,0,.35);--del-h:#2a3944;--focus:#2a5a94;--ease:cubic-bezier(.22,1,.36,1)}
:root[data-theme="light"]{--bg:#eef2f7;--panel:#ffffff;--panel2:#f0f4f8;--card:#e6edf4;--line:#d3dce6;--text:#0f1a24;--muted:#5a6b79;--accent:#1a8cff;--accent2:#0b6fd1;--bubble:#1a8cff;--bubble-text:#ffffff;--danger:#d9364a;--code:#f5f8fb;--code-h:#e8eef4;--inline:#e8eef4;--toast:#1d2932;--toast-text:#ffffff;--btn:#e1e8ef;--btn-h:#d3dde7;--ph:#8796a3;--hint:#7a8996;--sb:#c4cfda;--ov1:rgba(238,242,247,.84);--ov2:rgba(238,242,247,.93);--authcard:rgba(255,255,255,.82);--field:rgba(240,244,248,.95);--tabs:rgba(0,0,0,.07);--del-h:#d6dfe8;--focus:#7db5ee}
html,body{height:100%}
body{margin:0;background:var(--bg);color:var(--text);font-family:"Vazirmatn","Segoe UI",Tahoma,"Noto Sans Arabic",system-ui,sans-serif;font-size:16px;line-height:1.8;overflow:hidden;animation:pageIn .6s var(--ease)}
h1,h2,h3,.title{font-family:"Lalezar","Vazirmatn",system-ui,sans-serif;font-weight:400;letter-spacing:.3px}
button{font:inherit;color:inherit;background:none;border:0;cursor:pointer;padding:0}
a{color:var(--accent2)}
svg{display:block}
.logo{width:40px;height:40px;border-radius:12px;object-fit:cover}
.logo.sm{width:34px;height:34px;border-radius:10px}
.logo.round{border-radius:50%}
.icon-btn{width:42px;height:42px;border-radius:50%;display:inline-flex;align-items:center;justify-content:center;color:var(--muted);transition:background .25s var(--ease),color .25s var(--ease),transform .25s var(--ease);flex:none}
.icon-btn:hover{background:var(--panel2);color:var(--text)}
.icon-btn:active{transform:scale(.88)}
.icon-btn svg{width:22px;height:22px}
.brand{display:flex;align-items:center;gap:10px;direction:ltr;font-weight:600;letter-spacing:.2px}
.toast{position:fixed;inset-inline:0;bottom:calc(90px + env(safe-area-inset-bottom));margin:auto;width:max-content;max-width:88vw;background:var(--toast);color:var(--toast-text);padding:9px 18px;border-radius:14px;font-size:14px;opacity:0;pointer-events:none;transition:opacity .3s var(--ease),transform .3s var(--ease);transform:translateY(12px) scale(.96);z-index:80}
.toast.show{opacity:1;transform:none}
::-webkit-scrollbar{width:8px;height:8px}
::-webkit-scrollbar-thumb{background:var(--sb);border-radius:8px}
@keyframes pageIn{from{opacity:0;transform:translateY(10px)}to{opacity:1;transform:none}}
@keyframes pop{from{opacity:0;transform:translateY(10px) scale(.98)}to{opacity:1;transform:none}}
@media (prefers-reduced-motion:reduce){*{animation-duration:.01ms!important;transition-duration:.01ms!important}}
"""

COMMON_JS = r"""
const I18N={
fa:{
brand:"ایروان",tagline:"یک دستیار هوش مصنوعی که همیشه همراه شماست",login:"ورود",register:"ثبت‌نام",username:"نام کاربری",password:"رمز عبور",password2:"تکرار رمز عبور",create:"ساخت حساب",mismatch:"رمز عبور و تکرار آن یکسان نیستند.",
title_login:"ورود | ایروان",title_settings:"تنظیمات | ایروان",title_chat:"ایروان | irovan",
app_title:"آیروان",new_chat:"گفتگوی جدید",welcome_h:"هر چی می‌خوای بپرس، ایروان جوابتو میده",welcome_p:"ایروان همیشه همراه شماست",
chip_time:"ساعت چنده؟",chip_date:"تاریخ امروز",chip_weather:"آب و هوا",chip_code:"کمک در برنامه نویسی",chip_img:"ساخت عکس",
q_time:"ساعت چنده؟",q_date:"تاریخ امروز",q_weather:"هوا تهران",q_code:"بهم میتونی در برنامه نویسی کمک کنی؟",q_img:"یک عکس از یک روبات کوچک در حال حرکت در خیابان بساز",
pm_time:"ساعت",pm_date:"تاریخ",pm_weather:"هوا تهران",placeholder:"از آیروان بپرسید",hint:"ایروان ممکن است اشتباه کند؛ اطلاعات مهم را بررسی کنید.",
typing:"ایروان در حال پاسخ دادن است",copy:"کپی",copied:"کپی شد",copy_fail:"کپی انجام نشد",no_speech:"مرورگر شما از خواندن متن پشتیبانی نمی‌کند",
empty_list:"هنوز گفتگویی ندارید.",confirm_del:"این گفتگو حذف شود؟",menu:"منو",close:"بستن",send:"ارسال",tools:"ابزارها",message:"پیام",read:"خواندن",share:"اشتراک",
model_title:"انتخاب مدل",model_set:"مدل تغییر کرد",model_img:"دارای قابلیت تصویر سازی",
err_server:"مشکلی در سرورهای ایروان پیش آمده و نمی‌توانم پاسخ بدهم. لطفاً بعداً دوباره تلاش کنید.",expired:"نشست شما منقضی شده است.",
settings:"تنظیمات",back:"بازگشت",my_account:"حساب من",about:"درباره ما",pro:"پلن پرو",clear_all:"پاک کردن همه گفتگوها",logout:"خروج",
language:"زبان",theme:"تم",dark:"سیاه",light:"سفید",
about_text:"ایروان یک دستیار هوش مصنوعی ایرانی با پشتیبانی از زبان فارسی است که توسط تیم ایروان ساخته شده است.",
pro_text:"پلن پرو به‌زودی فعال می‌شود. با ما همراه باشید.",ok:"باشه",clear_confirm:"همه گفتگوهای شما حذف شود؟",cleared:"همه گفتگوها پاک شد",clear_fail:"حذف انجام نشد"
},
en:{
brand:"Irovan",tagline:"An AI assistant that is always with you",login:"Login",register:"Sign up",username:"Username",password:"Password",password2:"Repeat password",create:"Create account",mismatch:"Passwords do not match.",
title_login:"Login | Irovan",title_settings:"Settings | Irovan",title_chat:"Irovan | irovan",
app_title:"Irovan",new_chat:"New chat",welcome_h:"Ask anything, Irovan will answer",welcome_p:"Irovan is always with you",
chip_time:"What time is it?",chip_date:"Today date",chip_weather:"Weather",chip_code:"Coding help",chip_img:"Create image",
q_time:"What time is it?",q_date:"What is the date today",q_weather:"weather Tehran",q_code:"Can you help me with programming?",q_img:"Generate an image of a small robot walking down the street",
pm_time:"Time",pm_date:"Date",pm_weather:"Weather Tehran",placeholder:"Ask Irovan",hint:"Irovan can make mistakes; check important information.",
typing:"Irovan is replying",copy:"Copy",copied:"Copied",copy_fail:"Copy failed",no_speech:"Your browser does not support text to speech",
empty_list:"No conversations yet.",confirm_del:"Delete this conversation?",menu:"Menu",close:"Close",send:"Send",tools:"Tools",message:"Message",read:"Read aloud",share:"Share",
model_title:"Choose model",model_set:"Model changed",model_img:"Has image generation",
err_server:"There is a problem with Irovan servers and I cannot answer right now. Please try again later.",expired:"Your session has expired.",
settings:"Settings",back:"Back",my_account:"My account",about:"About us",pro:"Pro plan",clear_all:"Clear all conversations",logout:"Log out",
language:"Language",theme:"Theme",dark:"Dark",light:"Light",
about_text:"Irovan is an Iranian AI assistant with Persian language support, built by the Irovan team.",
pro_text:"The Pro plan will be available soon. Stay tuned.",ok:"OK",clear_confirm:"Delete all your conversations?",cleared:"All conversations cleared",clear_fail:"Could not delete"
}
};
function L(){try{return localStorage.getItem('irovan_lang')==='en'?'en':'fa';}catch(e){return 'fa';}}
function T(){try{return localStorage.getItem('irovan_theme')==='light'?'light':'dark';}catch(e){return 'dark';}}
function t(k){const d=I18N[L()];return d[k]!==undefined?d[k]:(I18N.fa[k]!==undefined?I18N.fa[k]:k);}
function applyTheme(){
  document.documentElement.setAttribute('data-theme',T());
  const m=document.querySelector('meta[name=theme-color]');
  if(m) m.content=T()==='light'?'#eef2f7':'#070b10';
}
function applyI18n(){
  const l=L(), d=document.documentElement;
  d.lang=l; d.dir=l==='fa'?'rtl':'ltr';
  document.querySelectorAll('[data-i]').forEach(e=>{e.textContent=t(e.dataset.i);});
  document.querySelectorAll('[data-ip]').forEach(e=>{e.placeholder=t(e.dataset.ip);});
  document.querySelectorAll('[data-ia]').forEach(e=>{e.setAttribute('aria-label',t(e.dataset.ia));});
  document.querySelectorAll('[data-iq]').forEach(e=>{e.dataset.q=t(e.dataset.iq);});
  const tk=document.body&&document.body.dataset.title;
  if(tk) document.title=t(tk);
}
applyTheme();
document.documentElement.lang=L();
document.documentElement.dir=L()==='fa'?'rtl':'ltr';
"""

PAGE = r"""<!doctype html>
<html lang="fa" dir="rtl" data-theme="dark">
<head>
<meta charset="utf-8">
<meta name="viewport" content="width=device-width, initial-scale=1, viewport-fit=cover">
<meta name="theme-color" content="#070b10">
<meta name="mobile-web-app-capable" content="yes">
<meta name="apple-mobile-web-app-capable" content="yes">
<link rel="manifest" href="/manifest.webmanifest">
<link rel="icon" href="/logo?v=3">
<link rel="apple-touch-icon" href="/logo?v=3">
<link rel="preconnect" href="https://fonts.googleapis.com">
<link rel="preconnect" href="https://fonts.gstatic.com" crossorigin>
<link rel="stylesheet" href="https://cdn.jsdelivr.net/gh/rastikerdar/vazirmatn@v33.003/Vazirmatn-font-face.css">
<link rel="stylesheet" href="https://fonts.googleapis.com/css2?family=Lalezar&display=swap">
<title>__TITLE__</title>
<style>__CSS__</style>
<script>__COMMON__</script>
</head>
<body data-title="__TK__">
__BODY__
</body>
</html>"""


def render(title: str, body: str, css: str = "", tk: str = "") -> Response:
    page = (
        PAGE.replace("__TITLE__", title)
        .replace("__TK__", tk)
        .replace("__CSS__", BASE_CSS + css)
        .replace("__COMMON__", COMMON_JS)
        .replace("__BODY__", body)
    )
    return Response(page, mimetype="text/html")


AUTH_CSS = r"""
body{display:flex;align-items:center;justify-content:center;padding:20px;overflow:auto;background:linear-gradient(180deg,var(--ov1),var(--ov2)),url(/bg?v=3) center/cover fixed no-repeat,var(--bg)}
.card{width:100%;max-width:410px;background:var(--authcard);backdrop-filter:blur(18px);-webkit-backdrop-filter:blur(18px);border:1px solid rgba(120,190,255,.16);border-radius:30px;padding:30px 24px;box-shadow:0 30px 90px rgba(0,0,0,.35);animation:pop .7s var(--ease)}
.head{text-align:center;margin-bottom:20px}
.head .logo{width:92px;height:92px;border-radius:0;box-shadow:none;animation:none;object-fit:contain;margin:0 auto 12px}
.head h1{margin:0;font-size:30px}
.head p{margin:6px 0 0;color:var(--muted);font-size:14px}
.tabs{position:relative;display:flex;background:var(--tabs);border-radius:16px;padding:4px;margin-bottom:18px}
.tabs .pill{position:absolute;top:4px;bottom:4px;width:calc(50% - 4px);border-radius:12px;background:var(--card);inset-inline-start:4px;transition:transform .45s var(--ease)}
.tabs.reg .pill{transform:translateX(-100%)}
html[dir="ltr"] .tabs.reg .pill{transform:translateX(100%)}
.tab{flex:1;padding:9px;border-radius:12px;color:var(--muted);font-size:15px;position:relative;z-index:1;transition:color .3s var(--ease)}
.tab.on{color:var(--text)}
.field{margin-bottom:12px}
.field label{display:block;font-size:13px;color:var(--muted);margin-bottom:4px}
.field input{width:100%;background:var(--field);border:1px solid transparent;border-radius:14px;padding:12px 14px;color:var(--text);font:inherit;outline:none;direction:ltr;text-align:left;transition:border .25s var(--ease),box-shadow .25s var(--ease)}
.field input:focus{border-color:var(--accent);box-shadow:0 0 0 4px rgba(26,140,255,.15)}
.collapse{display:grid;grid-template-rows:0fr;opacity:0;transition:grid-template-rows .5s var(--ease),opacity .4s var(--ease)}
.collapse>div{overflow:hidden;min-height:0}
.collapse.open{grid-template-rows:1fr;opacity:1}
.err{min-height:22px;color:var(--danger);font-size:14px;margin:2px 0 8px;text-align:center;transition:opacity .3s}
.go{width:100%;background:linear-gradient(135deg,#1a8cff,#12b5ff);color:#fff;border-radius:16px;padding:13px;font-weight:600;font-size:16px;transition:filter .25s,transform .25s var(--ease),box-shadow .25s}
.go:hover{filter:brightness(1.1);box-shadow:0 10px 30px rgba(26,140,255,.35)}
.go:active{transform:scale(.97)}
.go:disabled{opacity:.6;cursor:default}
.foot{margin-top:16px;text-align:center;color:var(--muted);font-size:13px}
"""

AUTH_BODY = r"""
<main class="card">
  <div class="head">
    <img class="logo" src="/logo?v=3" alt="irovan">
    <h1 data-i="brand"></h1>
    <p data-i="tagline"></p>
  </div>
  <div class="tabs" id="tabs">
    <span class="pill"></span>
    <button class="tab on" data-mode="login" data-i="login" type="button"></button>
    <button class="tab" data-mode="register" data-i="register" type="button" __REG__></button>
  </div>
  <form id="form" autocomplete="on">
    <div class="field"><label for="u" data-i="username"></label><input id="u" name="username" autocomplete="username" autocapitalize="off" spellcheck="false" placeholder="irovan" required></div>
    <div class="field"><label for="p" data-i="password"></label><input id="p" name="password" type="password" autocomplete="current-password" placeholder="••••••••" required></div>
    <div class="collapse" id="p2box"><div><div class="field"><label for="p2" data-i="password2"></label><input id="p2" type="password" autocomplete="new-password" placeholder="••••••••"></div></div></div>
    <div class="err" id="err"></div>
    <button class="go" id="go" type="submit"></button>
  </form>
  <div class="foot"> <a href="https://irovan.ir" target="_blank" rel="noopener">irovan.ir</a></div>
</main>
<script>
let mode='login';
const $=s=>document.querySelector(s);
const tabs=document.querySelectorAll('.tab');
function setMode(m){
  mode=m;
  tabs.forEach(b=>b.classList.toggle('on',b.dataset.mode===m));
  $('#tabs').classList.toggle('reg',m==='register');
  $('#p2box').classList.toggle('open',m==='register');
  $('#go').textContent=m==='login'?t('login'):t('create');
  $('#p').autocomplete=m==='login'?'current-password':'new-password';
  $('#err').textContent='';
}
tabs.forEach(b=>b.addEventListener('click',()=>{ if(!b.disabled) setMode(b.dataset.mode); }));
$('#form').addEventListener('submit',async e=>{
  e.preventDefault();
  const err=$('#err'), btn=$('#go');
  err.textContent='';
  if(mode==='register' && $('#p').value!==$('#p2').value){ err.textContent=t('mismatch'); return; }
  btn.disabled=true;
  try{
    const r=await fetch('/web/'+mode,{method:'POST',credentials:'same-origin',headers:{'Content-Type':'application/json'},body:JSON.stringify({username:$('#u').value,password:$('#p').value})});
    let d={}; try{ d=await r.json(); }catch(x){}
    if(!r.ok||!d.ok) throw new Error(d.error||t('err_server'));
    document.body.style.transition='opacity .35s';
    document.body.style.opacity='0';
    setTimeout(()=>{location.href='/';},300);
    return;
  }catch(x){ err.textContent=(x instanceof TypeError)?t('err_server'):x.message; }
  btn.disabled=false;
});
applyI18n();
setMode('login');
</script>
"""

CHAT_CSS = r"""
.app{display:flex;height:100dvh}
.sidebar{width:300px;flex:none;background:var(--panel);border-inline-end:1px solid var(--line);display:flex;flex-direction:column;padding:14px 12px calc(14px + env(safe-area-inset-bottom));transition:transform .5s var(--ease),margin .5s var(--ease),opacity .4s var(--ease);z-index:50}
.sb-head{display:flex;align-items:center;justify-content:space-between;padding:2px 4px 12px}
.new-chat{display:flex;align-items:center;gap:10px;justify-content:center;background:linear-gradient(135deg,#1a8cff,#12b5ff);color:#fff;border-radius:16px;padding:11px;font-weight:600;margin-bottom:12px;transition:filter .25s,transform .25s var(--ease)}
.new-chat:hover{filter:brightness(1.12)}
.new-chat:active{transform:scale(.97)}
.new-chat svg{width:20px;height:20px}
.conv-list{flex:1;overflow-y:auto;margin:0 -4px;padding:0 4px}
.conv{display:flex;align-items:center;gap:6px;padding:9px 12px;border-radius:14px;color:var(--text);cursor:pointer;font-size:15px;transition:background .25s var(--ease),transform .4s var(--ease),opacity .4s var(--ease),max-height .4s var(--ease);animation:pop .45s var(--ease) backwards;max-height:60px}
.conv.leaving{opacity:0;transform:translateX(30px);max-height:0;padding-block:0;overflow:hidden}
.conv:hover{background:var(--panel2)}
.conv.on{background:var(--card)}
.conv span{flex:1;overflow:hidden;text-overflow:ellipsis;white-space:nowrap}
.conv .del{opacity:0;width:28px;height:28px;border-radius:50%;display:flex;align-items:center;justify-content:center;color:var(--muted);transition:opacity .25s,background .25s,color .25s}
.conv:hover .del,.conv.on .del{opacity:1}
.conv .del:hover{background:var(--del-h);color:var(--danger)}
.conv .del svg{width:16px;height:16px}
.empty-list{color:var(--muted);text-align:center;font-size:14px;padding:26px 8px}
.user-chip{display:flex;align-items:center;gap:10px;padding:10px 12px;border-radius:16px;background:var(--panel2);text-decoration:none;color:var(--text);margin-top:10px;transition:background .25s var(--ease),transform .25s var(--ease)}
.user-chip:hover{background:var(--card)}
.user-chip:active{transform:scale(.97)}
.user-chip .logo{width:34px;height:34px}
.user-chip .uname{flex:1;direction:ltr;text-align:right;color:var(--accent2);font-size:15px}
.user-chip svg{width:20px;height:20px;color:var(--muted);transition:transform .6s var(--ease)}
.user-chip:hover svg{transform:rotate(90deg)}
.scrim{display:block;position:fixed;inset:0;background:rgba(0,0,0,.6);opacity:0;pointer-events:none;transition:opacity .4s var(--ease);z-index:40}
.scrim.show{opacity:1;pointer-events:auto}
.main{flex:1;display:flex;flex-direction:column;min-width:0;height:100dvh}
.top{display:flex;align-items:center;justify-content:space-between;margin:12px 14px 4px;padding:8px 12px;background:var(--panel);border-radius:22px;border:1px solid var(--line)}
.top-start{display:flex;align-items:center;gap:10px}
.top .title{font-size:20px}
.chat{flex:1;overflow-y:auto;padding:16px 14px 8px;position:relative;scroll-behavior:smooth}
.thread{max-width:820px;margin:0 auto;display:flex;flex-direction:column;gap:20px;padding-bottom:12px}
.msg.user{align-self:flex-start;max-width:82%;background:var(--bubble);color:var(--bubble-text);padding:9px 17px;border-radius:20px 20px 5px 20px;white-space:pre-wrap;word-break:break-word;animation:pop .4s var(--ease)}
html[dir="ltr"] .msg.user{align-self:flex-end}
.msg.bot{align-self:stretch;display:flex;gap:10px;align-items:flex-start;animation:pop .4s var(--ease)}
.msg.bot>.logo{width:30px;height:30px;border-radius:9px;margin-top:2px}
.bot-body{max-width:92%;word-break:break-word;min-width:0}
.bot-text{white-space:normal}
.bot-text h4{margin:10px 0 4px;font-size:17px}
.bot-text ul,.bot-text ol{margin:6px 0;padding-inline-start:24px}
.bot-text code{background:var(--inline);padding:1px 6px;border-radius:7px;font-size:.92em;direction:ltr;unicode-bidi:embed}
.gen{display:block;max-width:min(100%,420px);border-radius:16px;margin-top:8px;border:1px solid var(--line)}
.code{margin:10px 0;background:var(--code);border:1px solid var(--line);border-radius:14px;overflow:hidden;direction:ltr;text-align:left}
.code-h{display:flex;justify-content:space-between;align-items:center;padding:6px 12px;background:var(--code-h);color:var(--muted);font-size:13px}
.code-h button{color:var(--accent2);font-size:13px}
.code pre{margin:0;padding:12px 14px;overflow-x:auto;font-size:14px;line-height:1.6}
.code code{background:none;padding:0;font-family:ui-monospace,Consolas,Menlo,monospace}
.acts{display:flex;gap:2px;margin-top:2px;opacity:0;transition:opacity .4s var(--ease);pointer-events:none}
.msg.bot.ready .acts{opacity:.85;pointer-events:auto}
.acts .icon-btn{width:34px;height:34px}
.acts .icon-btn svg{width:18px;height:18px}
.typing{display:flex;align-items:center;gap:4px;color:var(--muted)}
.typing i{width:6px;height:6px;border-radius:50%;background:var(--accent2);animation:blink 1.2s infinite}
.typing i:nth-child(3){animation-delay:.2s}
.typing i:nth-child(4){animation-delay:.4s}
.typing span{margin-inline-end:6px}
.msg.err .bot-text{color:var(--danger)}
.welcome{position:absolute;inset:0;display:flex;flex-direction:column;align-items:center;justify-content:center;text-align:center;padding:20px;pointer-events:none;transition:opacity .5s var(--ease),transform .5s var(--ease),visibility .5s}
.welcome>*{pointer-events:auto}
.welcome.gone{opacity:0;transform:scale(.94) translateY(-10px);visibility:hidden}
.welcome.gone>*{pointer-events:none}
.welcome .logo{width:110px;height:110px;border-radius:0;box-shadow:none;animation:none;object-fit:contain;margin-bottom:16px}
.welcome h2{margin:0 0 6px;font-size:30px;max-width:520px}
.welcome p{margin:0 0 20px;color:var(--muted);font-size:15px}
.chips{display:flex;flex-wrap:wrap;gap:8px;justify-content:center;max-width:560px}
.chip{display:inline-flex;align-items:center;gap:8px;background:var(--panel);border:1px solid var(--line);border-radius:999px;padding:8px 16px;font-size:14px;transition:border-color .25s,background .25s,transform .3s var(--ease);animation:pop .6s var(--ease) backwards}
.chip:nth-child(2){animation-delay:.06s}
.chip:nth-child(3){animation-delay:.12s}
.chip:nth-child(4){animation-delay:.18s}
.chip:nth-child(5){animation-delay:.24s}
.chip:hover{border-color:var(--accent2);background:var(--panel2);transform:translateY(-2px)}
.chip:active{transform:scale(.95)}
.chip svg{width:16px;height:16px;color:var(--accent2)}
.composer{padding:6px 14px calc(10px + env(safe-area-inset-bottom));position:relative}
.bar{max-width:820px;margin:0 auto;background:var(--panel);border:1px solid var(--line);border-radius:28px;display:flex;align-items:flex-end;gap:6px;padding:7px 8px;transition:border-color .3s var(--ease),box-shadow .3s var(--ease)}
html[dir="ltr"] .bar{flex-direction:row-reverse}
.bar:focus-within{border-color:var(--focus);box-shadow:0 0 0 4px rgba(26,140,255,.1)}
.bar textarea{flex:1;background:none;border:0;outline:none;resize:none;color:var(--text);font:inherit;line-height:1.7;max-height:160px;padding:7px 8px;min-height:26px}
.bar textarea::placeholder{color:var(--ph)}
.send{width:44px;height:44px;border-radius:50%;background:linear-gradient(135deg,#1a8cff,#12b5ff);color:#fff;display:flex;align-items:center;justify-content:center;flex:none;transition:filter .25s,opacity .3s,transform .3s var(--ease)}
.send svg{width:22px;height:22px}
.send:disabled{opacity:.35;cursor:default;transform:scale(.9)}
.send:not(:disabled):hover{filter:brightness(1.15)}
.send:not(:disabled):active{transform:scale(.9)}
.hint{max-width:820px;margin:6px auto 0;text-align:center;color:var(--hint);font-size:12px}
.plus-menu{position:absolute;bottom:calc(100% - 2px);inset-inline:14px;max-width:820px;margin:0 auto;background:var(--panel);border:1px solid var(--line);border-radius:20px;padding:12px;display:flex;flex-wrap:wrap;gap:8px;box-shadow:0 18px 50px rgba(0,0,0,.35);opacity:0;visibility:hidden;transform:translateY(14px) scale(.97);transform-origin:bottom center;transition:opacity .35s var(--ease),transform .45s var(--ease),visibility .35s}
.plus-menu.open{opacity:1;visibility:visible;transform:none}
.pm-title{width:100%;color:var(--muted);font-size:13px;padding:0 6px}
.models{width:100%;display:flex;gap:8px}
.model-opt{flex:1;display:flex;flex-direction:column;align-items:center;justify-content:center;gap:0;padding:8px 10px;line-height:1.5;border-radius:14px;border:1px solid var(--line);background:var(--panel2);font-size:14px;transition:border-color .25s,background .25s,color .25s,transform .3s var(--ease)}
.model-opt small{color:var(--muted);font-size:12px}
.model-opt:hover{border-color:var(--accent2)}
.model-opt:active{transform:scale(.97)}
.model-opt.on{border-color:var(--accent2);background:var(--card);color:var(--accent2)}
.pm-sep{width:100%;height:1px;background:var(--line);margin:2px 0}
#plus svg{transition:transform .45s var(--ease)}
#plus.open svg{transform:rotate(135deg)}
@keyframes blink{0%,80%,100%{opacity:.25;transform:scale(.8)}40%{opacity:1;transform:scale(1.1)}}
.sb-hidden .sidebar{margin-inline-start:-300px;opacity:0;pointer-events:none}
@media (max-width:860px){
  .sidebar{position:fixed;inset-block:0;inset-inline-start:0;width:min(86vw,320px);transform:translateX(100%);margin:0!important;opacity:1!important;pointer-events:auto!important;box-shadow:-20px 0 60px rgba(0,0,0,.4)}
  .sidebar.open{transform:none}
  html[dir="ltr"] .sidebar{transform:translateX(-100%);box-shadow:20px 0 60px rgba(0,0,0,.4)}
  html[dir="ltr"] .sidebar.open{transform:none}
  .msg.user{max-width:88%}
  .bot-body{max-width:100%}
  .top{margin:calc(8px + env(safe-area-inset-top)) 10px 2px}
  .chat{padding:12px 12px 6px}
  .composer{padding:6px 10px calc(8px + env(safe-area-inset-bottom))}
  .hint{display:none}
  .welcome h2{font-size:25px}
}
"""

ICON_MENU = '<svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round"><path d="M4 8h16M4 16h10"/></svg>'
ICON_PLUS = '<svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round"><path d="M12 5v14M5 12h14"/></svg>'
ICON_SEND = '<svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2.4" stroke-linecap="round" stroke-linejoin="round"><path d="M12 19V5M5 12l7-7 7 7"/></svg>'
ICON_CLOSE = '<svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round"><path d="M6 6l12 12M18 6L6 18"/></svg>'
ICON_GEAR = '<svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="1.8" stroke-linecap="round" stroke-linejoin="round"><circle cx="12" cy="12" r="3"/><path d="M19.4 15a1.7 1.7 0 0 0 .3 1.8l.1.1a2 2 0 1 1-2.8 2.8l-.1-.1a1.7 1.7 0 0 0-1.8-.3 1.7 1.7 0 0 0-1 1.5V21a2 2 0 1 1-4 0v-.1a1.7 1.7 0 0 0-1.1-1.5 1.7 1.7 0 0 0-1.8.3l-.1.1a2 2 0 1 1-2.8-2.8l.1-.1a1.7 1.7 0 0 0 .3-1.8 1.7 1.7 0 0 0-1.5-1H3a2 2 0 1 1 0-4h.1a1.7 1.7 0 0 0 1.5-1.1 1.7 1.7 0 0 0-.3-1.8l-.1-.1a2 2 0 1 1 2.8-2.8l.1.1a1.7 1.7 0 0 0 1.8.3H9a1.7 1.7 0 0 0 1-1.5V3a2 2 0 1 1 4 0v.1a1.7 1.7 0 0 0 1 1.5 1.7 1.7 0 0 0 1.8-.3l.1-.1a2 2 0 1 1 2.8 2.8l-.1.1a1.7 1.7 0 0 0-.3 1.8V9a1.7 1.7 0 0 0 1.5 1H21a2 2 0 1 1 0 4h-.1a1.7 1.7 0 0 0-1.5 1z"/></svg>'
ICON_CLOCK = '<svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round"><circle cx="12" cy="12" r="9"/><path d="M12 7v5l3 2"/></svg>'
ICON_CAL = '<svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round"><rect x="4" y="5" width="16" height="15" rx="3"/><path d="M4 10h16M9 3v4M15 3v4"/></svg>'
ICON_CLOUD = '<svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round"><path d="M7 18a4 4 0 0 1-.6-7.9A5.5 5.5 0 0 1 17 9.5a4 4 0 0 1 .5 8.5z"/></svg>'
ICON_CODE = '<svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round"><path d="M8 7l-5 5 5 5M16 7l5 5-5 5M14 4l-4 16"/></svg>'
ICON_IMG = '<svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round"><rect x="3.5" y="4.5" width="17" height="15" rx="3"/><circle cx="9" cy="10" r="1.6"/><path d="M4 17l5-5 4 4 3-3 4 4"/></svg>'
ICON_SPARK = '<svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linejoin="round"><path d="M12 3c.7 5 2.8 7.3 9 9-6.2 1.7-8.3 4-9 9-.7-5-2.8-7.3-9-9 6.2-1.7 8.3-4 9-9z"/></svg>'

CHAT_BODY = r"""
<div class="app" id="app">
  <div class="scrim" id="scrim"></div>
  <aside class="sidebar" id="sidebar">
    <div class="sb-head">
      <div class="brand"><img class="logo sm" src="/logo?v=3" alt=""><span>irovan</span></div>
      <button class="icon-btn" id="closeSb" data-ia="close" type="button">__CLOSE__</button>
    </div>
    <button class="new-chat" id="newChat" type="button">__PLUS__<span data-i="new_chat"></span></button>
    <div class="conv-list" id="convList"></div>
    <a class="user-chip" href="/settings">
      <img class="logo round" src="/logo?v=3" alt="">
      <span class="uname">@__USER__</span>
      __GEAR__
    </a>
  </aside>
  <main class="main">
    <header class="top">
      <div class="top-start">
        <button class="icon-btn" id="menuBtn" data-ia="menu" type="button">__MENU__</button>
        <span class="title" data-i="app_title"></span>
      </div>
      <div class="brand"><img class="logo sm" src="/logo?v=3" alt=""><span>irovan</span></div>
    </header>
    <section class="chat" id="chat">
      <div class="thread" id="thread"></div>
      <div class="welcome" id="welcome">
        <img class="logo" src="/logo?v=3" alt="">
        <h2 data-i="welcome_h"></h2>
        <p data-i="welcome_p"></p>
        <div class="chips">
          <button class="chip" data-iq="q_time" type="button">__I_CLOCK__<span data-i="chip_time"></span></button>
          <button class="chip" data-iq="q_date" type="button">__I_CAL__<span data-i="chip_date"></span></button>
          <button class="chip" data-iq="q_weather" type="button">__I_CLOUD__<span data-i="chip_weather"></span></button>
          <button class="chip" data-iq="q_img" type="button">__I_IMG__<span data-i="chip_img"></span></button>
          <button class="chip" data-iq="q_code" type="button">__I_CODE__<span data-i="chip_code"></span></button>
        </div>
      </div>
    </section>
    <footer class="composer">
      <div class="plus-menu" id="plusMenu">
        <div class="pm-title" data-i="model_title"></div>
        <div class="models">
          <button class="model-opt" data-model="slim" type="button">__M1__</button>
          <button class="model-opt" data-model="plus" type="button">__M2__</button>
        </div>
        <div class="pm-sep"></div>
        <button class="chip" data-iq="q_time" type="button">__I_CLOCK__<span data-i="pm_time"></span></button>
        <button class="chip" data-iq="q_date" type="button">__I_CAL__<span data-i="pm_date"></span></button>
        <button class="chip" data-iq="q_weather" type="button">__I_CLOUD__<span data-i="pm_weather"></span></button>
        <button class="chip" id="plusNew" type="button">__I_SPARK__<span data-i="new_chat"></span></button>
      </div>
      <div class="bar">
        <button class="send" id="send" data-ia="send" type="button" disabled>__SEND__</button>
        <textarea id="input" rows="1" data-ip="placeholder" data-ia="message" maxlength="4000"></textarea>
        <button class="icon-btn" id="plus" data-ia="tools" type="button">__PLUS__</button>
      </div>
      <div class="hint" data-i="hint"></div>
    </footer>
  </main>
</div>
<div class="toast" id="toast"></div>
<script>
const $=s=>document.querySelector(s);
const thread=$('#thread'), chat=$('#chat'), input=$('#input'), sendBtn=$('#send'), welcome=$('#welcome');
const ICONS={
  copy:'<svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="1.8" stroke-linecap="round" stroke-linejoin="round"><rect x="9" y="9" width="11" height="11" rx="2.5"/><path d="M5 15V6a2 2 0 0 1 2-2h9"/></svg>',
  speak:'<svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="1.8" stroke-linecap="round" stroke-linejoin="round"><path d="M4 10v4h4l5 4V6l-5 4z"/><path d="M16.5 8.5a5 5 0 0 1 0 7M19 6a8.5 8.5 0 0 1 0 12"/></svg>',
  share:'<svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="1.8" stroke-linecap="round" stroke-linejoin="round"><circle cx="18" cy="5" r="2.6"/><circle cx="6" cy="12" r="2.6"/><circle cx="18" cy="19" r="2.6"/><path d="M8.3 10.8l7.4-4.4M8.3 13.2l7.4 4.4"/></svg>',
  del:'<svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="1.8" stroke-linecap="round" stroke-linejoin="round"><path d="M4 7h16M10 11v6M14 11v6M6 7l1 12a2 2 0 0 0 2 2h6a2 2 0 0 0 2-2l1-12M9 7V4h6v3"/></svg>'
};
let convId=null, busy=false, toastTimer=null, model='slim';
try{ const sm=localStorage.getItem('irovan_model'); if(sm==='slim'||sm==='plus') model=sm; }catch(e){}

function esc(s){return s.replace(/&/g,'&amp;').replace(/</g,'&lt;').replace(/>/g,'&gt;');}
function md(src){
  const blocks=[], imgs=[];
  let s=src.replace(/```([\w+-]*)\n?([\s\S]*?)```/g,(m,l,c)=>{blocks.push([l,c]);return '@@B'+(blocks.length-1)+'@@';});
  s=s.replace(/!\[([^\]]*)\]\((https?:\/\/[^)\s]+)\)/g,(m,a,u)=>{imgs.push(u);return '@@I'+(imgs.length-1)+'@@';});
  let r=esc(s);
  r=r.replace(/`([^`\n]+)`/g,'<code>$1</code>');
  r=r.replace(/\*\*([^*\n]+)\*\*/g,'<b>$1</b>');
  r=r.replace(/^#{1,3} +(.+)$/gm,'<h4>$1</h4>');
  r=r.replace(/^(?:[-*•] +.+(?:\n|$))+/gm,m=>'<ul>'+m.trim().split('\n').map(x=>'<li>'+x.replace(/^[-*•] +/,'')+'</li>').join('')+'</ul>');
  r=r.replace(/^(?:\d+[.)] +.+(?:\n|$))+/gm,m=>'<ol>'+m.trim().split('\n').map(x=>'<li>'+x.replace(/^\d+[.)] +/,'')+'</li>').join('')+'</ol>');
  r=r.replace(/(https?:\/\/[^\s<]+)/g,'<a href="$1" target="_blank" rel="noopener">$1</a>');
  r=r.replace(/\n/g,'<br>').replace(/<br>(<\/?(?:ul|ol|h4))/g,'$1').replace(/(<\/(?:ul|ol|h4)>)<br>/g,'$1');
  r=r.replace(/@@I(\d+)@@/g,(m,i)=>{
    const u=esc(imgs[+i]||'').replace(/"/g,'&quot;');
    return '<a href="'+u+'" target="_blank" rel="noopener"><img class="gen" src="'+u+'" alt="" loading="lazy"></a>';
  });
  r=r.replace(/@@B(\d+)@@/g,(m,i)=>{
    const b=blocks[+i]||['',''];
    return '<div class="code"><div class="code-h"><span>'+esc(b[0]||'code')+'</span><button data-copy type="button">'+t('copy')+'</button></div><pre dir="ltr"><code>'+esc(b[1].replace(/^\n|\n$/g,''))+'</code></pre></div>';
  });
  r=r.replace(/<br>(<div class="code")/g,'$1').replace(/(<\/div>)<br>/g,'$1');
  return r;
}
function toast(msg){
  const el=$('#toast'); el.textContent=msg; el.classList.add('show');
  clearTimeout(toastTimer); toastTimer=setTimeout(()=>el.classList.remove('show'),1800);
}
function copyText(text){
  if(navigator.clipboard && window.isSecureContext){
    return navigator.clipboard.writeText(text).then(()=>toast(t('copied')),()=>fallbackCopy(text));
  }
  fallbackCopy(text);
}
function fallbackCopy(text){
  const ta=document.createElement('textarea'); ta.value=text; ta.style.cssText='position:fixed;opacity:0;top:0';
  document.body.appendChild(ta); ta.select();
  try{ document.execCommand('copy'); toast(t('copied')); }catch(e){ toast(t('copy_fail')); }
  ta.remove();
}
function scrollBottom(){ chat.scrollTop=chat.scrollHeight; }
function setWelcome(show){ welcome.classList.toggle('gone',!show); }
function autosize(){ input.style.height='auto'; input.style.height=Math.min(input.scrollHeight,160)+'px'; sendBtn.disabled=busy||!input.value.trim(); }

async function api(url,opts){
  let r;
  try{
    r=await fetch(url,Object.assign({credentials:'same-origin',headers:{'Content-Type':'application/json'}},opts||{}));
  }catch(e){ throw new Error(t('err_server')); }
  let d={}; try{ d=await r.json(); }catch(e){}
  if(r.status===401){ location.href='/login'; throw new Error(t('expired')); }
  if(!r.ok||d.ok===false) throw new Error(d.error||t('err_server'));
  return d;
}

function addUser(text){
  const el=document.createElement('div'); el.className='msg user'; el.textContent=text;
  thread.appendChild(el); scrollBottom();
}
function botShell(){
  const el=document.createElement('div'); el.className='msg bot';
  el.innerHTML='<img class="logo" src="/logo?v=3" alt=""><div class="bot-body"><div class="bot-text"></div><div class="acts">'
    +'<button class="icon-btn" data-act="copy" aria-label="'+t('copy')+'" type="button">'+ICONS.copy+'</button>'
    +'<button class="icon-btn" data-act="speak" aria-label="'+t('read')+'" type="button">'+ICONS.speak+'</button>'
    +'<button class="icon-btn" data-act="share" aria-label="'+t('share')+'" type="button">'+ICONS.share+'</button>'
    +'</div></div>';
  thread.appendChild(el); return el;
}
function addBot(text,animate,isErr){
  const el=botShell(); el.raw=text;
  if(isErr) el.classList.add('err');
  const body=el.querySelector('.bot-text');
  if(!animate||/!\[[^\]]*\]\(https?:/.test(text)){ body.innerHTML=md(text); el.classList.add('ready'); scrollBottom(); return el; }
  let i=0; const step=Math.max(2,Math.ceil(text.length/110));
  const tick=()=>{
    i=Math.min(text.length,i+step);
    let part=text.slice(0,i);
    if((part.match(/```/g)||[]).length%2) part+='\n```';
    body.innerHTML=md(part); scrollBottom();
    if(i<text.length) setTimeout(tick,18); else el.classList.add('ready');
  };
  tick(); return el;
}
function addTyping(){
  const el=document.createElement('div'); el.className='msg bot';
  el.innerHTML='<img class="logo" src="/logo?v=3" alt=""><div class="bot-body typing"><span>'+t('typing')+'</span><i></i><i></i><i></i></div>';
  thread.appendChild(el); scrollBottom(); return el;
}

async function send(text){
  text=(text!==undefined?text:input.value).trim();
  if(!text||busy) return;
  busy=true; setWelcome(false); closePlus();
  input.value=''; autosize(); addUser(text);
  const typing=addTyping();
  try{
    const d=await api('/web/send',{method:'POST',body:JSON.stringify({message:text,conversation_id:convId,model:model})});
    convId=d.conversation_id; typing.remove(); addBot(d.reply,true); loadList();
  }catch(e){
    typing.remove(); addBot(e.message,false,true);
  }finally{
    busy=false; autosize(); if(!matchMedia('(pointer:coarse)').matches) input.focus();
  }
}

function setModel(m){
  model=m;
  try{ localStorage.setItem('irovan_model',m); }catch(e){}
  document.querySelectorAll('.model-opt').forEach(b=>b.classList.toggle('on',b.dataset.model===m));
}

function newChat(){
  convId=null; thread.innerHTML=''; setWelcome(true); closeSidebar(); closePlus();
  document.querySelectorAll('.conv').forEach(c=>c.classList.remove('on'));
  input.focus();
}
async function openConv(id){
  try{
    const d=await api('/web/conversations/'+id);
    convId=id; thread.innerHTML=''; setWelcome(false);
    d.messages.forEach(m=>{ if(m.role==='user') addUser(m.content); else addBot(m.content,false); });
    scrollBottom(); markActive(); closeSidebar();
  }catch(e){ toast(e.message); }
}
function markActive(){
  document.querySelectorAll('.conv').forEach(c=>c.classList.toggle('on',+c.dataset.id===convId));
}
async function loadList(){
  try{
    const d=await api('/web/conversations');
    const box=$('#convList'); box.innerHTML='';
    if(!d.conversations.length){ box.innerHTML='<div class="empty-list">'+t('empty_list')+'</div>'; return d.conversations; }
    d.conversations.forEach((c,idx)=>{
      const row=document.createElement('div'); row.className='conv'; row.dataset.id=c.id;
      row.style.animationDelay=Math.min(idx*35,350)+'ms';
      row.innerHTML='<span></span><button class="del" type="button">'+ICONS.del+'</button>';
      row.querySelector('span').textContent=c.title;
      row.addEventListener('click',e=>{
        if(e.target.closest('.del')){ delConv(c.id,row); return; }
        openConv(c.id);
      });
      box.appendChild(row);
    });
    markActive();
    return d.conversations;
  }catch(e){ return []; }
}
async function delConv(id,row){
  if(!confirm(t('confirm_del'))) return;
  try{
    await api('/web/conversations/'+id,{method:'DELETE'});
    if(row) row.classList.add('leaving');
    if(id===convId) newChat();
    setTimeout(loadList,420);
  }catch(e){ toast(e.message); }
}

function isMobile(){ return matchMedia('(max-width:860px)').matches; }
function openSidebar(){ $('#sidebar').classList.add('open'); $('#scrim').classList.add('show'); }
function closeSidebar(){ $('#sidebar').classList.remove('open'); $('#scrim').classList.remove('show'); }
function closePlus(){ $('#plusMenu').classList.remove('open'); $('#plus').classList.remove('open'); }
function togglePlus(){ $('#plusMenu').classList.toggle('open'); $('#plus').classList.toggle('open'); }

$('#menuBtn').addEventListener('click',()=>{
  if(isMobile()) openSidebar(); else $('#app').classList.toggle('sb-hidden');
});
$('#closeSb').addEventListener('click',()=>{
  if(isMobile()) closeSidebar(); else $('#app').classList.add('sb-hidden');
});
$('#scrim').addEventListener('click',closeSidebar);
$('#newChat').addEventListener('click',newChat);
$('#plusNew').addEventListener('click',newChat);
$('#plus').addEventListener('click',e=>{ e.stopPropagation(); togglePlus(); });
document.addEventListener('click',e=>{ if(!e.target.closest('#plusMenu')&&!e.target.closest('#plus')) closePlus(); });
document.querySelectorAll('[data-iq]').forEach(b=>b.addEventListener('click',()=>send(b.dataset.q)));
document.querySelectorAll('.model-opt').forEach(b=>b.addEventListener('click',()=>{ setModel(b.dataset.model); toast(t('model_set')); }));
sendBtn.addEventListener('click',()=>send());
input.addEventListener('input',autosize);
input.addEventListener('keydown',e=>{
  if(e.key==='Enter'&&!e.shiftKey&&!e.isComposing&&!matchMedia('(pointer:coarse)').matches){ e.preventDefault(); send(); }
});

thread.addEventListener('click',e=>{
  const cb=e.target.closest('[data-copy]');
  if(cb){ copyText(cb.closest('.code').querySelector('code').textContent); return; }
  const btn=e.target.closest('[data-act]'); if(!btn) return;
  const msg=btn.closest('.msg.bot'); const text=msg.raw||msg.textContent;
  const act=btn.dataset.act;
  if(act==='copy') copyText(text);
  else if(act==='share'){
    if(navigator.share) navigator.share({text:text+'\n\nhttps://irovan.ir'}).catch(()=>{});
    else copyText(text);
  }else if(act==='speak'){
    if(!('speechSynthesis' in window)){ toast(t('no_speech')); return; }
    if(speechSynthesis.speaking){ speechSynthesis.cancel(); return; }
    const u=new SpeechSynthesisUtterance(text.replace(/```[\s\S]*?```/g,' ').replace(/!\[[^\]]*\]\([^)]*\)/g,' ')); u.lang=L()==='fa'?'fa-IR':'en-US'; speechSynthesis.speak(u);
  }
});

applyI18n();
setModel(model);
autosize();
loadList();
</script>
"""

SETTINGS_CSS = r"""
body{overflow:auto}
.wrap{max-width:560px;margin:0 auto;padding:calc(16px + env(safe-area-inset-top)) 16px calc(24px + env(safe-area-inset-bottom));min-height:100dvh;display:flex;flex-direction:column}
.bar{display:flex;align-items:center;justify-content:center;position:relative;min-height:48px;margin-bottom:12px}
.bar a{position:absolute;left:0;width:44px;height:44px;border-radius:50%;background:var(--btn);display:flex;align-items:center;justify-content:center;color:var(--text);text-decoration:none;transition:background .25s var(--ease),transform .3s var(--ease)}
.bar a:hover{background:var(--btn-h);transform:translateX(-3px)}
.bar a svg{width:22px;height:22px}
.bar h1{margin:0;font-size:24px}
.me{text-align:center;margin:8px 0 20px}
.me .logo{width:110px;height:110px;border-radius:0;box-shadow:none;animation:none;object-fit:contain}
.me div{margin-top:8px;font-weight:600;direction:ltr}
.label{color:var(--muted);font-size:16px;margin:10px 4px}
.card{background:var(--card);border-radius:18px;padding:14px 18px;margin-bottom:12px;animation:pop .5s var(--ease) backwards}
.card small{display:block;color:var(--muted);font-size:14px}
.card b{display:block;margin-top:6px;color:var(--accent2);direction:ltr;text-align:right;font-weight:500}
.group{display:flex;flex-direction:column;gap:3px;margin-bottom:12px;animation:pop .5s var(--ease) backwards}
.acc{background:var(--card);border-radius:6px;overflow:hidden}
.acc:first-child{border-radius:28px 28px 6px 6px}
.acc:last-child{border-radius:6px 6px 28px 28px}
.acc-h{display:flex;align-items:center;gap:18px;width:100%;padding:20px 22px;text-align:start;transition:background .25s var(--ease)}
.acc-h:hover{background:var(--btn-h)}
.acc-h>svg{width:26px;height:26px;flex:none;color:var(--text)}
.acc-t{flex:1;display:flex;flex-direction:column;min-width:0;line-height:1.6}
.acc-t b{font-weight:500;font-size:18px}
.acc-t small{color:var(--muted);font-size:15px}
.acc-h .chev{width:24px;height:24px;color:var(--text);transition:transform .45s var(--ease)}
.acc.open .chev{transform:rotate(180deg)}
.acc-b{display:grid;grid-template-rows:0fr;transition:grid-template-rows .45s var(--ease)}
.acc.open .acc-b{grid-template-rows:1fr}
.acc-b>div{overflow:hidden;min-height:0}
.opt{display:flex;align-items:center;gap:14px;width:100%;padding:13px 22px;color:var(--muted);font-size:16px;text-align:start;transition:background .25s var(--ease),color .25s var(--ease)}
.opt:hover{background:var(--btn-h)}
.opt i{width:18px;height:18px;border-radius:50%;border:2px solid var(--muted);flex:none;position:relative;transition:border-color .25s var(--ease)}
.opt i::after{content:"";position:absolute;inset:3px;border-radius:50%;background:var(--accent);transform:scale(0);transition:transform .3s var(--ease)}
.opt.on{color:var(--text)}
.opt.on i{border-color:var(--accent)}
.opt.on i::after{transform:scale(1)}
.opt:last-child{padding-bottom:18px}
.row{display:flex;align-items:center;gap:14px;width:100%;background:var(--card);border-radius:999px;padding:14px 20px;margin-bottom:10px;text-align:start;font-size:16px;transition:background .25s,transform .3s var(--ease);animation:pop .5s var(--ease) backwards}
.row:nth-of-type(1){animation-delay:.05s}
.row:nth-of-type(2){animation-delay:.1s}
.row:nth-of-type(3){animation-delay:.15s}
.row:hover{background:var(--btn-h);transform:translateX(-4px)}
.row:active{transform:scale(.98)}
.row svg{width:24px;height:24px;flex:none}
.row.pro{color:var(--accent2)}
.row.danger{color:var(--danger)}
.grow{flex:1}
.ver{text-align:center;color:var(--muted);font-size:14px;padding-top:26px;direction:ltr}
.modal{position:fixed;inset:0;background:rgba(0,0,0,.6);display:flex;align-items:center;justify-content:center;padding:20px;z-index:60;opacity:0;visibility:hidden;transition:opacity .4s var(--ease),visibility .4s;backdrop-filter:blur(0);-webkit-backdrop-filter:blur(0)}
.modal.show{opacity:1;visibility:visible;backdrop-filter:blur(6px);-webkit-backdrop-filter:blur(6px)}
.sheet{width:100%;max-width:420px;background:var(--panel);border:1px solid var(--line);border-radius:26px;padding:24px;text-align:center;transform:translateY(40px) scale(.94);opacity:0;transition:transform .55s var(--ease),opacity .4s var(--ease)}
.modal.show .sheet{transform:none;opacity:1}
.sheet .logo{width:64px;height:64px;border-radius:18px;margin:0 auto 10px}
.sheet h3{margin:0 0 10px;font-size:22px}
.sheet p{margin:0 0 18px;color:var(--muted);font-size:15px}
.sheet .ok{background:linear-gradient(135deg,#1a8cff,#12b5ff);color:#fff;border-radius:14px;padding:10px 26px;transition:transform .25s var(--ease),filter .25s}
.sheet .ok:hover{filter:brightness(1.12)}
.sheet .ok:active{transform:scale(.94)}
.toast{bottom:40px}
"""

SETTINGS_BODY = r"""
<div class="wrap">
  <div class="bar">
    <a href="/" data-ia="back"><svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2.2" stroke-linecap="round" stroke-linejoin="round"><path d="M19 12H5M12 5l-7 7 7 7"/></svg></a>
    <h1 data-i="settings"></h1>
  </div>
  <div class="me">
    <img class="logo" src="/logo?v=3" alt="">
    <div>__USER__</div>
  </div>
  <div class="label" data-i="my_account"></div>
  <div class="card"><small data-i="username"></small><b>@__USER__</b></div>
  <div class="group">
    <div class="acc" id="acc-lang">
      <button class="acc-h" type="button">
        <svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="1.8" stroke-linecap="round" stroke-linejoin="round"><circle cx="12" cy="12" r="9.5"/><path d="M2.5 12h19M12 2.5c2.6 2.8 4 6 4 9.5s-1.4 6.7-4 9.5c-2.6-2.8-4-6-4-9.5s1.4-6.7 4-9.5z"/></svg>
        <span class="acc-t"><b data-i="language"></b><small id="langVal"></small></span>
        <svg class="chev" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2.2" stroke-linecap="round" stroke-linejoin="round"><path d="M5 9l7 7 7-7"/></svg>
      </button>
      <div class="acc-b"><div>
        <button class="opt" data-lang="fa" type="button"><i></i><span>فارسی</span></button>
        <button class="opt" data-lang="en" type="button"><i></i><span>English</span></button>
      </div></div>
    </div>
    <div class="acc" id="acc-theme">
      <button class="acc-h" type="button">
        <svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="1.8" stroke-linecap="round" stroke-linejoin="round"><circle cx="12" cy="12" r="4"/><path d="M12 2.5v2.2M12 19.3v2.2M2.5 12h2.2M19.3 12h2.2M5.3 5.3l1.6 1.6M17.1 17.1l1.6 1.6M5.3 18.7l1.6-1.6M17.1 6.9l1.6-1.6"/></svg>
        <span class="acc-t"><b data-i="theme"></b><small id="themeVal"></small></span>
        <svg class="chev" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2.2" stroke-linecap="round" stroke-linejoin="round"><path d="M5 9l7 7 7-7"/></svg>
      </button>
      <div class="acc-b"><div>
        <button class="opt" data-th="dark" type="button"><i></i><span data-i="dark"></span></button>
        <button class="opt" data-th="light" type="button"><i></i><span data-i="light"></span></button>
      </div></div>
    </div>
  </div>
  <button class="row" data-m="about" type="button">
    <svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="1.8" stroke-linecap="round"><circle cx="12" cy="12" r="9.5"/><path d="M12 11v6"/><circle cx="12" cy="7.6" r=".6" fill="currentColor"/></svg>
    <span class="grow" data-i="about"></span>
  </button>
  <button class="row pro" data-m="pro" type="button">
    <svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="1.8" stroke-linejoin="round"><path d="M12 2.5c.7 5 2.8 7.3 9.5 9.5-6.7 2.2-8.8 4.5-9.5 9.5-.7-5-2.8-7.3-9.5-9.5 6.7-2.2 8.8-4.5 9.5-9.5z"/></svg>
    <span class="grow" data-i="pro"></span>
  </button>
  <button class="row" id="clearAll" type="button">
    <svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="1.8" stroke-linecap="round" stroke-linejoin="round"><path d="M4 7h16M10 11v6M14 11v6M6 7l1 12a2 2 0 0 0 2 2h6a2 2 0 0 0 2-2l1-12M9 7V4h6v3"/></svg>
    <span class="grow" data-i="clear_all"></span>
  </button>
  <div style="flex:1;min-height:40px"></div>
  <button class="row danger" id="logout" type="button">
    <svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="1.9" stroke-linecap="round" stroke-linejoin="round"><path d="M9 4H5a2 2 0 0 0-2 2v12a2 2 0 0 0 2 2h4M16 8l4 4-4 4M20 12H9"/></svg>
    <span class="grow" data-i="logout"></span>
  </button>
  <div class="ver">version __VERSION__</div>
</div>
<div class="modal" id="m-about"><div class="sheet"><img class="logo" src="/logo?v=3" alt=""><h3 data-i="about"></h3><p><span data-i="about_text"></span><br><a href="https://irovan.ir" target="_blank" rel="noopener">irovan.ir</a></p><button class="ok" data-close data-i="ok" type="button"></button></div></div>
<div class="modal" id="m-pro"><div class="sheet"><img class="logo" src="/logo?v=3" alt=""><h3 data-i="pro"></h3><p data-i="pro_text"></p><button class="ok" data-close data-i="ok" type="button"></button></div></div>
<div class="toast" id="toast"></div>
<script>
const $=s=>document.querySelector(s);
function mark(){
  document.querySelectorAll('[data-lang]').forEach(b=>b.classList.toggle('on',b.dataset.lang===L()));
  document.querySelectorAll('[data-th]').forEach(b=>b.classList.toggle('on',b.dataset.th===T()));
  $('#langVal').textContent=L()==='fa'?'فارسی':'English';
  $('#themeVal').textContent=t(T()==='dark'?'dark':'light');
}
document.querySelectorAll('.acc-h').forEach(h=>h.addEventListener('click',()=>{
  const acc=h.parentElement;
  const wasOpen=acc.classList.contains('open');
  document.querySelectorAll('.acc').forEach(a=>a.classList.remove('open'));
  if(!wasOpen) acc.classList.add('open');
}));
document.querySelectorAll('[data-lang]').forEach(b=>b.addEventListener('click',()=>{
  try{ localStorage.setItem('irovan_lang',b.dataset.lang); }catch(e){}
  applyI18n(); mark();
}));
document.querySelectorAll('[data-th]').forEach(b=>b.addEventListener('click',()=>{
  try{ localStorage.setItem('irovan_theme',b.dataset.th); }catch(e){}
  applyTheme(); mark();
}));
document.querySelectorAll('[data-m]').forEach(b=>b.addEventListener('click',()=>{ $('#m-'+b.dataset.m).classList.add('show'); }));
document.querySelectorAll('.modal').forEach(m=>m.addEventListener('click',e=>{ if(e.target===m||e.target.closest('[data-close]')) m.classList.remove('show'); }));
document.addEventListener('keydown',e=>{ if(e.key==='Escape') document.querySelectorAll('.modal.show').forEach(m=>m.classList.remove('show')); });
function toast(msg){ const el=$('#toast'); el.textContent=msg; el.classList.add('show'); setTimeout(()=>el.classList.remove('show'),1800); }
$('#logout').addEventListener('click',async()=>{
  try{ await fetch('/logout',{method:'POST',credentials:'same-origin',headers:{'Content-Type':'application/json'},body:'{}'}); }catch(e){}
  location.href='/login';
});
$('#clearAll').addEventListener('click',async()=>{
  if(!confirm(t('clear_confirm'))) return;
  try{
    const r=await fetch('/web/conversations',{method:'DELETE',credentials:'same-origin',headers:{'Content-Type':'application/json'}});
    if(!r.ok) throw new Error();
    toast(t('cleared'));
  }catch(e){ toast(t('clear_fail')); }
});
applyI18n();
mark();
</script>
"""


def chat_page(username: str) -> Response:
    body = (
        CHAT_BODY.replace("__USER__", html.escape(username))
        .replace("__CLOSE__", ICON_CLOSE)
        .replace("__PLUS__", ICON_PLUS)
        .replace("__MENU__", ICON_MENU)
        .replace("__SEND__", ICON_SEND)
        .replace("__GEAR__", ICON_GEAR)
        .replace("__I_CLOCK__", ICON_CLOCK)
        .replace("__I_CAL__", ICON_CAL)
        .replace("__I_CLOUD__", ICON_CLOUD)
        .replace("__I_CODE__", ICON_CODE)
        .replace("__I_IMG__", ICON_IMG)
        .replace("__I_SPARK__", ICON_SPARK)
        .replace("__M1__", '<b>ایروان اسلیم</b><small data-i="model_img"></small>')
        .replace("__M2__", "<b>gpt-4o mini</b>")
    )
    return render("ایروان | irovan", body, CHAT_CSS, "title_chat")


@app.route("/")
def index():
    user = current_user()
    if not user:
        return redirect("/login")
    return chat_page(user["username"])


@app.route("/login")
def login_page():
    if current_user():
        return redirect("/")
    body = AUTH_BODY.replace("__REG__", "" if ALLOW_REGISTER else "disabled hidden")
    return render("ورود | ایروان", body, AUTH_CSS, "title_login")


@app.route("/settings")
def settings_page():
    user = current_user()
    if not user:
        return redirect("/login")
    body = SETTINGS_BODY.replace("__USER__", html.escape(user["username"])).replace("__VERSION__", APP_VERSION)
    return render("تنظیمات | ایروان", body, SETTINGS_CSS, "title_settings")


@app.route("/logo")
def logo():
    if not LOGO_BYTES:
        return Response(status=404)
    return Response(LOGO_BYTES, mimetype="image/png", headers={"Cache-Control": "public, max-age=86400"})


@app.route("/bg")
def background():
    if not BG_BYTES:
        return Response(status=404)
    return Response(BG_BYTES, mimetype="image/jpeg", headers={"Cache-Control": "public, max-age=86400"})


@app.route("/manifest.webmanifest")
def manifest():
    data = {
        "name": "ایروان",
        "short_name": "irovan",
        "start_url": "/",
        "display": "standalone",
        "background_color": "#070b10",
        "theme_color": "#070b10",
        "lang": "fa",
        "dir": "rtl",
        "icons": [{"src": "/logo?v=3", "sizes": "512x512", "type": "image/png", "purpose": "any"}],
    }
    return Response(json.dumps(data, ensure_ascii=False), mimetype="application/manifest+json")


USERNAME_RE = re.compile(r"^[a-z0-9_]{3,20}$")


def read_credentials():
    data = request.get_json(silent=True) or {}
    username = str(data.get("username", "")).strip().lower()
    password = str(data.get("password", ""))
    return username, password


@app.route("/web/register", methods=["POST"])
def web_register():
    if not ALLOW_REGISTER:
        return api_error("ثبت‌نام غیرفعال است.", 403)
    if not throttle(f"reg:{request.remote_addr}", 5, 3600):
        return api_error("تعداد تلاش‌ها زیاد است؛ کمی بعد دوباره امتحان کنید.", 429)
    username, password = read_credentials()
    if not USERNAME_RE.match(username):
        return api_error("نام کاربری باید ۳ تا ۲۰ کاراکتر و فقط شامل حروف انگلیسی، عدد و _ باشد.", 400)
    if len(password) < 6 or len(password) > 128:
        return api_error("رمز عبور باید حداقل ۶ کاراکتر باشد.", 400)
    conn = db()
    if conn.execute("SELECT 1 FROM users WHERE username=?", (username,)).fetchone():
        return api_error("این نام کاربری قبلاً گرفته شده است.", 409)
    cur = conn.execute(
        "INSERT INTO users (username, password_hash, created_at) VALUES (?,?,?)",
        (username, generate_password_hash(password), now_iso()),
    )
    conn.commit()
    session.clear()
    session["uid"] = cur.lastrowid
    session.permanent = True
    return jsonify({"ok": True})


@app.route("/web/login", methods=["POST"])
def web_login():
    if not throttle(f"login:{request.remote_addr}", 10, 600):
        return api_error("تعداد تلاش‌ها زیاد است؛ چند دقیقه بعد دوباره امتحان کنید.", 429)
    username, password = read_credentials()
    row = db().execute("SELECT id, password_hash FROM users WHERE username=?", (username,)).fetchone()
    if not row or not check_password_hash(row["password_hash"], password):
        return api_error("نام کاربری یا رمز عبور اشتباه است.", 401)
    session.clear()
    session["uid"] = row["id"]
    session.permanent = True
    return jsonify({"ok": True})


@app.route("/logout", methods=["POST"])
def logout():
    session.clear()
    return jsonify({"ok": True})


@app.route("/web/conversations", methods=["GET"])
def list_conversations():
    user = current_user()
    if not user:
        return api_error("unauthorized", 401)
    rows = db().execute(
        "SELECT id, title FROM conversations WHERE user_id=? ORDER BY updated_at DESC, id DESC LIMIT 100",
        (user["id"],),
    ).fetchall()
    return jsonify({"ok": True, "conversations": [{"id": r["id"], "title": r["title"]} for r in rows]})


@app.route("/web/conversations", methods=["DELETE"])
def clear_conversations():
    user = current_user()
    if not user:
        return api_error("unauthorized", 401)
    conn = db()
    conn.execute("DELETE FROM conversations WHERE user_id=?", (user["id"],))
    conn.commit()
    return jsonify({"ok": True})


@app.route("/web/conversations/<int:cid>", methods=["GET"])
def get_conversation(cid):
    user = current_user()
    if not user:
        return api_error("unauthorized", 401)
    conn = db()
    conv = conn.execute("SELECT id, title FROM conversations WHERE id=? AND user_id=?", (cid, user["id"])).fetchone()
    if not conv:
        return api_error("گفتگو پیدا نشد.", 404)
    rows = conn.execute(
        "SELECT role, content, kind FROM messages WHERE conversation_id=? ORDER BY id ASC", (cid,)
    ).fetchall()
    return jsonify({
        "ok": True,
        "id": conv["id"],
        "title": conv["title"],
        "messages": [{"role": r["role"], "content": r["content"], "kind": r["kind"]} for r in rows],
    })


@app.route("/web/conversations/<int:cid>", methods=["DELETE"])
def delete_conversation(cid):
    user = current_user()
    if not user:
        return api_error("unauthorized", 401)
    conn = db()
    conn.execute("DELETE FROM conversations WHERE id=? AND user_id=?", (cid, user["id"]))
    conn.commit()
    return jsonify({"ok": True})


@app.route("/web/send", methods=["POST"])
def web_send():
    user = current_user()
    if not user:
        return api_error("unauthorized", 401)
    data = request.get_json(silent=True) or {}
    message = str(data.get("message", "")).strip()[:4000]
    if not message:
        return api_error("پیام خالی است.", 400)
    if not throttle(f"send:{user['id']}", 20, 60):
        return api_error("پیام‌ها خیلی سریع ارسال می‌شوند؛ کمی صبر کنید.", 429)

    model_key = str(data.get("model", DEFAULT_MODEL))
    if model_key not in MODELS:
        model_key = DEFAULT_MODEL

    conn = db()
    cid = data.get("conversation_id")
    conv = None
    if cid:
        try:
            cid = int(cid)
        except (TypeError, ValueError):
            return api_error("شناسه گفتگو نامعتبر است.", 400)
        conv = conn.execute(
            "SELECT id, title FROM conversations WHERE id=? AND user_id=?", (cid, user["id"])
        ).fetchone()
        if not conv:
            return api_error("گفتگو پیدا نشد.", 404)

    if conv is None:
        title = title_from(message)
        cur = conn.execute(
            "INSERT INTO conversations (user_id, title, created_at, updated_at) VALUES (?,?,?,?)",
            (user["id"], title, now_iso(), now_iso()),
        )
        cid = cur.lastrowid
        history = []
    else:
        title = conv["title"]
        rows = conn.execute(
            "SELECT role, content FROM messages WHERE conversation_id=? ORDER BY id DESC LIMIT 12", (cid,)
        ).fetchall()
        history = [{"role": r["role"], "content": r["content"]} for r in reversed(rows)]

    conn.execute(
        "INSERT INTO messages (conversation_id, role, content, kind, created_at) VALUES (?,?,?,?,?)",
        (cid, "user", message, None, now_iso()),
    )
    conn.commit()

    reply, kind = process_message(message, history, model_key)

    conn.execute(
        "INSERT INTO messages (conversation_id, role, content, kind, created_at) VALUES (?,?,?,?,?)",
        (cid, "assistant", reply, kind, now_iso()),
    )
    conn.execute("UPDATE conversations SET updated_at=? WHERE id=?", (now_iso(), cid))
    conn.commit()

    return jsonify({"ok": True, "conversation_id": cid, "title": title, "reply": reply, "type": kind})


def read_api_field(keys) -> str:
    data = request.get_json(silent=True) or {}
    for key in keys:
        value = data.get(key) or request.values.get(key)
        if value:
            return str(value)
    return ""


@app.route("/", methods=["OPTIONS"])
def root_options():
    return ("", 204)


@app.route("/api/chat", methods=["GET", "POST"])
def api_chat():
    if not (session.get("uid") or api_token_ok()):
        return api_error("unauthorized", 401)

    message = read_api_field(("message", "text", "q")).strip()[:4000]
    if not message:
        return api_error("پارامتر message ارسال نشده.", 400)

    if not throttle(f"api:{request.remote_addr}", 60, 60):
        return api_error("rate limit", 429)

    model_key = read_api_field(("model",)) or DEFAULT_MODEL
    if model_key not in MODELS:
        model_key = DEFAULT_MODEL

    reply, kind = process_message(message, None, model_key)

    if request.values.get("footer") == "1" and kind != "greeting":
        reply += FOOTER

    if request.values.get("format") == "text":
        return Response(reply, mimetype="text/plain; charset=utf-8")

    return jsonify({"ok": True, "model": MODELS[model_key]["label"], "type": kind, "reply": reply})


if __name__ == "__main__":
    app.run(host="0.0.0.0", port=PORT, threaded=True)