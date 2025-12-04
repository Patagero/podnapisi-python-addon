from flask import Flask, jsonify, request
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

    title = tag["content"]
    clean = re.sub(r"\(\d{4}\).*", "", title).strip()
    return clean


# ---------------------------------------------------
# SEARCH – Using MOVIE PAGE (NO LOGIN REQUIRED)
# ---------------------------------------------------
def search_movie(title):
    print("🔍 Searching movie:", title)

    # Example: https://www.podnapisi.net/sl/movie/titanic-1997
    url = f"{BASE}/sl/movie?keywords={title}"

    r = requests.get(url, headers={"User-Agent": "Mozilla/5.0"})
    if r.status_code != 200:
        print("❌ Movie search failed")
        return []

    soup = BeautifulSoup(r.text, "html.parser")

    # All movies matching title
    links = soup.select("a[href*='/sl/movie/']")

    movies = []
    for a in links:
        href = a.get("href")
        if "/sl/movie/" in href and "edit" not in href:
            movies.append(BASE + href)

    print("🎬 Movie candidates found:", len(movies))
    return movies


# ---------------------------------------------------
# Extract subtitles from a MOVIE PAGE
# ---------------------------------------------------
def extract_subtitles(movie_url):
    print("📄 Checking movie page:", movie_url)

    r = requests.get(movie_url, headers={"User-Agent": "Mozilla/5.0"})
    if r.status_code != 200:
        print("❌ Cannot load movie page")
        return []

    soup = BeautifulSoup(r.text, "html.parser")

    rows = soup.select("table tbody tr")

    subs = []

    for row in rows:
        lang = row.select_one("td:nth-child(4) img")
        if not lang:
            continue

        if "sl" not in lang.get("src", ""):
            continue  # only Slovenian

        link = row.select_one("a[href*='/sl/subtitles/']")
        if not link:
            continue

        sub_url = BASE + link.get("href")
        name = link.text.strip()

        subs.append({
            "name": name,
            "url": sub_url + "/download"
        })

    print("📦 Found subtitles:", len(subs))
    return subs


# ---------------------------------------------------
# Download ZIP → SRT text
# ---------------------------------------------------
def download_srt(url):
    print("⬇ Downloading:", url)

    r = requests.get(url, headers={"User-Agent": "Mozilla/5.0"})
    if r.status_code != 200:
        print("❌ Cannot download file")
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
        "version": "2.0.0",
        "name": "Podnapisi.NET 🇸🇮 Python Addon (No Login)",
        "description": "Slovenski podnapisi iz Podnapisi.NET – brez Chromium, brez logina.",
        "types": ["movie", "series"],
        "idPrefixes": ["tt"],
        "resources": ["subtitles"]
    })


# ---------------------------------------------------
# SUBTITLES ENDPOINT
# ---------------------------------------------------
@app.route("/subtitles/<video_type>/<imdb>.json")
def subtitles(video_type, imdb):

    print("🎬 IMDb:", imdb)

    title = imdb_to_title(imdb)
    if not title:
        return jsonify({"subtitles": []})

    print("🎞 Title:", title)

    movies = search_movie(title)
    if not movies:
        return jsonify({"subtitles": []})

    # Use first match
    movie_url = movies[0]

    subs = extract_subtitles(movie_url)
    out = []

    for s in subs:
        content = download_srt(s["url"])
        if not content:
            continue

        out.append({
            "lang": "sl",
            "title": s["name"],
            "id": s["name"],
            "subtitles": content
        })

    return jsonify({"subtitles": out})


# ---------------------------------------------------
# RUN
# ---------------------------------------------------
if __name__ == "__main__":
    app.run(host="0.0.0.0", port=10000)
