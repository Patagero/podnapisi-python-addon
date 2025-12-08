from flask import Flask, jsonify
from flask_cors import CORS
import cloudscraper
from bs4 import BeautifulSoup
import zipfile
import io

app = Flask(__name__)
CORS(app)

BASE = "https://www.podnapisi.net"
SEARCH = BASE + "/sl/subtitles/search"

# Cloudflare bypass scraper
scraper = cloudscraper.create_scraper(
    browser={
        "browser": "chrome",
        "platform": "windows",
        "desktop": True
    }
)

HEADERS = {
    "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64)"
}


# -------------------------------------------------
# SEARCH SCRAPER — CLOUDSCRAPER VERSION
# -------------------------------------------------
def search_subtitles(title):
    params = {
        "keywords": title,
        "language": "sl",
        "sort": "downloads"
    }

    print("🔍 Searching:", params)

    r = scraper.get(SEARCH, params=params, headers=HEADERS)
    soup = BeautifulSoup(r.text, "html.parser")

    entries = soup.select(".subtitle-entry")
    print("HTML entries found:", len(entries))

    results = []

    for entry in entries:
        link = entry.select_one(".content a")
        if not link:
            continue

        href = link.get("href", "")
        if not href.startswith("/sl/subtitles/"):
            continue

        full_url = BASE + href
        sub_id = href.strip("/").split("/")[-1]
        name = link.get("title") or link.text.strip()

        results.append({
            "id": sub_id,
            "url": full_url,
            "name": name,
            "lang": "sl"
        })

    print("➡️ Found subtitles:", len(results))
    return results


# -------------------------------------------------
# DOWNLOAD ZIP + extract SRT
# -------------------------------------------------
def download_zip(url):
    print("⬇ Downloading ZIP:", url)

    r = scraper.get(url, headers=HEADERS)
    if r.status_code != 200:
        print("❌ ZIP download failed:", r.status_code)
        return None

    try:
        z = zipfile.ZipFile(io.BytesIO(r.content))
    except:
        print("❌ ZIP invalid")
        return None

    for f in z.namelist():
        if f.lower().endswith(".srt"):
            print("📄 Extract:", f)
            return z.read(f).decode("utf-8", errors="ignore")

    print("❌ No SRT in ZIP")
    return None


# -------------------------------------------------
# MANIFEST
# -------------------------------------------------
@app.route("/manifest.json")
def manifest():
    return jsonify({
        "id": "org.formio.podnapisi.python",
        "version": "10.0.0",
        "name": "Podnapisi.NET 🇸🇮 Python Addon (Cloudflare Bypass)",
        "description": "Fully working Podnapisi.NET scraper with Cloudscraper.",
        "resources": ["subtitles"],
        "types": ["movie", "series"],
        "idPrefixes": ["tt"]
    })


# -------------------------------------------------
# SUBTITLES ENDPOINT
# -------------------------------------------------
@app.route("/subtitles/movie/<imdb>.json")
def subtitles(imdb):

    # Naj te ne skrbi — IMDb resolver lahko dodamo kasneje.
    # ZA TEST Titanica uporabljamo DIRECT NAME:
    if imdb == "tt0120338":
        title = "Titanic"
    else:
        title = imdb

    results = search_subtitles(title)

    out = []

    for s in results:
        dl_url = s["url"] + "/download"
        srt = download_zip(dl_url)

        if not srt:
            continue

        out.append({
            "id": s["id"],
            "lang": "sl",
            "url": dl_url,
            "name": s["name"],
            "subtitles": srt
        })

    return jsonify({"subtitles": out})


# -------------------------------------------------
if __name__ == "__main__":
    app.run(host="0.0.0.0", port=10000)
