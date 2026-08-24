"""
CookEase — Flask Backend (User App)
Cleaned version without Admin Dashboard endpoints.
"""

import json
import os
import re
import sqlite3
import uuid

from flask import (
    Flask,
    jsonify,
    make_response,
    render_template,
    request,
    send_from_directory,
    session,
)
from werkzeug.security import check_password_hash, generate_password_hash
from dotenv import load_dotenv

from database import init_db

try:
    import ollama
except ImportError:
    ollama = None


load_dotenv()

app = Flask(__name__, template_folder=".", static_folder=".", static_url_path="")
app.secret_key = os.getenv(
    "SECRET_KEY",
    "cookease_secure_random_secret_key_2026"
)

DB_FILE = "cookease.db"

OLLAMA_HOST = os.getenv("OLLAMA_HOST", "")
CHAT_API_KEY = os.getenv("CHAT_API_KEY", "")
OLLAMA_CHAT_MODEL = os.getenv("OLLAMA_MODEL", "gpt-oss:120b")

chat_client = None
if ollama:
    try:
        if CHAT_API_KEY:
            chat_client = ollama.Client(
                host=OLLAMA_HOST if OLLAMA_HOST else None,
                headers={"Authorization": f"Bearer {CHAT_API_KEY}"}
            )
        else:
            chat_client = ollama.Client(host=OLLAMA_HOST if OLLAMA_HOST else None)
    except Exception as exc:
        print(f"[CookEase] Ollama client initialization failed: {exc}")


init_db()


def get_db_connection():
    conn = sqlite3.connect(DB_FILE)
    conn.row_factory = sqlite3.Row
    conn.execute("PRAGMA foreign_keys = ON")
    return conn


def get_session_id():
    session_id = request.cookies.get("user_session")
    if not session_id:
        session_id = str(uuid.uuid4())
    return session_id


def response_with_session(payload, status=200):
    response = make_response(jsonify(payload), status)
    if not request.cookies.get("user_session"):
        response.set_cookie(
            "user_session",
            get_session_id(),
            max_age=30 * 24 * 60 * 60,
            httponly=True,
            samesite="Lax",
        )
    return response


def get_favorites():
    user_id = session.get("user_id")
    session_id = get_session_id()
    conn = get_db_connection()

    try:
        if user_id:
            rows = conn.execute(
                "SELECT recipe_key FROM user_favorites WHERE user_id = ?",
                (user_id,),
            ).fetchall()
        else:
            rows = conn.execute(
                """
                SELECT recipe_key
                FROM user_favorites
                WHERE session_id = ? AND user_id IS NULL
                """,
                (session_id,),
            ).fetchall()

        return {row["recipe_key"] for row in rows}

    except sqlite3.Error as exc:
        print(f"[CookEase] Favorites read error: {exc}")
        return set()

    finally:
        conn.close()


def safe_json_loads(value, fallback):
    if not value:
        return fallback

    if isinstance(value, (list, dict)):
        return value

    try:
        return json.loads(value)
    except (TypeError, ValueError):
        return fallback


def normalize_text(value):
    return re.sub(r"\s+", " ", str(value or "").strip().lower())


@app.route("/")
def index():
    response = make_response(render_template("index.html"))
    if not request.cookies.get("user_session"):
        response.set_cookie(
            "user_session",
            str(uuid.uuid4()),
            max_age=30 * 24 * 60 * 60,
            httponly=True,
            samesite="Lax",
        )
    return response


@app.route("/images/<path:filename>")
def serve_images(filename):
    return send_from_directory("images", filename)


@app.route("/<path:filename>")
def serve_static(filename):
    return send_from_directory(".", filename)


