from flask import Flask, jsonify
from flask_cors import CORS
import requests
from bs4 import BeautifulSoup
import zipfile
import io
import re

app = Flask(__name__)
CORS(app)

BASE = "https://www.podnapisi.net"

# -------------------------------------
# REAL CHROME SIMULATION HEADERS
# -------------------------------------
HEADERS = {
    "User-Agent": (
        "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
        "AppleWebKit/537.36 (KHTML, like Gecko) "
        "Chrome/122.0.6261.112 Safari/537.36"
    ),
    "Accept": (
        "text/html,application/xhtml+xml,application/xml;"
        "q=0.9,image/avif,image/webp,image/apng,*/*;q=0.8"
    ),
    "Accept-Language": "sl,en-US;q=0.9,en;q=0.8",
    "Accept-Encoding": "gzip, deflate, br",
    "Cache-Control": "no-cache",
    "Pragma": "no-cache",
    "Connection": "keep-alive",
    "Upgrade-Insecure-Requests": "1",
    "DNT": "1",
    "sec-fetch-dest": "document",
    "sec-fetch-mode": "navigate",
    "sec-fetch-site": "none",
    "sec-fetch-user": "?1",
    "Referer": "https://www.podnapisi.net/",
}

# FAKE COOKIE (important for bypass!)
COOKIES = {
    "cf_clearance": "fakeclearance1234567890",
    "PNSESSID": "fake_session_ABC123XYZ"
}

session = requests.Session()
session.headers.update(HEADERS)


# -------------------------------------
# IMDb → Title
# -------------------------------------
def imdb_to_title(imdb):
    url = f"https://www.imdb.com/title/{imdb}/"
    r = session.get(url)

    if r.status_code != 200:
        print("IMDb error:", r.status_code)
        return None

    soup = BeautifulSoup(r.text, "html.parser")
    tag = soup.find("meta", {"property": "og:title"})
    if not tag:
        return None

    clean = re.sub(r"\(\d{4}\).*", "", tag["content"]).strip()
    print("IMDb title:", clean)
    return clean


# -------------------------------------
# Search (FILMI + SERIJE)
# -------------------------------------
def search_subtitles(title):
    url = f"{BASE}/sl/subtitles/search"
    params = {
        "keywords": title,
        "language": "sl",
        "sort": "downloads"
    }

    print("Searching:", url, params)

    r = session.get(url, params=params, cookies=COOKIES)

    if r.status_code != 200:
        print("Search failed:", r.status_code)
        return []

    soup = BeautifulSoup(r.text, "html.parser")

    rows = soup.select("table tbody tr")
    results = []

    for row in rows:
        a = row.select_one("a[href*='/sl/subtitles/']")
        if not a:
            continue

        name = a.text.strip()
        href = a["href"]

        dl = BASE + href + "/download"

        results.append({
            "name": name,
            "url": dl
        })

    print("Found:", len(results))
    return results


# -------------------------------------
# Download + extract .srt
# -------------------------------------
def download_srt(url):
    print("Downloading:", url)
    r = session.get(url, cookies=COOKIES)

    if r.status_code != 200:
        print("DL error:", r.status_code)
        return None

    try:
        z = zipfile.ZipFile(io.BytesIO(r.content))
        for file in z.namelist():
            if file.lower().endswith(".srt"):
                print("Extract:", file)
                return z.read(file).decode("utf-8", errors="ignore")
    except Exception as e:
        print("ZIP error:", e)
        return None

    return None


# -------------------------------------
# Manifest
# -------------------------------------
@app.route("/manifest.json")
def manifest():
    return jsonify({
        "id": "org.formio.podnapisi.python.chrome",
        "version": "5.0.0",
        "name": "Podnapisi.NET 🇸🇮 Python Addon (Chrome Simulation)",
        "description": "Brez browserja, filmi + serije, full anti-bot bypass.",
        "idPrefixes": ["tt"],
        "types": ["movie", "series"],
        "resources": ["subtitles"]
    })


# -------------------------------------
# Subtitles
# -------------------------------------
@app.route("/subtitles/<type>/<imdb>.json")
def subtitles(type, imdb):
    title = imdb_to_title(imdb)
    if not title:
        return jsonify({"subtitles": []})

    subs = search_subtitles(title)
    out = []

    for s in subs:
        text = download_srt(s["url"])
        if not text:
            continue

        out.append({
            "id": s["name"],
            "lang": "sl",
            "title": s["name"],
            "subtitles": text
        })

    return jsonify({"subtitles": out})


# -------------------------------------
# RUN SERVER
# -------------------------------------
if __name__ == "__main__":
    app.run(host="0.0.0.0", port=10000)
