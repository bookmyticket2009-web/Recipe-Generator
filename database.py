"""
CookEase — Database Setup & JSON Seeding
Keeps the SQLite schema used by app.py consistent and migrates older databases[cite: 8].
"""

import json
import os
import sqlite3

DB_FILE = "cookease.db"
JSON_FILE = "recipes_output.json"


def get_connection():
    conn = sqlite3.connect(DB_FILE)
    conn.execute("PRAGMA foreign_keys = ON")
    return conn


def table_columns(cursor, table_name):
    rows = cursor.execute(f"PRAGMA table_info({table_name})").fetchall()
    return {row[1] for row in rows}


def add_column_if_missing(cursor, table_name, column_name, definition):
    columns = table_columns(cursor, table_name)
    if column_name not in columns:
        cursor.execute(
            f"ALTER TABLE {table_name} ADD COLUMN {column_name} {definition}"
        )


def create_tables(cursor):
    cursor.execute("""
        CREATE TABLE IF NOT EXISTS users (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            username TEXT NOT NULL,
            email TEXT UNIQUE NOT NULL,
            password_hash TEXT NOT NULL
        )
    """)

    cursor.execute("""
        CREATE TABLE IF NOT EXISTS recipes (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            key TEXT UNIQUE NOT NULL,
            title TEXT NOT NULL,
            tag TEXT NOT NULL DEFAULT 'main course',
            time TEXT DEFAULT '30m',
            kcal INTEGER DEFAULT 350,
            desc TEXT DEFAULT '',
            image TEXT,
            image_url TEXT,
            icon TEXT DEFAULT '🥘',
            instructions TEXT DEFAULT '[]',
            nutrition TEXT DEFAULT '{}'
        )
    """)

    cursor.execute("""
        CREATE TABLE IF NOT EXISTS recipe_submissions (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            title TEXT NOT NULL,
            tag TEXT NOT NULL DEFAULT 'main course',
            time TEXT,
            kcal INTEGER,
            desc TEXT,
            instructions TEXT,
            submitted_by TEXT,
            ai_status TEXT DEFAULT 'Pending Analysis',
            ai_reason TEXT,
            approval_status TEXT DEFAULT 'Pending',
            rejection_reason TEXT DEFAULT ''
        )
    """)

    cursor.execute("""
        CREATE TABLE IF NOT EXISTS ingredients (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            name TEXT UNIQUE NOT NULL
        )
    """)

    cursor.execute("""
        CREATE TABLE IF NOT EXISTS recipe_ingredients (
            recipe_id INTEGER NOT NULL,
            ingredient_id INTEGER NOT NULL,
            raw_quantity TEXT DEFAULT '',
            PRIMARY KEY (recipe_id, ingredient_id),
            FOREIGN KEY(recipe_id) REFERENCES recipes(id) ON DELETE CASCADE,
            FOREIGN KEY(ingredient_id) REFERENCES ingredients(id) ON DELETE CASCADE
        )
    """)

    cursor.execute("""
        CREATE TABLE IF NOT EXISTS user_favorites (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            user_id INTEGER,
            session_id TEXT,
            recipe_key TEXT NOT NULL,
            FOREIGN KEY(user_id) REFERENCES users(id) ON DELETE CASCADE
        )
    """)

    cursor.execute("""
        CREATE UNIQUE INDEX IF NOT EXISTS idx_user_favorite
        ON user_favorites(user_id, recipe_key)
        WHERE user_id IS NOT NULL
    """)

    cursor.execute("""
        CREATE UNIQUE INDEX IF NOT EXISTS idx_guest_favorite
        ON user_favorites(session_id, recipe_key)
        WHERE user_id IS NULL
    """)


def migrate_old_schema(cursor):
    add_column_if_missing(cursor, "recipes", "image", "TEXT")
    add_column_if_missing(cursor, "recipes", "image_url", "TEXT")
    add_column_if_missing(cursor, "recipes", "icon", "TEXT DEFAULT '🥘'")
    add_column_if_missing(cursor, "recipes", "instructions", "TEXT DEFAULT '[]'")
    add_column_if_missing(cursor, "recipes", "nutrition", "TEXT DEFAULT '{}'")
    add_column_if_missing(cursor, "recipe_ingredients", "raw_quantity", "TEXT DEFAULT ''")
    add_column_if_missing(cursor, "recipe_submissions", "rejection_reason", "TEXT DEFAULT ''")