@app.route("/api/auth/signup", methods=["POST"])
def signup():
    data = request.get_json(silent=True) or {}
    username = str(data.get("username", "")).strip()
    email = str(data.get("email", "")).strip().lower()
    password = str(data.get("password", ""))

    if not username or not email or not password:
        return jsonify({"error": "All fields are required"}), 400

    if len(password) < 6:
        return jsonify({"error": "Password must be at least 6 characters"}), 400

    conn = get_db_connection()

    try:
        cursor = conn.cursor()
        cursor.execute(
            """
            INSERT INTO users (username, email, password_hash)
            VALUES (?, ?, ?)
            """,
            (username, email, generate_password_hash(password)),
        )
        user_id = cursor.lastrowid
        guest_session = get_session_id()

        cursor.execute(
            """
            UPDATE user_favorites
            SET user_id = ?
            WHERE session_id = ? AND user_id IS NULL
            """,
            (user_id, guest_session),
        )

        conn.commit()
        session["user_id"] = user_id
        session["username"] = username

        return response_with_session({
            "message": "Account created successfully",
            "user": {"id": user_id, "username": username},
        })

    except sqlite3.IntegrityError:
        return jsonify({"error": "An account with this email already exists"}), 400

    finally:
        conn.close()


@app.route("/api/auth/login", methods=["POST"])
def login():
    data = request.get_json(silent=True) or {}
    email = str(data.get("email", "")).strip().lower()
    password = str(data.get("password", ""))

    if not email or not password:
        return jsonify({"error": "Email and password are required"}), 400

    conn = get_db_connection()
    try:
        user = conn.execute("SELECT * FROM users WHERE email = ?", (email,)).fetchone()
    finally:
        conn.close()

    if not user or not check_password_hash(user["password_hash"], password):
        return jsonify({"error": "Invalid email or password"}), 401

    session["user_id"] = user["id"]
    session["username"] = user["username"]

    return response_with_session({
        "message": "Logged in successfully",
        "user": {"id": user["id"], "username": user["username"]},
    })


@app.route("/api/auth/logout", methods=["POST"])
def logout():
    session.clear()
    return jsonify({"message": "Logged out successfully"})


@app.route("/api/auth/me")
def get_current_user():
    user_id = session.get("user_id")
    if not user_id:
        return jsonify({"logged_in": False})
    return jsonify({
        "logged_in": True,
        "user": {"id": user_id, "username": session.get("username")},
    })


@app.route("/api/fridge/match", methods=["POST"])
def match_fridge_recipes():
    data = request.get_json(silent=True) or {}
    raw_items = data.get("ingredients", [])
    ingredients = [normalize_text(item) for item in raw_items if normalize_text(item)]

    if not ingredients:
        return jsonify([])

    conn = get_db_connection()
    try:
        recipes = conn.execute("""
            SELECT r.id, r.key, r.title, r.icon, r.tag, r.time, r.kcal, r.desc, r.image, r.image_url
            FROM recipes r ORDER BY r.title ASC
        """).fetchall()

        result = []
        for recipe in recipes:
            recipe_ingredients = conn.execute("""
                SELECT i.name, ri.raw_quantity FROM ingredients i
                JOIN recipe_ingredients ri ON i.id = ri.ingredient_id WHERE ri.recipe_id = ?
            """, (recipe["id"],)).fetchall()

            names = [normalize_text(row["name"]) for row in recipe_ingredients]
            matched = [req for req in ingredients if any(req in name or name in req for name in names)]
            matched = list(dict.fromkeys(matched))

            if not matched:
                continue

            total = len(names) if names else len(ingredients)
            match_percentage = round(min(100, (len(matched) / max(1, total)) * 100))

            result.append({
                "key": recipe["key"], "title": recipe["title"], "icon": recipe["icon"] or "🍲",
                "image": recipe["image"] or recipe["image_url"], "tag": recipe["tag"],
                "time": recipe["time"], "kcal": recipe["kcal"], "desc": recipe["desc"],
                "favorited": recipe["key"] in get_favorites(), "matched_count": len(matched),
                "match_percentage": match_percentage, "matched_ingredients": matched,
            })

        result.sort(key=lambda item: (-item["match_percentage"], -item["matched_count"], item["title"].lower()))
        return jsonify(result[:30])
    finally:
        conn.close()


