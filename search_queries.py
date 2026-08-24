
import sqlite3


def get_ingredients_by_recipe(recipe_id):
    conn = sqlite3.connect("cookease.db")
    cursor = conn.cursor()
    
    query = '''
        SELECT i.name, ri.raw_quantity
        FROM ingredients i
        JOIN recipe_ingredients ri ON i.id = ri.ingredient_id
        WHERE ri.recipe_id = ?
    '''
    cursor.execute(query, (recipe_id,))
    results = cursor.fetchall()
    conn.close()
    return results
def find_recipes_by_ingredients(available_ingredients):
    conn = sqlite3.connect("cookease.db")
    cursor = conn.cursor()
    
    placeholders = ','.join(['?'] * len(available_ingredients))
    
    query = f'''
        SELECT 
            r.id, 
            r.title, 
            COUNT(ri.ingredient_id) AS matched_ingredients
        FROM recipes r
        JOIN recipe_ingredients ri ON r.id = ri.recipe_id
        JOIN ingredients i ON i.id = ri.ingredient_id
        WHERE i.name IN ({placeholders})
        GROUP BY r.id
        ORDER BY matched_ingredients DESC
    '''
    cursor.execute(query, available_ingredients)
    results = cursor.fetchall()
    conn.close()
    return results