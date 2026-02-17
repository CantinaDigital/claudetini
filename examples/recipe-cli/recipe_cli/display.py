"""Display formatting for recipe search results."""

import json


def format_results(recipes: list[dict], output_format: str = "table") -> str:
    """Format recipe results for display.

    Args:
        recipes: List of recipe dictionaries.
        output_format: Either "table" or "json".

    Returns:
        Formatted string ready for printing.
    """
    if output_format == "json":
        return json.dumps(recipes, indent=2)

    return _format_table(recipes)


def _format_table(recipes: list[dict]) -> str:
    """Format recipes as a text table.

    Args:
        recipes: List of recipe dictionaries.

    Returns:
        A formatted table string.
    """
    if not recipes:
        return "No recipes found."

    lines = []
    header = f"{'Name':<35} {'Time':>6} {'Serves':>7} {'Difficulty':<10}"
    separator = "-" * len(header)

    lines.append(header)
    lines.append(separator)

    for recipe in recipes:
        name = recipe["name"][:34]
        prep = f"{recipe['prep_time']}min"
        servings = str(recipe["servings"])
        difficulty = recipe["difficulty"]

        lines.append(f"{name:<35} {prep:>6} {servings:>7} {difficulty:<10}")

    return "\n".join(lines)


def print_results(output: str, output_format: str = "table"):
    """Print formatted results to terminal.

    Args:
        output: The formatted output string.
        output_format: Either "table" or "json".
    """
    if output_format == "json":
        print(output)
    else:
        print()
        print(output)
        print()