@app.route("/api/ai-chef/chat", methods=["POST"])
def ai_chef_chat():
    data = request.get_json(silent=True) or {}
    user_message = str(data.get("message", "")).strip()
    if not user_message:
        return jsonify({"error": "Prompt message is required"}), 400

    if not chat_client:
        return jsonify({"error": "Ollama is not available."}), 503

    conn = get_db_connection()
    try:
        search_term = f"%{normalize_text(user_message)}%"
        rows = conn.execute("""
            SELECT DISTINCT r.title, r.desc, r.kcal, r.time FROM recipes r
            LEFT JOIN recipe_ingredients ri ON r.id = ri.recipe_id
            LEFT JOIN ingredients i ON ri.ingredient_id = i.id
            WHERE LOWER(r.title) LIKE ? OR LOWER(i.name) LIKE ? LIMIT 5
        """, (search_term, search_term)).fetchall()
    finally:
        conn.close()

    recipe_context = "Database Matched Recipes:\n" if rows else ""
    for row in rows:
        recipe_context += f"- {row['title']} | {row['time']} | {row['kcal']} kcal | {row['desc']}\n"

    system_prompt = f"You are CookEase, a 100% PURE VEGETARIAN culinary assistant. Only answer food/cooking questions.\n{recipe_context}"

    try:
        response = chat_client.chat(model=OLLAMA_CHAT_MODEL, messages=[{"role": "system", "content": system_prompt}, {"role": "user", "content": user_message}])
        return jsonify({"reply": response["message"]["content"]})
    except Exception as exc:
        print(f"AI CHAT ERROR: {exc}")
        return jsonify({"error": f"Could not connect to AI model: {exc}"}), 500


@app.route("/api/ai-chef/generate-recipe", methods=["POST"])
def generate_ai_recipe():
    data = request.get_json(silent=True) or {}
    ingredients = data.get("ingredients", [])
    if not ingredients or not chat_client:
        return jsonify({"error": "Invalid request or Ollama unavailable."}), 400

    prompt = f"Create a delicious PURE VEGETARIAN recipe using: {', '.join(map(str, ingredients))}."
    try:
        response = chat_client.chat(model=OLLAMA_CHAT_MODEL, messages=[{"role": "user", "content": prompt}])
        return jsonify({"recipe_markdown": response["message"]["content"]})
    except Exception as exc:
        print(f"GENERATE RECIPE ERROR: {exc}")
        return jsonify({"error": f"Failed to generate recipe: {exc}"}), 500


def recipe_summary(row, favorites):
    return {
        "key": row["key"], "title": row["title"], "icon": row["icon"] or "🌱",
        "image": row["image"] or row["image_url"], "tag": row["tag"],
        "time": row["time"], "kcal": row["kcal"], "desc": row["desc"],
        "favorited": row["key"] in favorites,
    }


@app.route("/api/recipes/roulette")
def roulette_pick():
    conn = get_db_connection()
    try:
        recipe = conn.execute("SELECT * FROM recipes ORDER BY RANDOM() LIMIT 1").fetchone()
    finally:
        conn.close()
    if not recipe: return jsonify({"error": "No recipes found"}), 404
    return jsonify(recipe_summary(recipe, get_favorites()))


@app.route("/api/recipes/todays-pick")
def todays_pick():
    conn = get_db_connection()
    try:
        recipe = conn.execute("SELECT * FROM recipes ORDER BY RANDOM() LIMIT 1").fetchone()
    finally:
        conn.close()
    if not recipe: return jsonify({"error": "No recipes found"}), 404
    return jsonify({"key": recipe["key"], "title": recipe["title"], "kcal": recipe["kcal"], "time": recipe["time"], "image": recipe["image"] or recipe["image_url"], "icon": recipe["icon"] or "🌱"})


