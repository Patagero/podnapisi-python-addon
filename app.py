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

    headers = {
        "User-Agent": "Mozilla/5.0",
        "Accept": "text/html",
        "Referer": LOGIN_URL,
    }

    r = session.get(LOGIN_URL, headers=headers)
    soup = BeautifulSoup(r.text, "lxml")

    token_tag = soup.find("input", {"name": "_token"})
    if not token_tag:
        print("❌ CSRF token not found")
        return False

    csrf_token = token_tag["value"]
    print("🔑 CSRF token:", csrf_token)

    payload = {
        "_token": csrf_token,
        "mail": USERNAME,      # <-- PRAVILNO
        "password": PASSWORD,
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

    if "Odjava" in resp.text or USERNAME.lower() in resp.text.lower():
        print("✅ Login successful")
        cookies_loaded = True
        return True

    print("❌ Login failed")
    return False


# -----------------------------
# IMDb → TITLE
# -----------------------------
def imdb_to_title(imdb_id):
    if imdb_id.startswith("tt"):
        url = f"https://www.imdb.com/title/{imdb_id}/"
    else:
        return None

    print("📡 Fetching IMDb:", url)

    r = requests.get(url, headers={"User-Agent": "Mozilla/5.0"})
    if r.status_code != 200:
        print("❌ IMDb lookup failed")
        return None

    soup = BeautifulSoup(r.text, "html.parser")
    og_title = soup.find("meta", property="og:title")

    if not og_title or "content" not in og_title.attrs:
        print("❌ IMDb title parse fail")
        return None

    full_title = og_title["content"]
    clean = re.sub(r"\(\d{4}\).*", "", full_title).strip()

    print("🎬 IMDb →", clean)
    return clean


# -----------------------------
# SEARCH PODNAPISI.NET
# -----------------------------
def find_subtitles(title):
    print("🔍 Searching Podnapisi.NET for:", title)

    params = {
        "keywords": title,
        "language": "sl",
        "sort": "downloads",
    }

    headers = {
        "User-Agent": "Mozilla/5.0",
        "Referer": SEARCH_URL,
    }

    r = session.get(SEARCH_URL, headers=headers, params=params)

    soup = BeautifulSoup(r.text, "html.parser")
    results = soup.select(".subtitle-entry")

    out = []
    for item in results:
        link = item.find("a")
        if not link:
            continue

        href = link.get("href")
        if not href:
            continue

        full_link = DETAIL_URL + href

        out.append({
            "id": href.split("/")[-1],
            "url": full_link,
            "name": link.text.strip(),
            "lang": "sl",
        })

    print(f"✅ Found {len(out)} subtitles")
    return out


# -----------------------------
# DOWNLOAD + UNZIP SUBTITLE
# -----------------------------
def download_subtitle(url):
    print("⬇ Downloading ZIP:", url)

    r = session.get(url, headers={"User-Agent": "Mozilla/5.0"})
    if r.status_code != 200:
        print("❌ ZIP download failed")
        return None

    z = zipfile.ZipFile(io.BytesIO(r.content))

    for file in z.namelist():
        if file.endswith(".srt"):
            print("📦 Extracted:", file)
            return z.read(file).decode("utf-8", errors="ignore")

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
# SUBTITLES ENDPOINT
# -----------------------------
@app.route("/subtitles/<type>/<imdb_id>/<extra>.json")
def subtitles(type, imdb_id, extra):

    if not login_if_needed():
        return jsonify({"subtitles": []})

    title = imdb_to_title(imdb_id)
    if not title:
        return jsonify({"subtitles": []})

    search_results = find_subtitles(title)
    out = []

    for s in search_results:
        dl = s["url"] + "/download"
        text = download_subtitle(dl)

        if not text:
            continue

        out.append({
            "id": s["id"],
            "url": s["url"],
            "lang": "sl",
            "subtitles": text,
            "title": s["name"],
        })

    return jsonify({"subtitles": out})


# -----------------------------
# RUN
# -----------------------------
if __name__ == "__main__":
    app.run(host="0.0.0.0", port=10000)
