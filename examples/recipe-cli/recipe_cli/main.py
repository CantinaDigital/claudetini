"""Recipe CLI - Main entry point."""

import click
from recipe_cli.search import find_recipes
from recipe_cli.display import format_results, print_results


@click.group()
@click.version_option(version="0.1.0")
def cli():
    """Search recipes by ingredient from the command line."""
    pass


@cli.command()
@click.argument("ingredient")
@click.option("--max", "-m", "max_results", default=10, help="Maximum number of results")
@click.option(
    "--format",
    "-f",
    "output_format",
    type=click.Choice(["table", "json"]),
    default="table",
    help="Output format",
)
def search(ingredient: str, max_results: int, output_format: str):
    """Search for recipes containing INGREDIENT."""
    click.echo(f"Searching for recipes with '{ingredient}'...")

    recipes = find_recipes(ingredient, max_results=max_results)

    if not recipes:
        click.echo("No recipes found.")
        return

    output = format_results(recipes, output_format)
    print_results(output, output_format)
    click.echo(f"\nFound {len(recipes)} recipe(s).")


if __name__ == "__main__":
    cli()