@app.route("/api/recipes/search")
def search_recipes():
    q = normalize_text(request.args.get("q", ""))
    tag = normalize_text(request.args.get("tag", "all"))
    conn = get_db_connection()
    try:
        params, query = [], "SELECT DISTINCT r.id, r.key, r.title, r.icon, r.tag, r.time, r.kcal, r.desc, r.image, r.image_url FROM recipes r"
        if tag == "favorites":
            user_id = session.get("user_id")
            session_id = get_session_id()
            query += " INNER JOIN user_favorites uf ON r.key = uf.recipe_key WHERE "
            if user_id: query += " uf.user_id = ? "; params.append(user_id)
            else: query += " uf.session_id = ? AND uf.user_id IS NULL "; params.append(session_id)
        else:
            query += " WHERE 1=1 "
            if tag not in ("", "all", "daily", "quick"):
                query += " AND LOWER(r.tag) LIKE ? "
                params.append(f"%{tag}%")
        if q:
            query += " AND (LOWER(r.title) LIKE ? OR LOWER(r.desc) LIKE ?)"
            params.extend([f"%{q}%", f"%{q}%"])
        rows = conn.execute(query + " ORDER BY r.id ASC", params).fetchall()
    finally:
        conn.close()

    favorites = get_favorites()
    return response_with_session([recipe_summary(row, favorites) for row in rows])


@app.route("/api/recipes/<key>")
def get_recipe_detail(key):
    conn = get_db_connection()
    try:
        recipe = conn.execute("SELECT * FROM recipes WHERE key = ?", (key,)).fetchone()
        if not recipe: return jsonify({"error": "Recipe not found"}), 404
        ingredients = conn.execute("SELECT i.name, ri.raw_quantity FROM ingredients i JOIN recipe_ingredients ri ON i.id = ri.ingredient_id WHERE ri.recipe_id = ? ORDER BY ri.ingredient_id ASC", (recipe["id"],)).fetchall()
    finally:
        conn.close()

    return jsonify({
        "key": recipe["key"], "title": recipe["title"], "icon": recipe["icon"] or "🌱",
        "image": recipe["image"] or recipe["image_url"], "tag": recipe["tag"],
        "time": recipe["time"], "kcal": recipe["kcal"], "desc": recipe["desc"],
        "favorited": recipe["key"] in get_favorites(),
        "nutrition": safe_json_loads(recipe["nutrition"], {"calories": f"{recipe['kcal']} kcal"}),
        "ingredients": [{"name": i["name"], "quantity": i["raw_quantity"] or "", "icon": "🥦"} for i in ingredients],
        "instructions": safe_json_loads(recipe["instructions"], [])
    })


@app.route("/api/favorites/<key>", methods=["POST"])
def toggle_favorite(key):
    user_id = session.get("user_id")
    session_id = get_session_id()
    conn = get_db_connection()
    try:
        recipe = conn.execute("SELECT 1 FROM recipes WHERE key = ?", (key,)).fetchone()
        if not recipe: return jsonify({"error": "Recipe not found"}), 404

        if user_id:
            existing = conn.execute("SELECT 1 FROM user_favorites WHERE user_id = ? AND recipe_key = ?", (user_id, key)).fetchone()
            if existing:
                conn.execute("DELETE FROM user_favorites WHERE user_id = ? AND recipe_key = ?", (user_id, key))
                is_fav = False
            else:
                conn.execute("INSERT OR IGNORE INTO user_favorites (user_id, session_id, recipe_key) VALUES (?, NULL, ?)", (user_id, key))
                is_fav = True
        else:
            existing = conn.execute("SELECT 1 FROM user_favorites WHERE session_id = ? AND recipe_key = ? AND user_id IS NULL", (session_id, key)).fetchone()
            if existing:
                conn.execute("DELETE FROM user_favorites WHERE session_id = ? AND recipe_key = ? AND user_id IS NULL", (session_id, key))
                is_fav = False
            else:
                conn.execute("INSERT OR IGNORE INTO user_favorites (user_id, session_id, recipe_key) VALUES (NULL, ?, ?)", (session_id, key))
                is_fav = True
        conn.commit()
        return response_with_session({"key": key, "favorited": is_fav})
    finally:
        conn.close()


if __name__ == "__main__":
    print("======================================")
    print(" CookEase Flask Server (app.py - Port 5000)")
    print(" http://127.0.0.1:5000")
    print("======================================")
    app.run(debug=True, port=5000)