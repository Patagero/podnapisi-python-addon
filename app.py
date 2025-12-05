from flask import Flask, jsonify
from flask_cors import CORS
import cloudscraper
from bs4 import BeautifulSoup
import zipfile
import io
import re
import urllib.parse

app = Flask(__name__)
CORS(app)

scraper = cloudscraper.create_scraper(
    browser={"browser": "chrome", "platform": "windows", "mobile": False}
)

BASE = "https://www.podnapisi.net"


# ------------------------------------------------
# IMDb → Normalized movie slug (for Podnapisi.NET)
# ------------------------------------------------
def imdb_to_slug(imdb_id):
    url = f"https://www.imdb.com/title/{imdb_id}/"
    print("📡 Fetching IMDb:", url)

    r = scraper.get(url)
    if r.status_code != 200:
        print("❌ IMDb fetch failed")
        return None

    soup = BeautifulSoup(r.text, "html.parser")
    tag = soup.find("meta", property="og:title")
    if not tag:
        print("❌ IMDb OG:title missing")
        return None

    full = tag["content"]                   # Titanic (1997) - IMDb
    title = re.sub(r"\s*\(\d{4}\).*", "", full).strip()
    year = re.search(r"\((\d{4})\)", full)
    if not year:
        print("❌ IMDb year missing")
        return None

    year = year.group(1)

    # Podnapisi slug: title-year → lowercase, spaces → hyphens
    slug = f"{title}-{year}".lower()
    slug = re.sub(r"[^a-z0-9\-]+", "-", slug)
    slug = re.sub(r"-+", "-", slug).strip("-")

    print("🎬 IMDb → Podnapisi slug:", slug)
    return slug


# ------------------------------------------------
# Parse movie page and extract Slovenian subtitles
# ------------------------------------------------
def get_subtitles_from_movie_page(slug):
    url = f"{BASE}/sl/movie/{slug}/subtitles"
    print("🔍 Fetching movie page:", url)

    r = scraper.get(url)
    if r.status_code != 200:
        print("❌ Movie page fetch failed")
        return []

    soup = BeautifulSoup(r.text, "html.parser")

    rows = soup.select("tr.subtitle-entry")

    out = []

    for row in rows:
        lang = row.select_one(".flag")
        if not lang:
            continue

        # Slovenian only:
        if "sl" not in lang.get("class", []):
            continue

        link = row.select_one("a[href*='/subtitles/']")
        if not link:
            continue

        href = link["href"]
        title = link.text.strip()
        full_page = BASE + href
        dl_url = full_page + "/download"

        print("📄 Subtitle found:", title)
        print("⬇ Download URL:", dl_url)

        # Download ZIP → extract SRT
        srt = download_srt(dl_url)
        if not srt:
            continue

        out.append({
            "id": href.split("/")[-1],
            "lang": "sl",
            "title": title,
            "url": full_page,
            "subtitles": srt
        })

    print("✅ Total Slovenian subs:", len(out))
    return out


# ------------------------------------------------
# Download ZIP → extract SRT
# ------------------------------------------------
def download_srt(url):
    r = scraper.get(url)
    if r.status_code != 200:
        print("❌ ZIP download failed")
        return None

    try:
        z = zipfile.ZipFile(io.BytesIO(r.content))
    except:
        print("❌ ZIP corrupt")
        return None

    for f in z.namelist():
        if f.endswith(".srt"):
            print("📦 Extracted:", f)
            return z.read(f).decode("utf-8", errors="ignore")

    print("❌ No SRT found")
    return None


# ------------------------------------------------
# Manifest
# ------------------------------------------------
@app.route("/manifest.json")
def manifest():
    return jsonify({
        "id": "org.formio.podnapisi.python",
        "version": "2.0.0",
        "name": "Podnapisi.NET 🇸🇮 Python Addon (Movie Page Version)",
        "description": "Končno delujoči slovenski podnapisi iz Podnapisi.NET — brez browserja, brez searcha, 100% stabilno.",
        "idPrefixes": ["tt"],
        "types": ["movie", "series"],
        "resources": ["subtitles"]
    })


# ------------------------------------------------
# MAIN ROUTE (simple)
# ------------------------------------------------
@app.route("/subtitles/<video_type>/<imdb_id>.json")
def subtitles_simple(video_type, imdb_id):
    slug = imdb_to_slug(imdb_id)
    if not slug:
        return jsonify({"subtitles": []})

    results = get_subtitles_from_movie_page(slug)
    return jsonify({"subtitles": results})


# ------------------------------------------------
# EXTRA ROUTE (Stremio filename/hash support)
# ------------------------------------------------
@app.route("/subtitles/<video_type>/<imdb_id>/<extra>.json")
def subtitles_extra(video_type, imdb_id, extra):
    print("⚠️ Ignoring Stremio extra params:", extra)
    return subtitles_simple(video_type, imdb_id)


# ------------------------------------------------
# RUN SERVER
# ------------------------------------------------
if __name__ == "__main__":
    app.run(host="0.0.0.0", port=10000)
