from flask import Flask, jsonify
from flask_cors import CORS
import requests
from bs4 import BeautifulSoup
import re

app = Flask(__name__)
CORS(app)

BASE = "https://www.podnapisi.net"


# ---------------------------------------------------
# GET CLEAN TITLE FROM IMDb
# ---------------------------------------------------
def imdb_to_title(imdb_id):
    url = f"https://www.imdb.com/title/{imdb_id}/"
    r = requests.get(url, headers={"User-Agent": "Mozilla/5.0"})

    soup = BeautifulSoup(r.text, "html.parser")
    meta = soup.find("meta", property="og:title")
    if not meta:
        return None

    title = meta["content"]
    title = re.sub(r"\(\d{4}\).*", "", title).strip()
    return title


# ---------------------------------------------------
# SEARCH PODNAPISI.NET FOR SUBTITLES
# ---------------------------------------------------
def search_subtitles(title):
    print("🔍 Searching for:", title)

    params = {
        "keywords": title,
        "language": "sl",
        "sort": "downloads"
    }

    r = requests.get(f"{BASE}/sl/subtitles/search", params=params, headers={"User-Agent": "Mozilla/5.0"})

    soup = BeautifulSoup(r.text, "html.parser")
    
    rows = soup.select(".subtitle-entry")
    out = []

    for row in rows:
        link = row.select_one("a")
        if not link:
            continue

        href = link.get("href")

        lang_flag = row.select_one(".flag")
        lang = lang_flag.get("title", "unknown") if lang_flag else "unknown"

        out.append({
            "id": href.split("/")[-1],
            "url": BASE + href,
            "title": link.text.strip(),
            "lang": lang,
        })

    print("✅ Found", len(out), "subtitles")
    return out


# ---------------------------------------------------
# MANIFEST
# ---------------------------------------------------
@app.route("/manifest.json")
def manifest():
    return jsonify({
        "id": "org.formio.podnapisi.python",
        "version": "6.0.0",
        "name": "Podnapisi.NET 🇸🇮 Python Addon (Search Based)",
        "description": "Ultra-stable version using search instead of movie page.",
        "idPrefixes": ["tt"],
        "types": ["movie", "series"],
        "resources": ["subtitles"]
    })


# ---------------------------------------------------
# SUBTITLES ENDPOINT (MAIN)
# ---------------------------------------------------
@app.route("/subtitles/<type>/<imdb_id>.json")
def subtitles(type, imdb_id):
    print("📥 Request:", imdb_id)

    title = imdb_to_title(imdb_id)
    if not title:
        return jsonify({"subtitles": []})

    results = search_subtitles(title)

    return jsonify({"subtitles": results})


# ---------------------------------------------------
# RUN
# ---------------------------------------------------
if __name__ == "__main__":
    app.run(host="0.0.0.0", port=10000)
