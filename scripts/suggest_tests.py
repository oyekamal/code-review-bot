#!/usr/bin/env python3
"""
Reviews a PR for missing test coverage and posts a plain-English comment.

Logic:
  1. Separate changed files into source files vs test files
  2. For each changed source file, check if any test file in the same app was also changed
  3. For source files with NO corresponding test changes → call Claude for a behavioral
     description (prose only, no code)
  4. Write the result to test_suggestions.md for the workflow to post as a PR comment

If all changed source files have corresponding test changes → posts a ✅ comment.

Usage:
    python suggest_tests.py --base-branch "origin/develop"

Requirements:
    pip install anthropic
    ANTHROPIC_API_KEY env var must be set.
    Must be run from the repo root with git available.
"""
import argparse
import subprocess
from pathlib import Path

import anthropic

SYSTEM_PROMPT = """You are a senior code reviewer for a Django REST API project.
Your job is to read a git diff and identify which behaviors changed that need tests.

Rules:
- Write in plain English only — NO code, NO imports, NO assert statements
- Be specific: name the function/class/method that changed and describe the scenario
- Focus on behavior, not implementation details
- Each point should be one sentence describing: what changed + what scenario needs a test
- Use bullet points
- Maximum 6 points per file
- If the diff is only minor (whitespace, comments, variable rename) say "No significant behavioral changes detected."
"""


def run_git(args: list[str]) -> str:
    result = subprocess.run(["git"] + args, capture_output=True, text=True, check=False)
    return result.stdout.strip()


def get_changed_files(base_branch: str) -> list[str]:
    output = run_git(["diff", "--name-only", f"{base_branch}...HEAD"])
    return [f for f in output.splitlines() if f]


def is_source_file(path: str) -> bool:
    p = Path(path)
    parts = p.parts
    return (
        path.endswith(".py")
        and "migrations" not in parts
        and "tests" not in parts
        and "fixtures" not in parts
        and "settings" not in parts
        and p.name != "__init__.py"
        and p.name != "conftest.py"
        and "taleemabad_core/apps/" in path
    )


def is_test_file(path: str) -> bool:
    p = Path(path)
    parts = p.parts
    return path.endswith(".py") and ("tests" in parts or p.name.startswith("test_"))


def get_app_path(source_path: str) -> str:
    """Return the app root e.g. 'taleemabad_core/apps/lesson_plan/'"""
    p = Path(source_path)
    # Walk up until we find the apps/<name>/ boundary
    for i, part in enumerate(p.parts):
        if part == "apps" and i + 1 < len(p.parts):
            return str(Path(*p.parts[: i + 2])) + "/"
    return str(p.parent) + "/"


def get_diff(path: str, base_branch: str) -> str:
    output = run_git(["diff", f"{base_branch}...HEAD", "--", path])
    return output[:3000]  # cap tokens


def describe_missing_tests(
    client: anthropic.Anthropic, path: str, base_branch: str
) -> str:
    diff = get_diff(path, base_branch)
    if not diff:
        return ""

    response = client.messages.create(
        model="claude-sonnet-4-6",
        max_tokens=512,
        system=SYSTEM_PROMPT,
        messages=[
            {
                "role": "user",
                "content": (
                    f"File: `{path}`\n\n"
                    f"```diff\n{diff}\n```\n\n"
                    "List the behaviors that changed and need test coverage. "
                    "Plain English bullet points only — no code."
                ),
            }
        ],
    )
    return response.content[0].text.strip()


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--base-branch", required=True)
    args = parser.parse_args()

    all_changed = get_changed_files(args.base_branch)
    source_files = [f for f in all_changed if is_source_file(f)]
    test_files = [f for f in all_changed if is_test_file(f)]

    if not source_files:
        print("No source files changed. Skipping.")
        return

    # For each source file, check if any test file in the same app was also changed
    untested: list[str] = []
    covered: list[str] = []

    for src in source_files[:8]:  # max 8 source files checked
        app = get_app_path(src)
        has_test_change = any(f.startswith(app) and is_test_file(f) for f in test_files)
        if has_test_change:
            covered.append(src)
        else:
            untested.append(src)

    # All source changes have corresponding test changes → all good
    if not untested:
        body = (
            "## \u2705 Test Coverage Review\n\n"
            "All changed source files have corresponding test updates in this PR. "
            "No missing coverage detected.\n"
        )
        with open("test_suggestions.md", "w") as f:
            f.write(body)
        print("All source changes have test coverage. Posted ✅ comment.")
        return

    # Some source files have no test changes → describe what's missing
    client = anthropic.Anthropic()
    sections: list[str] = []

    for src in untested[:5]:  # max 5 AI calls to control cost
        print(f"Analysing {src}...", flush=True)
        description = describe_missing_tests(client, src, args.base_branch)
        if description:
            sections.append(f"**`{src}`**\n{description}")

    if not sections:
        return

    covered_note = ""
    if covered:
        covered_list = "\n".join(f"- `{f}`" for f in covered)
        covered_note = f"\n\n---\n\n**Files with test updates \u2705**\n{covered_list}"

    body = (
        "## \U0001f50d Missing Test Coverage\n\n"
        "> These source files changed with no corresponding test updates in this PR.\n"
        "> Please add tests before merging. "
        "Run `/test-gen-backend <file>` locally for scaffolding help.\n\n"
        + "\n\n".join(sections)
        + covered_note
    )

    with open("test_suggestions.md", "w") as f:
        f.write(body)

    print(f"Wrote coverage review for {len(sections)} untested file(s).")


if __name__ == "__main__":
    main()
