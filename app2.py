"""
app2.py — CookEase Full Application + Secure Admin Dashboard (ID & Password)
Runs on port 5001 with direct publishing support for admins and active Ollama chatbot.
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

# Fixed variable name to 'app' so Gunicorn can detect it properly on Render (`gunicorn app2:app`)
app = Flask(__name__, template_folder=".", static_folder=".", static_url_path="")
app.secret_key = os.getenv("SECRET_KEY", "cookease_secure_random_secret_key_2026")

DB_FILE = "cookease.db"
JSON_FILE = "recipes_output.json"

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
            rows = conn.execute("SELECT recipe_key FROM user_favorites WHERE user_id = ?", (user_id,)).fetchall()
        else:
            rows = conn.execute("SELECT recipe_key FROM user_favorites WHERE session_id = ? AND user_id IS NULL", (session_id,)).fetchall()
        return {row["recipe_key"] for row in rows}
    except sqlite3.Error:
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
    response = make_response(render_template("index2.html"))
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


ADMIN_CREDENTIALS = {
    "Prasheel": "prasheel123",
    "Manan": "manan123",
    "Veer": "veer123",
    "Gunja": "gunja123",
    "Hetakshi": "hetakshi123"
}


@app.route("/api/auth/signup", methods=["POST"])
def signup():
    data = request.get_json(silent=True) or {}
    username = str(data.get("username", "")).strip()
    email = str(data.get("email", "")).strip().lower()
    password = str(data.get("password", ""))

    if not username or not email or not password:
        return jsonify({"error": "All fields are required"}), 400

    conn = get_db_connection()
    try:
        cursor = conn.cursor()
        cursor.execute("INSERT INTO users (username, email, password_hash) VALUES (?, ?, ?)", (username, email, generate_password_hash(password)))
        user_id = cursor.lastrowid
        conn.commit()
        session["user_id"] = user_id
        session["username"] = username
        return response_with_session({"message": "Success", "user": {"id": user_id, "username": username}})
    except sqlite3.IntegrityError:
        return jsonify({"error": "Email already exists"}), 400
    finally:
        conn.close()


@app.route("/api/auth/login", methods=["POST"])
def login():
    data = request.get_json(silent=True) or {}
    email = str(data.get("email", "")).strip().lower()
    password = str(data.get("password", ""))

    conn = get_db_connection()
    user = conn.execute("SELECT * FROM users WHERE email = ?", (email,)).fetchone()
    conn.close()

    if not user or not check_password_hash(user["password_hash"], password):
        return jsonify({"error": "Invalid email or password"}), 401

    session["user_id"] = user["id"]
    session["username"] = user["username"]
    return response_with_session({"message": "Logged in", "user": {"id": user["id"], "username": user["username"]}})


@app.route("/api/auth/logout", methods=["POST"])
def logout():
    session.clear()
    return jsonify({"message": "Logged out"})


@app.route("/api/auth/me")
def get_current_user():
    user_id = session.get("user_id")
    if not user_id:
        return jsonify({"logged_in": False})
    return jsonify({"logged_in": True, "user": {"id": user_id, "username": session.get("username")}})


@app.route("/api/admin/login", methods=["POST"])
def admin_login():
    data = request.get_json(silent=True) or {}
    admin_id = str(data.get("id", "")).strip().capitalize()
    password = str(data.get("password", "")).strip()

    if admin_id in ADMIN_CREDENTIALS and ADMIN_CREDENTIALS[admin_id] == password:
        session["is_admin"] = True
        session["admin_name"] = admin_id
        return jsonify({"message": f"Welcome Admin, {admin_id}!", "admin": admin_id})

    return jsonify({"error": "Invalid Admin ID or Password. Access denied."}), 403


@app.route("/api/admin/check")
def check_admin():
    return jsonify({"is_admin": bool(session.get("is_admin")), "admin_name": session.get("admin_name")})


@app.route("/api/admin/logout", methods=["POST"])
def admin_logout():
    session.pop("is_admin", None)
    session.pop("admin_name", None)
    return jsonify({"message": "Logged out of admin panel"})


@app.route("/api/recipes/submit", methods=["POST"])
def submit_recipe():
    user_id = session.get("user_id")
    username = session.get("username")
    is_admin = session.get("is_admin", False)

    if not user_id or not username:
        return jsonify({"error": "You must be logged in to submit recipes."}), 401

    data = request.get_json(silent=True) or {}
    title = str(data.get("title", "")).strip()
    tag = str(data.get("tag", "main course")).strip().lower()
    time = str(data.get("time", "30m")).strip()
    desc = str(data.get("desc", "")).strip()
    instructions = data.get("instructions", "")
    kcal = data.get("kcal", 350)

    if not title or not desc:
        return jsonify({"error": "Title and description required"}), 400

    conn = get_db_connection()

    if is_admin:
        recipe_key = re.sub(r"[^a-z0-9]+", "_", title.lower()).strip("_")
        icon = "🍞" if tag == "bakery" else ("🥤" if tag == "beverages" else "🥘")
        instructions_list = instructions if isinstance(instructions, list) else [str(instructions)]
        nutrition_dict = {"calories": f"{kcal} kcal", "carbs": "20g", "protein": "8g", "fat": "15g"}

        try:
            conn.execute("""
                INSERT OR IGNORE INTO recipes (key, title, tag, time, kcal, desc, image_url, icon, instructions, nutrition)
                VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            """, (recipe_key, title, tag, time, kcal, desc,
                  "https://images.unsplash.com/photo-1540420773420-3366772f4999?auto=format&fit=crop&w=600&q=80",
                  icon, json.dumps(instructions_list), json.dumps(nutrition_dict)))
            conn.commit()

            recipes_list = []
            if os.path.exists(JSON_FILE):
                with open(JSON_FILE, "r", encoding="utf-8") as jf:
                    try: recipes_list = json.load(jf)
                    except: recipes_list = []

            new_recipe = {
                "key": recipe_key, "title": title, "tag": tag,
                "time": time, "kcal": kcal, "desc": desc,
                "image_url": "https://images.unsplash.com/photo-1540420773420-3366772f4999?auto=format&fit=crop&w=600&q=80",
                "icon": icon, "instructions": instructions_list, "nutrition": nutrition_dict
            }
            if not any(r.get("key") == recipe_key for r in recipes_list):
                recipes_list.append(new_recipe)
                with open(JSON_FILE, "w", encoding="utf-8") as jf:
                    json.dump(recipes_list, jf, indent=2)

            conn.close()
            return jsonify({"message": "Admin direct publish: Recipe added and published immediately!"})
        except Exception as exc:
            conn.close()
            return jsonify({"error": str(exc)}), 500

    existing = conn.execute("SELECT title FROM recipes").fetchall()
    existing_titles = [row["title"] for row in existing]
    ai_status, ai_reason = "New", "Unique recipe structure."

    if chat_client:
        try:
            prompt = f"Analyze Title: {title}. Existing: {', '.join(existing_titles)}. Return JSON with keys 'status' ('New' or 'Copied') and 'reason'."
            response = chat_client.chat(model=OLLAMA_CHAT_MODEL, messages=[{"role": "user", "content": prompt}])
            reply = response["message"]["content"].strip()
            start, end = reply.find("{"), reply.rfind("}")
            if start >= 0 and end > start:
                ai_data = json.loads(reply[start:end + 1])
                if ai_data.get("status") in {"New", "Copied"}:
                    ai_status = ai_data["status"]
                ai_reason = str(ai_data.get("reason", "Analyzed by AI."))
        except Exception as exc:
            print(f"Ollama error: {exc}")

    instructions_json = json.dumps(instructions) if isinstance(instructions, list) else json.dumps([str(instructions)])

    conn.execute("""
        INSERT INTO recipe_submissions (title, tag, time, kcal, desc, instructions, submitted_by, ai_status, ai_reason, approval_status, rejection_reason)
        VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, 'Pending', '')
    """, (title, tag, time, kcal, desc, instructions_json, username, ai_status, ai_reason))
    conn.commit()
    conn.close()

    return jsonify({"message": "Recipe submitted successfully for admin approval!", "ai_analysis": {"status": ai_status, "reason": ai_reason}})


@app.route("/api/recipes/my-submissions")
def get_my_submissions():
    user_id = session.get("user_id")
    username = session.get("username")
    
    if not user_id or not username:
        return jsonify({"error": "Unauthorized"}), 401
        
    conn = get_db_connection()
    try:
        rows = conn.execute(
            "SELECT title, tag, time, kcal, approval_status, rejection_reason FROM recipe_submissions WHERE submitted_by = ? ORDER BY id DESC",
            (username,)
        ).fetchall()
        return jsonify([dict(row) for row in rows])
    finally:
        conn.close()


@app.route("/api/admin/submissions")
def get_admin_submissions():
    if not session.get("is_admin"):
        return jsonify({"error": "Unauthorized"}), 403
    conn = get_db_connection()
    rows = conn.execute("SELECT * FROM recipe_submissions ORDER BY id DESC").fetchall()
    conn.close()
    return jsonify([dict(row) for row in rows])


@app.route("/api/admin/submissions/<int:sub_id>/approve", methods=["POST"])
def approve_submission(sub_id):
    if not session.get("is_admin"):
        return jsonify({"error": "Unauthorized"}), 403

    conn = get_db_connection()
    sub = conn.execute("SELECT * FROM recipe_submissions WHERE id = ?", (sub_id,)).fetchone()
    if not sub:
        conn.close()
        return jsonify({"error": "Not found"}), 404

    recipe_key = re.sub(r"[^a-z0-9]+", "_", sub["title"].lower()).strip("_")
    icon = "🍞" if sub["tag"] == "bakery" else ("🥤" if sub["tag"] == "beverages" else "🥘")
    instructions = safe_json_loads(sub["instructions"], [])
    nutrition_dict = {"calories": f"{sub['kcal']} kcal", "carbs": "20g", "protein": "8g", "fat": "15g"}

    try:
        conn.execute("""
            INSERT OR IGNORE INTO recipes (key, title, tag, time, kcal, desc, image_url, icon, instructions, nutrition)
            VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
        """, (recipe_key, sub["title"], sub["tag"], sub["time"], sub["kcal"], sub["desc"],
              "https://images.unsplash.com/photo-1540420773420-3366772f4999?auto=format&fit=crop&w=600&q=80",
              icon, json.dumps(instructions), json.dumps(nutrition_dict)))
        
        conn.execute("UPDATE recipe_submissions SET approval_status = 'Approved' WHERE id = ?", (sub_id,))
        conn.commit()

        recipes_list = []
        if os.path.exists(JSON_FILE):
            with open(JSON_FILE, "r", encoding="utf-8") as jf:
                try: recipes_list = json.load(jf)
                except: recipes_list = []

        new_recipe = {
            "key": recipe_key, "title": sub["title"], "tag": sub["tag"],
            "time": sub["time"], "kcal": sub["kcal"], "desc": sub["desc"],
            "image_url": "https://images.unsplash.com/photo-1540420773420-3366772f4999?auto=format&fit=crop&w=600&q=80",
            "icon": icon, "instructions": instructions, "nutrition": nutrition_dict
        }
        if not any(r.get("key") == recipe_key for r in recipes_list):
            recipes_list.append(new_recipe)
            with open(JSON_FILE, "w", encoding="utf-8") as jf:
                json.dump(recipes_list, jf, indent=2)

    except Exception as exc:
        conn.close()
        return jsonify({"error": str(exc)}), 500

    conn.close()
    return jsonify({"message": "Approved and published successfully!"})


@app.route("/api/admin/submissions/<int:sub_id>/reject", methods=["POST"])
def reject_submission(sub_id):
    if not session.get("is_admin"):
        return jsonify({"error": "Unauthorized"}), 403
    data = request.get_json(silent=True) or {}
    reason = str(data.get("reason", "No reason provided.")).strip()

    conn = get_db_connection()
    conn.execute("UPDATE recipe_submissions SET approval_status = 'Rejected', rejection_reason = ? WHERE id = ?", (reason, sub_id))
    conn.commit()
    conn.close()
    return jsonify({"message": "Rejected with reason."})


@app.route("/api/fridge/match", methods=["POST"])
def match_fridge_recipes():
    data = request.get_json(silent=True) or {}
    raw_items = data.get("ingredients", [])
    ingredients = [normalize_text(i) for i in raw_items if normalize_text(i)]
    if not ingredients: return jsonify([])

    conn = get_db_connection()
    try:
        recipes = conn.execute("SELECT * FROM recipes ORDER BY title ASC").fetchall()
        result = []
        for recipe in recipes:
            result.append({
                "key": recipe["key"], "title": recipe["title"], "icon": recipe["icon"] or "🍲",
                "image": recipe["image"] or recipe["image_url"], "tag": recipe["tag"],
                "time": recipe["time"], "kcal": recipe["kcal"], "desc": recipe["desc"],
                "favorited": recipe["key"] in get_favorites(), "match_percentage": 85
            })
        return jsonify(result[:30])
    finally:
        conn.close()


@app.route("/api/recipes/search")
def search_recipes():
    q = normalize_text(request.args.get("q", ""))
    tag = normalize_text(request.args.get("tag", "all"))
    conn = get_db_connection()
    try:
        query, params = "SELECT * FROM recipes WHERE 1=1", []
        if tag not in ("", "all"):
            query += " AND LOWER(tag) LIKE ?"
            params.append(f"%{tag}%")
        if q:
            query += " AND (LOWER(title) LIKE ? OR LOWER(desc) LIKE ?)"
            params.extend([f"%{q}%", f"%{q}%"])
        rows = conn.execute(query, params).fetchall()
    finally:
        conn.close()

    favorites = get_favorites()
    return response_with_session([{
        "key": r["key"], "title": r["title"], "icon": r["icon"] or "🌱",
        "image": r["image"] or r["image_url"], "tag": r["tag"],
        "time": r["time"], "kcal": r["kcal"], "desc": r["desc"],
        "favorited": r["key"] in favorites
    } for r in rows])


@app.route("/api/recipes/<key>")
def get_recipe_detail(key):
    conn = get_db_connection()
    try:
        recipe = conn.execute("SELECT * FROM recipes WHERE key = ?", (key,)).fetchone()
        if not recipe: return jsonify({"error": "Not found"}), 404
        ingredients = conn.execute("SELECT i.name, ri.raw_quantity FROM ingredients i JOIN recipe_ingredients ri ON i.id = ri.ingredient_id WHERE ri.recipe_id = ?", (recipe["id"],)).fetchall()
    finally:
        conn.close()

    return jsonify({
        "key": recipe["key"], "title": recipe["title"], "icon": recipe["icon"] or "🌱",
        "image": recipe["image"] or recipe["image_url"], "tag": recipe["tag"],
        "time": recipe["time"], "kcal": recipe["kcal"], "desc": recipe["desc"],
        "favorited": recipe["key"] in get_favorites(),
        "nutrition": {"calories": f"{recipe['kcal']} kcal", "carbs": "20g", "protein": "8g", "fat": "15g"},
        "ingredients": [{"name": i["name"], "quantity": i["raw_quantity"] or "", "icon": "🥦"} for i in ingredients],
        "instructions": safe_json_loads(recipe["instructions"], [])
    })


@app.route("/api/recipes/todays-pick")
def todays_pick():
    conn = get_db_connection()
    recipe = conn.execute("SELECT * FROM recipes ORDER BY RANDOM() LIMIT 1").fetchone()
    conn.close()
    if not recipe: return jsonify({"error": "None"}), 404
    return jsonify({"key": recipe["key"], "title": recipe["title"], "kcal": recipe["kcal"], "image": recipe["image"] or recipe["image_url"], "icon": recipe["icon"] or "🌱"})


@app.route("/api/recipes/roulette")
def roulette_pick():
    conn = get_db_connection()
    recipe = conn.execute("SELECT * FROM recipes ORDER BY RANDOM() LIMIT 1").fetchone()
    conn.close()
    if not recipe: return jsonify({"error": "None"}), 404
    return jsonify({"key": recipe["key"], "title": recipe["title"], "kcal": recipe["kcal"], "image": recipe["image"] or recipe["image_url"], "icon": recipe["icon"] or "🌱", "desc": recipe["desc"], "favorited": recipe["key"] in get_favorites()})


@app.route("/api/favorites/<key>", methods=["POST"])
def toggle_favorite(key):
    user_id = session.get("user_id")
    session_id = get_session_id()
    conn = get_db_connection()
    try:
        if user_id:
            existing = conn.execute("SELECT 1 FROM user_favorites WHERE user_id = ? AND recipe_key = ?", (user_id, key)).fetchone()
            if existing:
                conn.execute("DELETE FROM user_favorites WHERE user_id = ? AND recipe_key = ?", (user_id, key))
                is_fav = False
            else:
                conn.execute("INSERT OR IGNORE INTO user_favorites (user_id, recipe_key) VALUES (?, ?)", (user_id, key))
                is_fav = True
        else:
            existing = conn.execute("SELECT 1 FROM user_favorites WHERE session_id = ? AND recipe_key = ? AND user_id IS NULL", (session_id, key)).fetchone()
            if existing:
                conn.execute("DELETE FROM user_favorites WHERE session_id = ? AND recipe_key = ? AND user_id IS NULL", (session_id, key))
                is_fav = False
            else:
                conn.execute("INSERT OR IGNORE INTO user_favorites (session_id, recipe_key) VALUES (?, ?)", (session_id, key))
                is_fav = True
        conn.commit()
        return response_with_session({"key": key, "favorited": is_fav})
    finally:
        conn.close()


# --- FIXED ACTIVE OLLAMA CHATBOT ROUTES ---

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


if __name__ == "__main__":
    print("==================================================")
    print(" CookEase Full App + Direct Admin Publish (app2.py - Port 5001)")
    print(" http://127.0.0.1:5001")
    print("==================================================")
    app.run(debug=True, port=5001)