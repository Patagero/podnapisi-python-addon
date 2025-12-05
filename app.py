from flask import Flask, jsonify, request
from flask_cors import CORS
import requests
from bs4 import BeautifulSoup
import zipfile
import io
import re

app = Flask(__name__)
CORS(app)

# ------------------------------------
# CONFIG
# ------------------------------------
SEARCH_URL = "https://www.podnapisi.net/sl/subtitles/search"
DETAIL_URL = "https://www.podnapisi.net"
IMDB_URL = "https://www.imdb.com/title/"

session = requests.Session()


# ------------------------------------
# IMDb → TITLE
# ------------------------------------
def imdb_to_title(imdb_id):
    url = f"{IMDB_URL}{imdb_id}/"
    print("📡 IMDb:", url)

    r = requests.get(url, headers={"User-Agent": "Mozilla/5.0"})
    if r.status_code != 200:
        print("❌ IMDb fetch fail")
        return None

    soup = BeautifulSoup(r.text, "html.parser")
    tag = soup.find("meta", property="og:title")

    if not tag:
        print("❌ IMDb title tag missing")
        return None

    title_full = tag["content"]
    clean_title = re.sub(r"\(\d{4}\).*", "", title_full).strip()

    print("🎬 IMDb title:", clean_title)
    return clean_title


# ------------------------------------
# SEARCH
# ------------------------------------
def search_subtitles(title):
    print("🔍 Searching Podnapisi.NET for:", title)

    params = {
        "keywords": title,
        "language": "sl",
        "sort": "downloads",
    }

    r = session.get(SEARCH_URL, params=params, headers={"User-Agent": "Mozilla/5.0"})
    soup = BeautifulSoup(r.text, "html.parser")

    entries = soup.select(".subtitle-entry")
    results = []

    for item in entries:
        link = item.find("a")
        if not link:
            continue

        href = link.get("href")
        full = DETAIL_URL + href

        results.append({
            "id": href.split("/")[-1],
            "url": full,
            "title": link.text.strip(),
        })

    print(f"✅ Found {len(results)} results")
    return results


# ------------------------------------
# DOWNLOAD ZIP → EXTRACT SRT
# ------------------------------------
def download_srt(zip_url):
    print("⬇ ZIP:", zip_url)
    r = session.get(zip_url, headers={"User-Agent": "Mozilla/5.0"})

    if r.status_code != 200:
        print("❌ ZIP download failed:", r.status_code)
        return None

    z = zipfile.ZipFile(io.BytesIO(r.content))

    for f in z.namelist():
        if f.endswith(".srt"):
            print("📦 Extracted:", f)
            return z.read(f).decode("utf-8", errors="ignore")

    print("❌ No SRT found")
    return None


# ------------------------------------
# MANIFEST
# ------------------------------------
@app.route("/manifest.json")
def manifest():
    return jsonify({
        "id": "org.formio.podnapisi.python",
        "version": "1.0.0",
        "name": "Podnapisi.NET 🇸🇮 Python Addon",
        "description": "Slovenski podnapisi iz Podnapisi.NET (Python, brez Chromium).",
        "idPrefixes": ["tt"],
        "types": ["movie", "series"],
        "resources": ["subtitles"]
    })


# ------------------------------------
# MAIN SUBTITLE ROUTE
# ------------------------------------
@app.route("/subtitles/<video_type>/<imdb_id>.json")
def subtitles_simple(video_type, imdb_id):
    print("🎬 Request for:", imdb_id)

    title = imdb_to_title(imdb_id)
    if not title:
        return jsonify({"subtitles": []})

    results = search_subtitles(title)

    out = []
    for r_item in results:
        dl_url = r_item["url"] + "/download"
        srt = download_srt(dl_url)

        if not srt:
            continue

        out.append({
            "id": r_item["id"],
            "lang": "sl",
            "title": r_item["title"],
            "url": r_item["url"],
            "subtitles": srt
        })

    return jsonify({"subtitles": out})


# ------------------------------------
# EXTRA ROUTE (Stremio/Kodi)
# Accepts filename=..., videoHash=..., ANYTHING
# ------------------------------------
@app.route("/subtitles/<video_type>/<imdb_id>/<extra>.json")
def subtitles_with_extra(video_type, imdb_id, extra):
    print("⚠️ Extra params ignored:", extra)
    return subtitles_simple(video_type, imdb_id)


# ------------------------------------
# RUN
# ------------------------------------
if __name__ == "__main__":
    app.run(host="0.0.0.0", port=10000)