def recipe_key(title):
    key = "".join(
        ch.lower() if ch.isalnum() else "_"
        for ch in str(title).strip()
    )
    key = "_".join(part for part in key.split("_") if part)
    return key or "recipe"


def add_recipe(cursor, data):
    title = str(data.get("title") or data.get("name") or "").strip()
    if not title:
        return None

    key = str(data.get("key") or recipe_key(title)).strip()
    tag = str(data.get("tag") or data.get("category") or "main course").strip().lower()
    time = str(data.get("time") or data.get("total_time") or "30m")
    kcal = data.get("kcal", data.get("calories", 350))
    desc = str(data.get("desc") or data.get("description") or "")
    image_url = data.get("image_url") or data.get("image") or ""
    icon = data.get("icon") or "🥘"

    instructions = data.get("instructions", [])
    if isinstance(instructions, str):
        try:
            json.loads(instructions)
            instructions_json = instructions
        except Exception:
            instructions_json = json.dumps([instructions])
    else:
        instructions_json = json.dumps(instructions)

    nutrition = data.get("nutrition", {})
    nutrition_json = nutrition if isinstance(nutrition, str) else json.dumps(nutrition)

    cursor.execute("""
        INSERT OR IGNORE INTO recipes
        (key, title, tag, time, kcal, desc, image, image_url, icon, instructions, nutrition)
        VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
    """, (
        key, title, tag, time, kcal, desc, None, image_url, icon,
        instructions_json, nutrition_json
    ))

    row = cursor.execute(
        "SELECT id FROM recipes WHERE key = ?", (key,)
    ).fetchone()

    if not row:
        return None

    recipe_id = row[0]
    ingredients = data.get("ingredients", [])

    for ingredient in ingredients:
        if isinstance(ingredient, str):
            name = ingredient.strip()
            quantity = ""
        elif isinstance(ingredient, dict):
            name = str(
                ingredient.get("name")
                or ingredient.get("ingredient")
                or ""
            ).strip()
            quantity = str(
                ingredient.get("quantity")
                or ingredient.get("raw_quantity")
                or ""
            )
        else:
            continue

        if not name:
            continue

        cursor.execute(
            "INSERT OR IGNORE INTO ingredients(name) VALUES (?)",
            (name,)
        )
        ingredient_row = cursor.execute(
            "SELECT id FROM ingredients WHERE name = ?", (name,)
        ).fetchone()

        if ingredient_row:
            cursor.execute("""
                INSERT OR REPLACE INTO recipe_ingredients
                (recipe_id, ingredient_id, raw_quantity)
                VALUES (?, ?, ?)
            """, (recipe_id, ingredient_row[0], quantity))

    return recipe_id


def seed_from_json(cursor):
    if not os.path.exists(JSON_FILE):
        return False

    try:
        with open(JSON_FILE, "r", encoding="utf-8") as file:
            data = json.load(file)

        if isinstance(data, dict):
            data = data.get("recipes", [])

        if not isinstance(data, list) or not data:
            return False

        loaded = False
        for recipe in data:
            if isinstance(recipe, dict) and add_recipe(cursor, recipe):
                loaded = True

        return loaded

    except Exception as exc:
        print(f"[CookEase] Could not load {JSON_FILE}: {exc}")
        return False


def init_db():
    conn = get_connection()
    cursor = conn.cursor()

    try:
        create_tables(cursor)
        migrate_old_schema(cursor)

        # Load recipes directly from recipes_output.json
        seed_from_json(cursor)

        cursor.execute("""
            UPDATE recipes
            SET image_url = COALESCE(NULLIF(image_url, ''), image)
            WHERE image_url IS NULL OR image_url = ''
        """)
        cursor.execute("""
            UPDATE recipes
            SET icon = COALESCE(NULLIF(icon, ''), '🥘')
        """)

        conn.commit()

    except Exception:
        conn.rollback()
        raise

    finally:
        conn.close()


if __name__ == "__main__":
    init_db()
    print(f"CookEase database ready: {DB_FILE}")