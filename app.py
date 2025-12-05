from flask import Flask, jsonify
from flask_cors import CORS
import cloudscraper
from bs4 import BeautifulSoup
import zipfile
import io
import re

app = Flask(__name__)
CORS(app)

# Cloudflare-bypass session
scraper = cloudscraper.create_scraper(
    browser={"browser": "chrome", "platform": "windows", "mobile": False}
)

SEARCH_URL = "https://www.podnapisi.net/sl/subtitles/search"
DETAIL_URL = "https://www.podnapisi.net"
IMDB_URL = "https://www.imdb.com/title/"


# ------------------------------------------------
# IMDb → Title (only for logging, not for search)
# ------------------------------------------------
def imdb_to_title(imdb_id):
    url = f"{IMDB_URL}{imdb_id}/"
    print("📡 IMDb:", url)

    r = scraper.get(url)
    if r.status_code != 200:
        print("❌ IMDb error")
        return None

    soup = BeautifulSoup(r.text, "html.parser")
    tag = soup.find("meta", property="og:title")

    if not tag:
        print("❌ IMDb meta fail")
        return None

    title_full = tag["content"]
    clean_title = re.sub(r"\(\d{4}\).*", "", title_full).strip()

    print("🎬 IMDb title:", clean_title)
    return clean_title


# ------------------------------------------------
# SEARCH PODNAPISI.NET **BY IMDB ID**
# ------------------------------------------------
def search_subtitles(imdb_id):
    print("🔍 Searching Podnapisi.NET for IMDB:", imdb_id)

    params = {
        "keywords": imdb_id,   # <-- KLJUČNO: iščemo po tt0120338
        "language": "sl",
        "sort": "downloads",
    }

    r = scraper.get(SEARCH_URL, params=params)
    soup = BeautifulSoup(r.text, "html.parser")
    rows = soup.select(".subtitle-entry")

    results = []
    for row in rows:
        link = row.find("a")
        if not link:
            continue

        href = link.get("href")
        results.append({
            "id": href.split("/")[-1],
            "title": link.text.strip(),
            "url": DETAIL_URL + href
        })

    print("✅ Found", len(results), "subtitles")
    return results


# ------------------------------------------------
# DOWNLOAD ZIP → EXTRACT SRT
# ------------------------------------------------
def download_srt(url):
    print("⬇ Download ZIP:", url)

    r = scraper.get(url)
    if r.status_code != 200:
        print("❌ ZIP error", r.status_code)
        return None

    z = zipfile.ZipFile(io.BytesIO(r.content))

    for f in z.namelist():
        if f.endswith(".srt"):
            print("📦 Extracting:", f)
            return z.read(f).decode("utf-8", errors="ignore")

    print("❌ No SRT found")
    return None


# ------------------------------------------------
# MANIFEST
# ------------------------------------------------
@app.route("/manifest.json")
def manifest():
    return jsonify({
        "id": "org.formio.podnapisi.python",
        "version": "1.1.0",
        "name": "Podnapisi.NET 🇸🇮 Python Addon",
        "description": "Slovenski podnapisi iz Podnapisi.NET (Python + Cloudflare bypass + IMDB search).",
        "resources": ["subtitles"],
        "types": ["movie", "series"],
        "idPrefixes": ["tt"]
    })


# ------------------------------------------------
# MAIN SUBTITLE ROUTE (Stremio Simple)
# ------------------------------------------------
@app.route("/subtitles/<video_type>/<imdb_id>.json")
def subtitles_simple(video_type, imdb_id):

    # Only for logging:
    imdb_to_title(imdb_id)

    results = search_subtitles(imdb_id)
    out = []

    for r in results:
        dl_url = r["url"] + "/download"
        srt = download_srt(dl_url)

        if not srt:
            continue

        out.append({
            "id": r["id"],
            "title": r["title"],
            "lang": "sl",
            "url": r["url"],
            "subtitles": srt
        })

    return jsonify({"subtitles": out})


# ------------------------------------------------
# EXTRA ROUTE (Stremio filename=... support)
# ------------------------------------------------
@app.route("/subtitles/<video_type>/<imdb_id>/<extra>.json")
def subtitles_extra(video_type, imdb_id, extra):
    print("⚠️ Stremio extra params ignored:", extra)
    return subtitles_simple(video_type, imdb_id)


# ------------------------------------------------
# RUN SERVER
# ------------------------------------------------
if __name__ == "__main__":
    app.run(host="0.0.0.0", port=10000)
