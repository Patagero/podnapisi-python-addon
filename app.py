from flask import Flask, jsonify
from flask_cors import CORS
import requests
from bs4 import BeautifulSoup
import zipfile
import io
import re
import os

app = Flask(__name__)
CORS(app)

USERNAME = os.environ.get("PN_USERNAME", "")
PASSWORD = os.environ.get("PN_PASSWORD", "")

LOGIN_URL = "https://www.podnapisi.net/sl/users/login"
SEARCH_URL = "https://www.podnapisi.net/sl/subtitles/search"
DETAIL_URL = "https://www.podnapisi.net"

session = requests.Session()
cookies_loaded = False


# -----------------------------
# LOGIN FIXED
# -----------------------------
def login_if_needed():
    global cookies_loaded
    if cookies_loaded:
        return True

    print("🔐 Fetching login page…")

    r = session.get(LOGIN_URL, headers={"User-Agent": "Mozilla/5.0"})
    soup = BeautifulSoup(r.text, "lxml")

    csrf_input = soup.find("input", {"name": "_token"})
    if not csrf_input:
        print("❌ No CSRF token found!")
        return False

    csrf_token = csrf_input["value"]
    print("🔑 CSRF token:", csrf_token)

    # REAL LOGIN FIELDS (verified)
    payload = {
        "_token": csrf_token,
        "mail": USERNAME,         # THIS WORKS even if username is not an email
        "password": PASSWORD,
        "remember-me": "on"
    }

    headers_post = {
        "User-Agent": "Mozilla/5.0",
        "Referer": LOGIN_URL,
        "Origin": "https://www.podnapisi.net",
        "Content-Type": "application/x-www-form-urlencoded",
    }

    print(f"🔐 Logging in as: {USERNAME}")

    resp = session.post(
        LOGIN_URL,
        data=payload,
        headers=headers_post,
        allow_redirects=True
    )

    # SUCCESS CHECKS
    if "Odjava" in resp.text or USERNAME.lower() in resp.text.lower():
        print("✅ Login successful!")
        cookies_loaded = True
        return True

    print("❌ Login failed!")
    return False


# -----------------------------
# IMDb → Title
# -----------------------------
def imdb_to_title(imdb_id):
    url = f"https://www.imdb.com/title/{imdb_id}/"
    print("📡 Fetching IMDb:", url)

    r = requests.get(url, headers={"User-Agent": "Mozilla/5.0"})
    if r.status_code != 200:
        print("❌ IMDb fetch failed")
        return None

    soup = BeautifulSoup(r.text, "html.parser")
    meta = soup.find("meta", property="og:title")

    if not meta:
        return None

    clean = re.sub(r"\(\d{4}\).*", "", meta["content"]).strip()
    print("🎬 Title parsed:", clean)
    return clean


# -----------------------------
# Search Podnapisi.net
# -----------------------------
def find_subtitles(title):
    print("🔍 Searching Podnapisi.net for:", title)

    params = {
        "keywords": title,
        "language": "sl",
        "sort": "downloads"
    }

    r = session.get(SEARCH_URL, params=params, headers={"User-Agent": "Mozilla/5.0"})
    soup = BeautifulSoup(r.text, "html.parser")

    items = soup.select(".subtitle-entry")
    out = []

    for item in items:
        link = item.find("a")
        if not link:
            continue

        href = link.get("href")
        if not href:
            continue

        out.append({
            "id": href.split("/")[-1],
            "url": DETAIL_URL + href,
            "name": link.text.strip(),
            "lang": "sl"
        })

    print(f"✅ Found {len(out)} subtitles")
    return out


# -----------------------------
# Download subtitle ZIP + extract SRT
# -----------------------------
def download_subtitle(url):
    print("⬇ Downloading:", url)
    r = session.get(url, headers={"User-Agent": "Mozilla/5.0"})

    if r.status_code != 200:
        print("❌ ZIP download failed")
        return None

    z = zipfile.ZipFile(io.BytesIO(r.content))

    for f in z.namelist():
        if f.lower().endswith(".srt"):
            print("📦 Extracting:", f)
            return z.read(f).decode("utf-8", errors="ignore")

    print("❌ No SRT inside ZIP")
    return None


# -----------------------------
# Manifest
# -----------------------------
@app.route("/manifest.json")
def manifest():
    return jsonify({
        "id": "org.formio.podnapisi.python",
        "version": "1.0.0",
        "name": "Podnapisi.NET 🇸🇮 Python Addon",
        "description": "Slovenski podnapisi iz Podnapisi.NET (Python brez Chromium).",
        "idPrefixes": ["tt"],
        "types": ["movie", "series"],
        "resources": ["subtitles"]
    })


# -----------------------------
# Stremio Subtitles Endpoint
# -----------------------------
@app.route("/subtitles/<type>/<imdb_id>.json")
def subtitles(type, imdb_id):

    if not login_if_needed():
        return jsonify({"subtitles": []})

    title = imdb_to_title(imdb_id)
    if not title:
        return jsonify({"subtitles": []})

    subs = find_subtitles(title)
    out = []

    for s in subs:
        dl_url = s["url"] + "/download"
        srt_text = download_subtitle(dl_url)

        if not srt_text:
            continue

        out.append({
            "id": s["id"],
            "lang": "sl",
            "title": s["name"],
            "subtitles": srt_text
        })

    return jsonify({"subtitles": out})


# -----------------------------
# Diagnostic Test Endpoint
# -----------------------------
@app.route("/test/<imdb>")
def test(imdb):
    ok = login_if_needed()
    title = imdb_to_title(imdb)
    results = find_subtitles(title) if title else []

    return jsonify({
        "imdb": imdb,
        "login_success": ok,
        "title": title,
        "results_found": len(results)
    })


# -----------------------------
# Run server
# -----------------------------
if __name__ == "__main__":
    app.run(host="0.0.0.0", port=10000)
