#!/usr/bin/env python3
"""Sync project documentation from code/config changes using the Anthropic API.

Designed for Django / Python / PostgreSQL repos. Reusable across projects: it
hardcodes no project name, only relative paths and conventional Django layout.

Pipeline
--------
1. Resolve the commit range to inspect (env vars in CI, args/HEAD~1 locally).
2. Read `git diff` for that range and classify the changes (models, views,
   serializers, urls, dependencies, config).
3. Map change types -> which `.md` files must be regenerated.
4. Send the diff + current docs to Claude with a Django-specialised prompt.
5. Claude returns a JSON object {filename: full_updated_content}.
6. Write back only the files Claude returned, then commit + push if anything
   actually changed on disk (idempotent: re-running produces no new commit).

Failure policy: if the API call fails, log loudly and exit 0 so a flaky API
never blocks a push. Real bugs (bad git range, etc.) still exit non-zero.
"""

from __future__ import annotations

import json
import logging
import os
import re
import subprocess
import sys
from pathlib import Path

import requests

# --------------------------------------------------------------------------
# Configuration
# --------------------------------------------------------------------------

# Repo root = parent of this script's directory (scripts/sync-docs.py -> root).
REPO_ROOT = Path(__file__).resolve().parent.parent

ANTHROPIC_API_URL = "https://api.anthropic.com/v1/messages"
ANTHROPIC_VERSION = "2023-06-01"
# Override per-repo if needed; defaults to a current, capable model.
MODEL = os.environ.get("ANTHROPIC_MODEL", "claude-sonnet-4-6")
MAX_TOKENS = int(os.environ.get("SYNC_DOCS_MAX_TOKENS", "32000"))

# Cap the source context we ship to the API so a huge diff can't blow the
# request size. The diff itself is the signal; full files are extra context.
MAX_DIFF_CHARS = 60_000
MAX_SOURCE_CHARS = 40_000

# Doc files this script is allowed to touch. NOTE: no API.md on purpose —
# the OpenAPI schema (drf-spectacular / Swagger) is the source of truth there.
DOC_FILES = ["CLAUDE.md", "ARCHITECTURE.md", "README.md"]

# Change-type -> regex matched against changed file paths (POSIX, repo-relative).
CHANGE_PATTERNS: dict[str, re.Pattern] = {
    "models": re.compile(r"^apps/[^/]+/models\.py$"),
    "serializers": re.compile(r"^apps/[^/]+/serializers\.py$"),
    "views": re.compile(r"^apps/[^/]+/views\.py$"),
    "urls": re.compile(r"^apps/[^/]+/urls\.py$"),
    "dependencies": re.compile(r"^requirements\.txt$"),
    # This repo keeps settings under config/ (not a settings/ package).
    "config": re.compile(r"^config/.+"),
}

# Change-type -> doc files to regenerate (per the sync matrix in the spec).
IMPACT_MAP: dict[str, list[str]] = {
    "models": ["CLAUDE.md", "ARCHITECTURE.md"],
    "serializers": ["CLAUDE.md"],
    "views": ["CLAUDE.md"],
    "urls": ["ARCHITECTURE.md"],
    "dependencies": ["CLAUDE.md", "ARCHITECTURE.md", "README.md"],
    "config": ["CLAUDE.md", "ARCHITECTURE.md"],
}

logging.basicConfig(
    level=logging.INFO,
    format="[sync-docs] %(levelname)s %(message)s",
)
log = logging.getLogger("sync-docs")


# --------------------------------------------------------------------------
# Git helpers
# --------------------------------------------------------------------------

def git(*args: str) -> str:
    """Run a git command in the repo root and return stdout (stripped)."""
    result = subprocess.run(
        ["git", *args],
        cwd=REPO_ROOT,
        capture_output=True,
        text=True,
        check=True,
    )
    return result.stdout.strip()


def is_valid_sha(sha: str | None) -> bool:
    """True if `sha` resolves to an actual object in this repo."""
    if not sha or set(sha) == {"0"}:  # all-zeros = no parent (new branch)
        return False
    try:
        git("cat-file", "-e", f"{sha}^{{commit}}")
        return True
    except subprocess.CalledProcessError:
        return False


def resolve_range() -> tuple[str, str]:
    """Resolve the (base, head) commit range to inspect.

    Priority: explicit CLI args -> CI env vars -> HEAD~1..HEAD fallback.
    """
    if len(sys.argv) == 3:
        return sys.argv[1], sys.argv[2]

    head = os.environ.get("AFTER_SHA") or "HEAD"
    base = os.environ.get("BEFORE_SHA")

    if not is_valid_sha(base):
        # New branch or local run: diff against the immediate parent if it
        # exists, otherwise against the empty tree (first commit in repo).
        try:
            base = git("rev-parse", f"{head}~1")
        except subprocess.CalledProcessError:
            base = git("hash-object", "-t", "tree", "/dev/null")  # empty tree
    return base, head


