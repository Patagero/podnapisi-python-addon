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
HEADERS = {
    "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64)",
    "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,*/*;q=0.8",
    "Accept-Language": "sl,en-US;q=0.7,en;q=0.3",
    "Connection": "keep-alive"
}
session = requests.Session()


# ---------------------------
# IMDb → Title
# ---------------------------
def imdb_to_title(imdb):
    url = f"https://www.imdb.com/title/{imdb}/"
    r = session.get(url, headers=HEADERS)
    if r.status_code != 200:
        return None

    soup = BeautifulSoup(r.text, "html.parser")
    tag = soup.find("meta", {"property": "og:title"})
    if not tag:
        return None

    clean = re.sub(r"\(\d{4}\).*", "", tag["content"]).strip()
    return clean


# ---------------------------
# Search Subtitles (movies + series)
# ---------------------------
def search_subtitles(title):
    url = f"{BASE}/sl/subtitles/search"
    params = {
        "keywords": title,
        "language": "sl",
        "sort": "downloads"
    }

    r = session.get(url, headers=HEADERS, params=params)
    if r.status_code != 200:
        print("Search failed:", r.status_code)
        return []

    soup = BeautifulSoup(r.text, "html.parser")
    rows = soup.select("table tbody tr")

    results = []
    for row in rows:
        link = row.select_one("a[href*='/sl/subtitles/']")
        if not link:
            continue

        name = link.text.strip()
        href = link["href"]
        dl_url = BASE + href + "/download"

        results.append({
            "name": name,
            "url": dl_url
        })

    return results


# ---------------------------
# Download ZIP → Extract SRT
# ---------------------------
def download_srt(url):
    r = session.get(url, headers=HEADERS)
    if r.status_code != 200:
        return None

    try:
        z = zipfile.ZipFile(io.BytesIO(r.content))
        for f in z.namelist():
            if f.lower().endswith(".srt"):
                return z.read(f).decode("utf-8", errors="ignore")
    except:
        return None

    return None


# ---------------------------
# Manifest
# ---------------------------
@app.route("/manifest.json")
def manifest():
    return jsonify({
        "id": "org.formio.podnapisi.python",
        "version": "4.0.0",
        "name": "Podnapisi.NET 🇸🇮 Python Addon",
        "description": "Slovenski podnapisi (filmi + serije), brez login, brez browserja.",
        "idPrefixes": ["tt"],
        "types": ["movie", "series"],
        "resources": ["subtitles"]
    })


# ---------------------------
# Subtitles endpoint
# ---------------------------
@app.route("/subtitles/<type>/<imdb>.json")
def subtitles(type, imdb):

    title = imdb_to_title(imdb)
    if not title:
        return jsonify({"subtitles": []})

    results = search_subtitles(title)
    out = []

    for r in results:
        text = download_srt(r["url"])
        if not text:
            continue

        out.append({
            "id": r["name"],
            "lang": "sl",
            "title": r["name"],
            "subtitles": text
        })

    return jsonify({"subtitles": out})


# ---------------------------
# Run (Render)
# ---------------------------
if __name__ == "__main__":
    app.run(host="0.0.0.0", port=10000)
