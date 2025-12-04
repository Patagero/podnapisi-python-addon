from flask import Flask, jsonify, request
from flask_cors import CORS
import requests
from bs4 import BeautifulSoup
import zipfile
import io
import re
import os

app = Flask(__name__)
CORS(app)

# -----------------------------
# CONFIG
# -----------------------------
USERNAME = os.environ.get("PN_USERNAME", "")
PASSWORD = os.environ.get("PN_PASSWORD", "")

LOGIN_URL = "https://www.podnapisi.net/sl/users/login"
SEARCH_URL = "https://www.podnapisi.net/sl/subtitles/search"
DETAIL_URL = "https://www.podnapisi.net"

session = requests.Session()
cookies_loaded = False


# -----------------------------
# LOGIN
# -----------------------------
def login_if_needed():
    global cookies_loaded
    if cookies_loaded:
        return True

    print("🔐 Fetching login page...")

    r = session.get(LOGIN_URL, headers={"User-Agent": "Mozilla/5.0"})
    soup = BeautifulSoup(r.text, "lxml")

    # CSRF TOKEN
    token_tag = soup.find("input", {"name": "_token"})
    if not token_tag:
        print("❌ CSRF token not found in login page!")
        return False

    csrf_token = token_tag["value"]
    print("🔑 CSRF token:", csrf_token)

    # REAL login payload — Podnapisi.NET expects "username", not "mail"
    payload = {
        "_token": csrf_token,
        "username": USERNAME,
        "password": PASSWORD,
        "remember": "1"
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
        headers=headers_post,
        data=payload,
        allow_redirects=True
    )

    # SUCCESS CONDITIONS
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
    if not imdb_id.startswith("tt"):
        return None

    url = f"https://www.imdb.com/title/{imdb_id}/"
    print("📡 IMDb URL:", url)

    r = requests.get(url, headers={"User-Agent": "Mozilla/5.0"})
    if r.status_code != 200:
        print("❌ IMDb fetch failed")
        return None

    soup = BeautifulSoup(r.text, "html.parser")
    meta = soup.find("meta", property="og:title")

    if not meta:
        print("❌ IMDb title not found")
        return None

    full_title = meta["content"]
    clean = re.sub(r"\(\d{4}\).*", "", full_title).strip()

    print("🎬 Parsed title:", clean)
    return clean


# -----------------------------
# SEARCH SUBTITLES
# -----------------------------
def find_subtitles(title):
    print("🔍 Searching Podnapisi.NET:", title)

    params = {
        "keywords": title,
        "language": "sl",
        "sort": "downloads"
    }

    r = session.get(SEARCH_URL, headers={"User-Agent": "Mozilla/5.0"}, params=params)
    soup = BeautifulSoup(r.text, "html.parser")

    entries = soup.select(".subtitle-entry")

    results = []
    for e in entries:
        a = e.find("a")
        if not a:
            continue

        href = a.get("href")
        if not href:
            continue

        full_url = DETAIL_URL + href
        name = a.text.strip()

        results.append({
            "id": href.split("/")[-1],
            "url": full_url,
            "name": name,
            "lang": "sl"
        })

    print(f"✅ Found {len(results)} subtitles")
    return results


# -----------------------------
# DOWNLOAD ZIP + EXTRACT SRT
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
            print("📦 Extracted:", f)
            try:
                return z.read(f).decode("utf-8", errors="ignore")
            except:
                return z.read(f).decode("iso-8859-1", errors="ignore")

    print("❌ No SRT found in zip")
    return None


# -----------------------------
# MANIFEST
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
# SUBTITLES ENDPOINT FOR STREMIO
# -----------------------------
@app.route("/subtitles/<type>/<imdb_id>.json")
def subtitles(imdb_id, type):
    if not login_if_needed():
        return jsonify({"subtitles": []})

    title = imdb_to_title(imdb_id)
    if not title:
        return jsonify({"subtitles": []})

    subs = find_subtitles(title)
    output = []

    for s in subs:
        dl_url = s["url"] + "/download"
        text = download_subtitle(dl_url)
        if not text:
            continue

        output.append({
            "id": s["id"],
            "lang": "sl",
            "url": s["url"],
            "title": s["name"],
            "subtitles": text
        })

    return jsonify({"subtitles": output})


# -----------------------------
# DEBUG / TEST ENDPOINT
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
# RUN SERVER
# -----------------------------
if __name__ == "__main__":
    app.run(host="0.0.0.0", port=10000)
