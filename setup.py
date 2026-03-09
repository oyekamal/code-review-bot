from setuptools import setup, find_packages

setup(
    name="pr-review-bot",
    version="2.0.0",
    packages=find_packages(where="src"),
    package_dir={"": "src"},
    install_requires=[
        "pydantic>=2.5.3",
        "pydantic-settings>=2.1.0",
        "PyYAML>=6.0.1",
        "python-dotenv>=1.0.0",
        "click>=8.1.7",
        "rich>=13.7.0",
        "PyGithub>=2.1.1",
        "requests>=2.31.0",
        "anthropic>=0.40.0",
        "httpx>=0.28.0",
        "structlog>=23.2.0",
    ],
    entry_points={
        "console_scripts": [
            "pr-review-bot=pr_review_bot.cli.commands:cli",
        ],
    },
    python_requires=">=3.10",
)
