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


# ---------------------------------------------------
# IMDb → Title
# ---------------------------------------------------
def imdb_to_title(imdb):
    url = f"https://www.imdb.com/title/{imdb}/"
    r = requests.get(url, headers={"User-Agent": "Mozilla/5.0"})
    if r.status_code != 200:
        return None

    soup = BeautifulSoup(r.text, "html.parser")
    tag = soup.find("meta", property="og:title")
    if not tag:
        return None

    clean = re.sub(r"\(\d{4}\).*", "", tag["content"]).strip()
    return clean


# ---------------------------------------------------
# SEARCH USING REAL PODNAPISI SEARCH PAGE
# ---------------------------------------------------
def search_subtitles(title):
    url = f"{BASE}/sl/subtitles/search"
    params = {
        "keywords": title,
        "language": "sl",
        "sort": "downloads"
    }

    print("🔍 Searching:", url, params)

    r = requests.get(url, headers={"User-Agent": "Mozilla/5.0"}, params=params)
    if r.status_code != 200:
        print("❌ Search failed")
        return []

    soup = BeautifulSoup(r.text, "html.parser")

    rows = soup.select("table tbody tr")

    if not rows:
        print("❌ No rows found")
        return []

    results = []

    for row in rows:
        link = row.select_one("a[href*='/sl/subtitles/']")
        if not link:
            continue

        name = link.text.strip()
        href = link.get("href")

        # full page → + "/download"
        url = BASE + href + "/download"

        results.append({
            "name": name,
            "url": url
        })

    print("✅ Found", len(results), "Slovenian subtitles")
    return results


# ---------------------------------------------------
# DOWNLOAD ZIP → SRT
# ---------------------------------------------------
def download_srt(url):
    print("⬇ Downloading:", url)

    r = requests.get(url, headers={"User-Agent": "Mozilla/5.0"})
    if r.status_code != 200:
        print("❌ Cannot download")
        return None

    try:
        z = zipfile.ZipFile(io.BytesIO(r.content))
        for f in z.namelist():
            if f.endswith(".srt"):
                return z.read(f).decode("utf-8", errors="ignore")
    except:
        return None

    return None


# ---------------------------------------------------
# MANIFEST
# ---------------------------------------------------
@app.route("/manifest.json")
def manifest():
    return jsonify({
        "id": "org.formio.podnapisi.python",
        "version": "3.0.0",
        "name": "Podnapisi.NET 🇸🇮 Python Addon",
        "description": "Slovenski podnapisi preko uradnega search endpointa.",
        "idPrefixes": ["tt"],
        "types": ["movie"],
        "resources": ["subtitles"]
    })


# ---------------------------------------------------
# MAIN SUBTITLE ENDPOINT
# ---------------------------------------------------
@app.route("/subtitles/movie/<imdb>.json")
def subtitles(imdb):

    title = imdb_to_title(imdb)
    if not title:
        return jsonify({"subtitles": []})

    results = search_subtitles(title)
    if not results:
        return jsonify({"subtitles": []})

    out = []

    for r_info in results:
        text = download_srt(r_info["url"])
        if not text:
            continue

        out.append({
            "id": r_info["name"],
            "lang": "sl",
            "title": r_info["name"],
            "subtitles": text
        })

    return jsonify({"subtitles": out})


# ---------------------------------------------------
# RUN LOCAL
# ---------------------------------------------------
if __name__ == "__main__":
    app.run(host="0.0.0.0", port=10000)
