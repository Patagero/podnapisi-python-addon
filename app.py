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


# ---------------------------------------------------------
# IMDb → Title (TMDB free API – no key needed)
# ---------------------------------------------------------
def imdb_to_title(imdb_id):
    url = (
        f"https://api.themoviedb.org/3/find/{imdb_id}"
        f"?external_source=imdb_id&api_key=730b8680e6fb1d80b3d5bc1a58b2d2f0"
    )

    print("🔎 TMDB lookup:", url)
    data = requests.get(url).json()

    if data.get("movie_results"):
        movie = data["movie_results"][0]
        title = movie.get("title", imdb_id)
        year = movie.get("release_date", "")[:4]
        combo = f"{title} {year}".strip()
        print("🎬 Title:", combo)
        return combo

    if data.get("tv_results"):
        tv = data["tv_results"][0]
        title = tv.get("name", imdb_id)
        year = tv.get("first_air_date", "")[:4]
        combo = f"{title} {year}".strip()
        print("📺 Series Title:", combo)
        return combo

    print("⚠️ TMDB found nothing — fallback to IMDB ID")
    return imdb_id


# ---------------------------------------------------------
# LOGIN (FULL CLOUDLARE-SAFE VERSION)
# ---------------------------------------------------------
def login_if_needed():
    global cookies_loaded
    if cookies_loaded:
        return

    print("🔐 Fetching login page...")

    headers = {
        "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120 Safari/537.36",
        "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,*/*;q=0.8",
        "Referer": LOGIN_URL,
    }

    r = session.get(LOGIN_URL, headers=headers)
    soup = BeautifulSoup(r.text, "lxml")

    token_tag = soup.find("input", {"name": "_token"})
    if not token_tag:
        print("❌ CSRF token not found")
        return

    csrf_token = token_tag["value"]
    print("🔑 CSRF token:", csrf_token)

    payload = {
        "_token": csrf_token,
        "username": USERNAME,
        "password": PASSWORD,
    }

    headers_post = {
        "User-Agent": headers["User-Agent"],
        "Referer": LOGIN_URL,
        "Origin": "https://www.podnapisi.net",
        "Content-Type": "application/x-www-form-urlencoded",
    }

    print(f"🔐 Logging in as: {USERNAME}")
    resp = session.post(LOGIN_URL, headers=headers_post, data=payload, allow_redirects=True)

    if "Odjava" in resp.text or USERNAME.lower() in resp.text.lower():
        print("✅ Login successful")
        cookies_loaded = True
        return

    print("❌ Login failed")
    print(resp.text[:500])


# ---------------------------------------------------------
# FIND SUBTITLES
# ---------------------------------------------------------
def find_subtitles(imdb_id):
    login_if_needed()

    query = imdb_to_title(imdb_id)
    print("🔍 Searching Podnapisi.NET for:", query)

    url = SEARCH_URL.format(query.replace(" ", "+"))
    print("🔗 Search URL:", url)

    r = session.get(url)
    soup = BeautifulSoup(r.text, "lxml")

    rows = soup.select("table.table tbody tr")
    results = []

    for row in rows:
        a = row.find("a", href=True)
        if not a or "/download" not in a["href"]:
            continue

        href = "https://www.podnapisi.net" + a["href"]
        name = a.text.strip()

        results.append({"title": name, "link": href})

    print(f"✅ Found {len(results)} results")
    return results


# ---------------------------------------------------------
# ZIP → SRT
# ---------------------------------------------------------
def extract_srt_from_zip(url):
    try:
        print("⬇️ Downloading ZIP:", url)
        r = session.get(url)

        tmp_zip = tempfile.NamedTemporaryFile(delete=False, suffix=".zip")
        tmp_zip.write(r.content)
        tmp_zip.close()

        out_dir = tempfile.mkdtemp()

        with zipfile.ZipFile(tmp_zip.name, "r") as z:
            z.extractall(out_dir)

        for f in os.listdir(out_dir):
            if f.endswith(".srt"):
                return os.path.join(out_dir, f)

        return None
    except Exception as e:
        print("⚠️ ZIP error:", e)
        return None


# ---------------------------------------------------------
# ROUTES
# ---------------------------------------------------------
@app.route("/manifest.json")
def manifest():
    return jsonify({
        "id": "org.formio.podnapisi.python",
        "name": "Podnapisi.NET 🇸🇮 Python Addon",
        "version": "1.0.0",
        "description": "Slovenski podnapisi iz Podnapisi.NET (Python brez Chromium).",
        "types": ["movie", "series"],
        "resources": ["subtitles"],
        "idPrefixes": ["tt"]
    })


@app.route("/subtitles/<stype>/<imdb_id>/<path:rest>.json")
def subtitles_rest(stype, imdb_id, rest):
    return subtitles(stype, imdb_id)


@app.route("/subtitles/<stype>/<imdb_id>.json")
def subtitles(stype, imdb_id):
    print("🎬 Subtitles request for:", imdb_id)

    found = find_subtitles(imdb_id)

    base = os.getenv(
        "RENDER_EXTERNAL_URL",
        f"https://{os.getenv('RENDER_EXTERNAL_HOSTNAME', 'podnapisi-python-addon.onrender.com')}"
    )

    out = []
    idx = 1

    for sub in found:
        srt_file = extract_srt_from_zip(sub["link"])
        if not srt_file:
            continue

        fname = os.path.basename(srt_file)
        url = f"{base}/file/{fname}"

        out.append({
            "id": f"srt-{idx}",
            "lang": "sl",
            "title": f"🇸🇮 {sub['title']}",
            "url": url
        })
        idx += 1

    return jsonify({"subtitles": out})


@app.route("/file/<filename>")
def serve_file(filename):
    tmp = tempfile.gettempdir()

    for root, dirs, files in os.walk(tmp):
        if filename in files:
            return send_file(os.path.join(root, filename))

    return "Not found", 404


# ---------------------------------------------------------
# RUN
# ---------------------------------------------------------
if __name__ == "__main__":
    port = int(os.getenv("PORT", 7000))
    print(f"🚀 Starting Flask on {port}")
    app.run(host="0.0.0.0", port=port)
