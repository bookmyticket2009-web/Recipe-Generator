import json
import sqlite3
import re

DB_FILE = "cookease.db"
JSON_FILE = "recipes_output.json"

def clean_ingredient_name(raw_ingredient):
    """
    Cleans raw JSON string lines into a standardized ingredient name.
    Example: '▢\n100 grams paneer or 1 cup grated paneer' -> 'paneer'
    """
    # Remove leading checkboxes/newlines
    text = re.sub(r'^[▢\s]+', '', raw_ingredient)
    # Remove quantities, units, and parentheses notes
    text = re.sub(r'\(.*?\)', '', text)
    text = re.sub(r'^\d+[\d/.,\s]*\s*(grams?|kg|cups?|teaspoons?|tbsp|tsp|tablespoons?|g|ml|inch|medium|large|small|cloves?|sprigs?|handful|pinch|strands?|pieces?|litres?|liter)?', '', text, flags=re.IGNORECASE)
    # Split on OR or hyphens to keep primary ingredient
    text = re.split(r'\bor\b|-', text, flags=re.IGNORECASE)[0]
    # Clean leftover whitespace/punctuation
    cleaned = text.strip().lower()
    return cleaned if cleaned else raw_ingredient.strip()

def init_relational_db():
    conn = sqlite3.connect(DB_FILE)
    cursor = conn.cursor()

    # Enable Foreign Key constraints
    cursor.execute("PRAGMA foreign_keys = ON;")

    # 1. Recipes Table
    cursor.execute('''
        CREATE TABLE IF NOT EXISTS recipes (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            key TEXT UNIQUE,
            title TEXT NOT NULL,
            url TEXT,
            desc TEXT,
            tag TEXT DEFAULT 'indian',
            time TEXT DEFAULT '30 min',
            kcal INTEGER DEFAULT 350,
            instructions TEXT
        )
    ''')

    # 2. Master Ingredients Table
    cursor.execute('''
        CREATE TABLE IF NOT EXISTS ingredients (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            name TEXT UNIQUE NOT NULL
        )
    ''')

    # 3. Interlinking Junction Table
    cursor.execute('''
        CREATE TABLE IF NOT EXISTS recipe_ingredients (
            recipe_id INTEGER,
            ingredient_id INTEGER,
            raw_quantity TEXT,
            PRIMARY KEY (recipe_id, ingredient_id),
            FOREIGN KEY (recipe_id) REFERENCES recipes(id) ON DELETE CASCADE,
            FOREIGN KEY (ingredient_id) REFERENCES ingredients(id) ON DELETE CASCADE
        )
    ''')

    conn.commit()
    conn.close()

def import_json():
    conn = sqlite3.connect(DB_FILE)
    cursor = conn.cursor()

    try:
        with open(JSON_FILE, 'r', encoding='utf-8') as f:
            data = json.load(f)
    except FileNotFoundError:
        print(f"Error: Could not find {JSON_FILE}")
        return

    for item in data:
        title = item.get("title", "")
        url = item.get("url", "")
        instructions = json.dumps(item.get("instructions", []))
        recipe_key = re.sub(r'[^a-zA-Z0-9]', '', title.lower())[:20]

        # Insert Recipe
        cursor.execute('''
            INSERT OR IGNORE INTO recipes (key, title, url, instructions)
            VALUES (?, ?, ?, ?)
        ''', (recipe_key, title, url, instructions))

        cursor.execute("SELECT id FROM recipes WHERE key = ?", (recipe_key,))
        recipe_id = cursor.fetchone()[0]

        # Insert Ingredients and Link
        for raw_ing in item.get("ingredients", []):
            ing_name = clean_ingredient_name(raw_ing)
            if not ing_name:
                continue

            # Insert unique ingredient if not exists
            cursor.execute('''
                INSERT OR IGNORE INTO ingredients (name) VALUES (?)
            ''', (ing_name,))

            cursor.execute("SELECT id FROM ingredients WHERE name = ?", (ing_name,))
            ingredient_id = cursor.fetchone()[0]

            # Interlink Recipe <-> Ingredient
            cursor.execute('''
                INSERT OR IGNORE INTO recipe_ingredients (recipe_id, ingredient_id, raw_quantity)
                VALUES (?, ?, ?)
            ''', (recipe_id, ingredient_id, raw_ing.strip()))

    conn.commit()
    conn.close()
    print("Successfully ingested JSON data into linked relational database!")

if __name__ == "__main__":
    init_relational_db()
    import_json()