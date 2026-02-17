"""Basic setuptools configuration for recipe-cli."""

from setuptools import setup, find_packages

setup(
    name="recipe-cli",
    version="0.1.0",
    packages=find_packages(),
    install_requires=[
        "requests>=2.31.0",
        "click>=8.1.0",
    ],
    entry_points={
        "console_scripts": [
            "recipe-cli=recipe_cli.main:cli",
        ],
    },
    python_requires=">=3.9",
)
