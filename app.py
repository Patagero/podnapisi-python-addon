from flask import Flask, jsonify
from flask_cors import CORS
import cloudscraper
from bs4 import BeautifulSoup
import zipfile
import io
import re

app = Flask(__name__)
CORS(app)

# Cloudflare bypass session (cloudscraper instead of requests)
scraper = cloudscraper.create_scraper(
    browser={"browser": "chrome", "platform": "windows", "mobile": False}
)

SEARCH_URL = "https://www.podnapisi.net/sl/subtitles/search"
DETAIL_URL = "https://www.podnapisi.net"
IMDB_URL = "https://www.imdb.com/title/"


# ------------------------------------
# IMDb → TITLE
# ------------------------------------
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


# ------------------------------------
# SEARCH PODNAPISI.NET (Cloudflare bypass)
# ------------------------------------
def search_subtitles(title):
    print("🔍 Searching:", title)

    params = {
        "keywords": title,
        "language": "sl",
        "sort": "downloads",
    }

    r = scraper.get(SEARCH_URL, params=params)

    soup = BeautifulSoup(r.text, "html.parser")
    entries = soup.select(".subtitle-entry")

    results = []
    for e in entries:
        link = e.find("a")
        if not link:
            continue

        href = link.get("href")
        results.append({
            "id": href.split("/")[-1],
            "title": link.text.strip(),
            "url": DETAIL_URL + href
        })

    print("✅ Results:", len(results))
    return results


# ------------------------------------
# DOWNLOAD ZIP → EXTRACT SRT
# ------------------------------------
def download_srt(url):
    print("⬇ ZIP:", url)

    r = scraper.get(url)
    if r.status_code != 200:
        print("❌ ZIP download fail")
        return None

    z = zipfile.ZipFile(io.BytesIO(r.content))

    for name in z.namelist():
        if name.endswith(".srt"):
            print("📦 Extracted:", name)
            return z.read(name).decode("utf-8", errors="ignore")

    print("❌ No SRT in ZIP")
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
        "description": "Slovenski podnapisi (Python + Cloudflare bypass).",
        "idPrefixes": ["tt"],
        "types": ["movie", "series"],
        "resources": ["subtitles"]
    })


# ------------------------------------
# MAIN SUBTITLE ROUTE
# ------------------------------------
@app.route("/subtitles/<video_type>/<imdb_id>.json")
def subtitles_simple(video_type, imdb_id):
    title = imdb_to_title(imdb_id)
    if not title:
        return jsonify({"subtitles": []})

    results = search_subtitles(title)
    out = []

    for s in results:
        dl = s["url"] + "/download"
        srt = download_srt(dl)
        if not srt:
            continue

        out.append({
            "id": s["id"],
            "title": s["title"],
            "lang": "sl",
            "url": s["url"],
            "subtitles": srt
        })

    return jsonify({"subtitles": out})


# ------------------------------------
# EXTRA ROUTE FOR STREMIO
# ------------------------------------
@app.route("/subtitles/<video_type>/<imdb_id>/<extra>.json")
def subtitles_extra(video_type, imdb_id, extra):
    print("⚠️ Extra params ignored:", extra)
    return subtitles_simple(video_type, imdb_id)


# ------------------------------------
# RUN
# ------------------------------------
if __name__ == "__main__":
    app.run(host="0.0.0.0", port=10000)