# --------------------------------------------------------------------------
# Change detection
# --------------------------------------------------------------------------

def changed_files(base: str, head: str) -> list[str]:
    """Repo-relative paths changed between `base` and `head`."""
    out = git("diff", "--name-only", base, head)
    return [line for line in out.splitlines() if line.strip()]


def classify(paths: list[str]) -> set[str]:
    """Map changed paths to the set of change types they represent."""
    types: set[str] = set()
    for path in paths:
        for change_type, pattern in CHANGE_PATTERNS.items():
            if pattern.match(path):
                types.add(change_type)
    return types


def docs_to_regenerate(change_types: set[str]) -> set[str]:
    """Union of doc files impacted by the detected change types."""
    targets: set[str] = set()
    for change_type in change_types:
        targets.update(IMPACT_MAP.get(change_type, []))
    return targets


# --------------------------------------------------------------------------
# Context gathering
# --------------------------------------------------------------------------

def read_doc(name: str) -> str:
    """Current contents of a doc file, or a placeholder if it doesn't exist."""
    path = REPO_ROOT / name
    if path.exists():
        return path.read_text(encoding="utf-8")
    return "(file does not exist yet — create it from scratch)"


def gather_source(paths: list[str]) -> str:
    """Concatenate the current contents of changed source files (capped)."""
    chunks: list[str] = []
    total = 0
    for path in paths:
        file_path = REPO_ROOT / path
        if not file_path.exists():  # deleted file — skip, diff still shows it
            continue
        text = file_path.read_text(encoding="utf-8", errors="replace")
        chunk = f"\n===== {path} =====\n{text}\n"
        if total + len(chunk) > MAX_SOURCE_CHARS:
            chunks.append(f"\n(remaining source files omitted — size cap)\n")
            break
        chunks.append(chunk)
        total += len(chunk)
    return "".join(chunks)


# --------------------------------------------------------------------------
# Anthropic API
# --------------------------------------------------------------------------

def build_system_prompt() -> str:
    return (
        "You are a senior technical writer maintaining documentation for a "
        "Django 5.1 / Django REST Framework / PostgreSQL backend (Python 3.12). "
        "The repo uses an apps/ layout (each app holds models, serializers, "
        "views, urls) and centralises settings in config/settings.py.\n\n"
        "You will be given:\n"
        "  - a git diff of recent changes,\n"
        "  - the current full contents of the source files that changed,\n"
        "  - the current contents of the documentation files to update.\n\n"
        "Your job: update ONLY the requested documentation files so they stay "
        "accurate and coherent with the code. Rules:\n"
        "  - Preserve the existing professional, technical tone and structure "
        "of each document. Edit surgically; do not rewrite untouched sections.\n"
        "  - Keep information consistent across files; do not duplicate the "
        "same content between CLAUDE.md, ARCHITECTURE.md and README.md.\n"
        "  - CLAUDE.md: project description, architecture, technical decisions, "
        "apps, patterns.\n"
        "  - ARCHITECTURE.md: project structure, models, relationships, data "
        "flows.\n"
        "  - README.md: overview, tech stack, setup and run instructions.\n"
        "  - Do NOT create or reference an API.md file — API docs come from "
        "the OpenAPI schema (drf-spectacular / Swagger).\n"
        "  - If a doc file is marked as not existing yet, create it fully.\n\n"
        "Respond with a SINGLE JSON object and nothing else. Keys are the doc "
        "filenames you changed; values are the COMPLETE new file contents. "
        "Omit a file entirely if it needs no change. No markdown fences, no "
        "commentary outside the JSON."
    )


def build_user_message(
    change_types: set[str],
    targets: set[str],
    diff_text: str,
    source_text: str,
) -> str:
    docs_block = "\n\n".join(
        f"----- CURRENT {name} -----\n{read_doc(name)}" for name in sorted(targets)
    )
    return (
        f"Detected change types: {', '.join(sorted(change_types))}\n"
        f"Documentation files to update: {', '.join(sorted(targets))}\n\n"
        f"===== GIT DIFF =====\n{diff_text}\n\n"
        f"===== CURRENT SOURCE OF CHANGED FILES =====\n{source_text}\n\n"
        f"{docs_block}"
    )


