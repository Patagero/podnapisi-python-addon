from flask import Flask, jsonify
from flask_cors import CORS
import cloudscraper
from bs4 import BeautifulSoup
import re

app = Flask(__name__)
CORS(app)

BASE = "https://www.podnapisi.net"

# Cloudflare bypass scraper
scraper = cloudscraper.create_scraper(
    browser={
        "browser": "chrome",
        "platform": "windows",
        "mobile": False
    }
)

# ---------------------------------------------------
# GET TITLE FROM IMDb
# ---------------------------------------------------
def imdb_to_title(imdb_id):
    url = f"https://www.imdb.com/title/{imdb_id}/"
    r = scraper.get(url)

    soup = BeautifulSoup(r.text, "html.parser")
    meta = soup.find("meta", property="og:title")
    if not meta:
        return None

    title = meta["content"]
    title = re.sub(r"\(\d{4}\).*", "", title).strip()
    return title


# ---------------------------------------------------
# SEARCH SUBTITLES THROUGH Cloudflare-bypassed SESSION
# ---------------------------------------------------
def search_subtitles(title):
    print("🔍 Searching:", title)

    params = {
        "keywords": title,
        "language": "sl",
        "sort": "downloads"
    }

    r = scraper.get(f"{BASE}/sl/subtitles/search", params=params)
    html = r.text

    soup = BeautifulSoup(html, "html.parser")
    rows = soup.select(".subtitle-entry")

    print("HTML length:", len(html))
    print("Found entries:", len(rows))

    out = []

    for row in rows:
        link = row.select_one("a")
        if not link:
            continue

        href = link.get("href")
        out.append({
            "id": href.split("/")[-1],
            "url": BASE + href,
            "title": link.text.strip(),
            "lang": "sl"
        })

    return out


# ---------------------------------------------------
# MANIFEST
# ---------------------------------------------------
@app.route("/manifest.json")
def manifest():
    return jsonify({
        "id": "org.formio.podnapisi.python",
        "version": "7.0.0",
        "name": "Podnapisi.NET 🇸🇮 Python Addon (Cloudflare Bypass)",
        "description": "Search-based + Cloudflare bypass = WORKING subtitles.",
        "idPrefixes": ["tt"],
        "types": ["movie", "series"],
        "resources": ["subtitles"]
    })


# ---------------------------------------------------
# MAIN SUBTITLES ROUTE
# ---------------------------------------------------
@app.route("/subtitles/<type>/<imdb_id>.json")
def subtitles(type, imdb_id):
    print("📥 Request for:", imdb_id)

    title = imdb_to_title(imdb_id)
    if not title:
        return jsonify({"subtitles": []})

    subs = search_subtitles(title)

    return jsonify({"subtitles": subs})


# ---------------------------------------------------
# RUN
# ---------------------------------------------------
if __name__ == "__main__":
    app.run(host="0.0.0.0", port=10000)
