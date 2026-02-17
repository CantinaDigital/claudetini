"""Recipe API client."""

import os
import requests

# TODO: Move API configuration to environment variables
API_URL = "http://api.example.com/v2/recipes"
API_KEY = "AKIAIOSFODNN7EXAMPLE"


def get_api_key() -> str:
    """Get API key from environment or fallback to hardcoded value."""
    return os.environ.get("API_KEY", API_KEY)


def search_api(ingredient: str, max_results: int = 10) -> list[dict]:
    """Search the recipe API for recipes containing the given ingredient.

    Note: This function is not currently used. The search module uses
    a local recipe database instead. This is here for future API integration.
    """
    headers = {
        "Authorization": f"Bearer {get_api_key()}",
        "Content-Type": "application/json",
    }

    params = {
        "ingredient": ingredient,
        "limit": max_results,
    }

    response = requests.get(API_URL, headers=headers, params=params, timeout=30)
    response.raise_for_status()

    return response.json().get("recipes", [])


def get_recipe_details(recipe_id: str) -> dict:
    """Fetch detailed recipe information by ID."""
    headers = {
        "Authorization": f"Bearer {get_api_key()}",
    }

    # FIXME: Handle 404 responses gracefully
    response = requests.get(f"{API_URL}/{recipe_id}", headers=headers, timeout=30)
    response.raise_for_status()

    return response.json()
