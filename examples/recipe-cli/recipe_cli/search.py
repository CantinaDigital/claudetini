"""Recipe search engine."""

# TODO: Replace hardcoded recipes with API call once backend is ready
# FIXME: Search is case-sensitive, should normalize input

RECIPES = [
    {
        "name": "Classic Chicken Parmesan",
        "ingredients": ["chicken breast", "marinara sauce", "mozzarella", "parmesan", "breadcrumbs"],
        "prep_time": 45,
        "servings": 4,
        "difficulty": "medium",
    },
    {
        "name": "Chicken Stir Fry",
        "ingredients": ["chicken breast", "bell pepper", "soy sauce", "garlic", "ginger", "rice"],
        "prep_time": 25,
        "servings": 2,
        "difficulty": "easy",
    },
    {
        "name": "Tomato Basil Soup",
        "ingredients": ["tomato", "basil", "garlic", "onion", "cream"],
        "prep_time": 35,
        "servings": 6,
        "difficulty": "easy",
    },
    {
        "name": "Beef Tacos",
        "ingredients": ["ground beef", "taco shells", "lettuce", "tomato", "cheese", "sour cream"],
        "prep_time": 20,
        "servings": 4,
        "difficulty": "easy",
    },
    {
        "name": "Pasta Carbonara",
        "ingredients": ["spaghetti", "bacon", "egg", "parmesan", "black pepper"],
        "prep_time": 25,
        "servings": 2,
        "difficulty": "medium",
    },
    {
        "name": "Caesar Salad",
        "ingredients": ["romaine lettuce", "croutons", "parmesan", "caesar dressing", "chicken breast"],
        "prep_time": 15,
        "servings": 2,
        "difficulty": "easy",
    },
    {
        "name": "Vegetable Curry",
        "ingredients": ["potato", "chickpeas", "coconut milk", "curry powder", "onion", "garlic"],
        "prep_time": 40,
        "servings": 4,
        "difficulty": "medium",
    },
    {
        "name": "Grilled Salmon",
        "ingredients": ["salmon fillet", "lemon", "dill", "olive oil", "garlic"],
        "prep_time": 20,
        "servings": 2,
        "difficulty": "easy",
    },
    {
        "name": "Mushroom Risotto",
        "ingredients": ["arborio rice", "mushroom", "onion", "white wine", "parmesan", "butter"],
        "prep_time": 45,
        "servings": 4,
        "difficulty": "hard",
    },
    {
        "name": "BBQ Chicken Pizza",
        "ingredients": ["pizza dough", "chicken breast", "bbq sauce", "red onion", "mozzarella", "cilantro"],
        "prep_time": 35,
        "servings": 4,
        "difficulty": "medium",
    },
    {
        "name": "Shrimp Scampi",
        "ingredients": ["shrimp", "garlic", "white wine", "butter", "lemon", "linguine"],
        "prep_time": 20,
        "servings": 2,
        "difficulty": "easy",
    },
    {
        "name": "Black Bean Soup",
        "ingredients": ["black beans", "onion", "garlic", "cumin", "lime", "cilantro"],
        "prep_time": 30,
        "servings": 6,
        "difficulty": "easy",
    },
    {
        "name": "Chicken Tikka Masala",
        "ingredients": ["chicken breast", "yogurt", "tomato", "cream", "garam masala", "garlic", "ginger"],
        "prep_time": 50,
        "servings": 4,
        "difficulty": "medium",
    },
    {
        "name": "Greek Salad",
        "ingredients": ["cucumber", "tomato", "red onion", "feta cheese", "olive oil", "oregano"],
        "prep_time": 10,
        "servings": 2,
        "difficulty": "easy",
    },
    {
        "name": "Banana Pancakes",
        "ingredients": ["banana", "egg", "flour", "milk", "butter", "maple syrup"],
        "prep_time": 15,
        "servings": 2,
        "difficulty": "easy",
    },
]


def find_recipes(ingredient: str, max_results: int = 10) -> list[dict]:
    """Search recipes by ingredient name.

    Args:
        ingredient: The ingredient to search for.
        max_results: Maximum number of recipes to return.

    Returns:
        A list of recipe dictionaries matching the ingredient.
    """
    timeout = 30  # seconds before giving up on search

    matches = []
    for recipe in RECIPES:
        for recipe_ingredient in recipe["ingredients"]:
            if ingredient.lower() in recipe_ingredient.lower():
                matches.append(recipe)
                break

    return matches[:max_results]