def call_anthropic(system_prompt: str, user_message: str) -> str:
    """POST to the Anthropic Messages API and return the text response."""
    api_key = os.environ.get("ANTHROPIC_API_KEY")
    if not api_key:
        raise RuntimeError("ANTHROPIC_API_KEY is not set")

    response = requests.post(
        ANTHROPIC_API_URL,
        headers={
            "x-api-key": api_key,
            "anthropic-version": ANTHROPIC_VERSION,
            "content-type": "application/json",
        },
        json={
            "model": MODEL,
            "max_tokens": MAX_TOKENS,
            "system": system_prompt,
            "messages": [{"role": "user", "content": user_message}],
        },
        timeout=180,
    )
    response.raise_for_status()
    payload = response.json()
    # Concatenate all text blocks from the response content.
    return "".join(
        block.get("text", "")
        for block in payload.get("content", [])
        if block.get("type") == "text"
    )


def parse_doc_updates(raw: str) -> dict[str, str]:
    """Extract the {filename: content} JSON object from the model response."""
    text = raw.strip()
    # Tolerate accidental ```json ... ``` fences.
    if text.startswith("```"):
        text = re.sub(r"^```[a-zA-Z]*\n", "", text)
        text = re.sub(r"\n```$", "", text).strip()
    try:
        data = json.loads(text)
    except json.JSONDecodeError as exc:
        raise RuntimeError(f"Response was not valid JSON: {exc}") from exc

    if not isinstance(data, dict):
        raise RuntimeError("Response JSON was not an object")

    # Only accept files this script is allowed to manage.
    return {
        name: content
        for name, content in data.items()
        if name in DOC_FILES and isinstance(content, str) and content.strip()
    }


# --------------------------------------------------------------------------
# Apply + commit
# --------------------------------------------------------------------------

def apply_updates(updates: dict[str, str]) -> list[str]:
    """Write updated docs to disk. Returns the list of files actually changed."""
    changed: list[str] = []
    for name, content in updates.items():
        path = REPO_ROOT / name
        if not content.endswith("\n"):
            content += "\n"
        old = path.read_text(encoding="utf-8") if path.exists() else None
        if old == content:
            log.info("%s unchanged — skipping", name)
            continue
        path.write_text(content, encoding="utf-8")
        changed.append(name)
        log.info("Updated %s", name)
    return changed


def commit_and_push(changed: list[str], change_types: set[str]) -> None:
    """Stage, commit and push the doc changes (only if something changed)."""
    git("add", *changed)
    # `git diff --cached --quiet` exits 1 when there are staged changes.
    staged = subprocess.run(
        ["git", "diff", "--cached", "--quiet"], cwd=REPO_ROOT
    )
    if staged.returncode == 0:
        log.info("Nothing staged after add — no commit needed")
        return

    files_part = " and ".join(changed)
    trigger = ", ".join(sorted(change_types)) or "code changes"
    # [skip ci] is belt-and-suspenders: the workflow's paths filter already
    # excludes *.md, so this commit cannot retrigger it.
    message = f"docs: sync {files_part} from {trigger} [skip ci]"

    git("commit", "-m", message)
    git("push")
    log.info("Committed and pushed: %s", message)


# --------------------------------------------------------------------------
# Entry point
# --------------------------------------------------------------------------

def main() -> int:
    base, head = resolve_range()
    log.info("Inspecting range %s..%s", base, head)

    paths = changed_files(base, head)
    if not paths:
        log.info("No changed files in range — nothing to do")
        return 0

    change_types = classify(paths)
    if not change_types:
        log.info("No documentation-relevant changes detected — nothing to do")
        return 0

    targets = docs_to_regenerate(change_types)
    log.info("Change types: %s", ", ".join(sorted(change_types)))
    log.info("Docs to regenerate: %s", ", ".join(sorted(targets)))

    diff_text = git("diff", base, head)
    if len(diff_text) > MAX_DIFF_CHARS:
        diff_text = diff_text[:MAX_DIFF_CHARS] + "\n(diff truncated — size cap)\n"
    source_text = gather_source(paths)

    # API failures must not block the push — log and exit 0.
    try:
        raw = call_anthropic(
            build_system_prompt(),
            build_user_message(change_types, targets, diff_text, source_text),
        )
        updates = parse_doc_updates(raw)
    except (requests.RequestException, RuntimeError) as exc:
        log.error("Doc sync skipped — Anthropic API call failed: %s", exc)
        return 0

    if not updates:
        log.info("Claude returned no doc updates — nothing to do")
        return 0

    changed = apply_updates(updates)
    if not changed:
        log.info("All returned docs already up to date — nothing to commit")
        return 0

    commit_and_push(changed, change_types)
    return 0


if __name__ == "__main__":
    sys.exit(main())
