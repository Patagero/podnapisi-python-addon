import os
import json
import requests
import zipfile
import tempfile
from flask import Flask, jsonify, send_file
from bs4 import BeautifulSoup
from flask_cors import CORS

USERNAME = os.getenv("PODNAPISI_USER", "")
PASSWORD = os.getenv("PODNAPISI_PASS", "")

LOGIN_URL = "https://www.podnapisi.net/sl/login"
SEARCH_URL = "https://www.podnapisi.net/sl/subtitles/search/?keywords={}&language=sl"

session = requests.Session()
cookies_loaded = False

app = Flask(__name__)
CORS(app, resources={r"/*": {"origins": "*"}})


# -----------------------------------
# TMDB: Convert IMDB → Title
# -----------------------------------
def imdb_to_title(imdb_id):
    url = (
        f"https://api.themoviedb.org/3/find/{imdb_id}"
        f"?external_source=imdb_id&api_key=730b8680e6fb1d80b3d5bc1a58b2d2f0"
    )

    print("🔎 TMDB lookup:", url)
    data = requests.get(url).json()

    # Movie result
    if data.get("movie_results"):
        movie = data["movie_results"][0]
        title = movie.get("title", imdb_id)
        year = movie.get("release_date", "")[:4]
        combo = f"{title} {year}".strip()
        print("🎬 TMDB Title:", combo)
        return combo

    # TV series result
    if data.get("tv_results"):
        tv = data["tv_results"][0]
        title = tv.get("name", imdb_id)
        year = tv.get("first_air_date", "")[:4]
        combo = f"{title} {year}".strip()
        print("📺 TMDB Series Title:", combo)
        return combo

    return imdb_id  # fallback


# -----------------------------------
# LOGIN
# -----------------------------------
def login_if_needed():
    global cookies_loaded
    if cookies_loaded:
        return

    print("🔐 Logging into Podnapisi.NET...")

    resp = session.get(LOGIN_URL)
    soup = BeautifulSoup(resp.text, "lxml")

    token = soup.find("input", {"name": "_token"})
    if not token:
        print("⚠️ Login token missing")
        return

    payload = {
        "_token": token["value"],
        "username": USERNAME,
        "password": PASSWORD
    }

    session.post(LOGIN_URL, data=payload)
    cookies_loaded = True
    print("✅ Login OK")


# -----------------------------------
# FIND SUBTITLES
# -----------------------------------
def find_subtitles(imdb_id):
    login_if_needed()

    search_query = imdb_to_title(imdb_id)
    print("🔍 Searching Podnapisi.NET for:", search_query)

    url = SEARCH_URL.format(search_query)
    print("🔗 Query URL:", url)

    r = session.get(url)
    soup = BeautifulSoup(r.text, "lxml")

    results = []
    rows = soup.select("table.table tbody tr")

    for row in rows:
        a = row.find("a", href=True)
        if not a or "/download" not in a["href"]:
            continue

        full = "https://www.podnapisi.net" + a["href"]
        name = a.text.strip()

        results.append({
            "title": name,
            "link": full
        })

    print(f"✅ Found {len(results)} subtitles")
    return results


# -----------------------------------
# ZIP → SRT extract
# -----------------------------------
def extract_srt_from_zip(url):
    try:
        print("⬇️ Downloading ZIP:", url)
        r = session.get(url)

        tmp_zip = tempfile.NamedTemporaryFile(delete=False, suffix=".zip")
        tmp_zip.write(r.content)
        tmp_zip.close()

        extract_dir = tempfile.mkdtemp()

        with zipfile.ZipFile(tmp_zip.name, "r") as z:
            z.extractall(extract_dir)

        for file in os.listdir(extract_dir):
            if file.endswith(".srt"):
                return os.path.join(extract_dir, file)

        return None

    except Exception as e:
        print("⚠️ ZIP error:", e)
        return None


# -----------------------------------
# ROUTES
# -----------------------------------
@app.route("/manifest.json")
def manifest():
    return jsonify({
        "id": "org.formio.podnapisi.python",
        "version": "1.0.0",
        "name": "Podnapisi.NET 🇸🇮 Python Addon",
        "description": "Slovenski podnapisi iz Podnapisi.NET (Python brez Chromium).",
        "types": ["movie", "series"],
        "resources": ["subtitles"],
        "idPrefixes": ["tt"]
    })


# Stremio 5 URL format
@app.route("/subtitles/<stype>/<imdb_id>/<path:rest>.json")
def subtitles_rest(stype, imdb_id, rest):
    return subtitles(stype, imdb_id)


# Stremio 4 URL format
@app.route("/subtitles/<stype>/<imdb_id>.json")
def subtitles(stype, imdb_id):
    print("🎬 Request for IMDB:", imdb_id)

    results = find_subtitles(imdb_id)

    base = os.getenv(
        "RENDER_EXTERNAL_URL",
        f"https://{os.getenv('RENDER_EXTERNAL_HOSTNAME', 'podnapisi-python-addon.onrender.com')}"
    )

    out = []
    idx = 1

    for r in results:
        srt = extract_srt_from_zip(r["link"])
        if not srt:
            continue

        fname = os.path.basename(srt)
        url = f"{base}/file/{fname}"

        out.append({
            "id": f"srt-{idx}",
            "lang": "sl",
            "title": f"🇸🇮 {r['title']}",
            "url": url
        })
        idx += 1

    return jsonify({"subtitles": out})


@app.route("/file/<filename>")
def serve_srt(filename):
    tmp = tempfile.gettempdir()

    for root, dirs, files in os.walk(tmp):
        if filename in files:
            return send_file(os.path.join(root, filename), as_attachment=False)

    return "Not found", 404


# -----------------------------------
# RUN SERVER
# -----------------------------------
if __name__ == "__main__":
    port = int(os.getenv("PORT", 7000))
    print(f"🚀 Starting Flask on 0.0.0.0:{port}")
    app.run(host="0.0.0.0", port=port)
