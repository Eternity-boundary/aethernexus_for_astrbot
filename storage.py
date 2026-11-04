"""Local settings and revisioned prompts ported from PromptStore/BudgetService.

Copyright (c) 2026 Skylight Software Organization.
Created by EternityBoundary
All rights reserved.
SPDX-License-Identifier: GPL-3.0-only

File: storage.py
Project: AetherNexus for AstrBot
"""

import json
import re
import sqlite3
import time
import uuid
from pathlib import Path


def render_variables(text: str, variables: dict) -> str:
    """Substitute prompt variables once without evaluating inserted content.

    Args:
        text: Template of at most 65536 characters.
        variables: At most 32 named string values.

    Returns:
        Rendered template.

    Raises:
        ValueError: A variable is missing or input exceeds the port's limits.
    """
    if not isinstance(text, str) or len(text) > 65536:
        raise ValueError("Template must be a string of at most 65536 characters.")
    if not isinstance(variables, dict) or len(variables) > 32:
        raise ValueError("Expected at most 32 variables.")
    if any(
        not isinstance(k, str) or not 1 <= len(k) <= 64 or not isinstance(v, str)
        for k, v in variables.items()
    ):
        raise ValueError("Variable names and values must be strings.")
    for name in re.findall(r"{{(.*?)}}", text, flags=re.DOTALL):
        if name not in variables:
            raise ValueError(f"Missing variable: {name[:64]}")
    if "{{" in re.sub(r"{{.*?}}", "", text, flags=re.DOTALL):
        raise ValueError("Unclosed template variable.")
    result = re.sub(r"{{(.*?)}}", lambda m: variables[m[1]], text, flags=re.DOTALL)
    if len(result) > 65536:
        raise ValueError("Rendered template is too large.")
    return result


class LocalStore:
    """Store non-secret documents with transactional revision checks."""

    def __init__(self, directory: Path):
        """Create a database outside the plugin installation.

        Args:
            directory: AstrBot plugin data directory or an isolated test directory.
        """
        directory.mkdir(parents=True, exist_ok=True)
        self.path = directory / "workspace.sqlite3"
        with sqlite3.connect(self.path) as db:
            db.execute(
                "CREATE TABLE IF NOT EXISTS settings (id INTEGER PRIMARY KEY, value TEXT NOT NULL)"
            )
            db.execute(
                "CREATE TABLE IF NOT EXISTS prompts (id TEXT, version INTEGER, value TEXT NOT NULL, PRIMARY KEY(id, version))"
            )

    def settings(self, value: dict | None = None) -> dict:
        """Read or merge non-secret workspace preferences.

        Args:
            value: Optional appearance, budget and usage command preferences.

        Returns:
            Current persisted settings.

        Raises:
            ValueError: Settings are invalid.
        """
        with sqlite3.connect(self.path) as db:
            row = db.execute("SELECT value FROM settings WHERE id = 1").fetchone()
            current = {
                "theme": "system",
                "monthly_usd_cents": None,
                "usage_command_enabled": False,
            }
            if row:
                current.update(json.loads(row[0]))
            if value is not None:
                if not isinstance(value, dict):
                    raise ValueError("Settings must be a JSON object.")
                theme = value.get("theme", current["theme"])
                budget = value.get("monthly_usd_cents", current["monthly_usd_cents"])
                command_enabled = value.get(
                    "usage_command_enabled", current["usage_command_enabled"]
                )
                if type(command_enabled) is not bool:
                    raise ValueError("usage_command_enabled must be a boolean.")
                if theme not in ("system", "light", "dark"):
                    raise ValueError("Invalid theme.")
                if budget is not None and (
                    type(budget) is not int or not 1 <= budget <= 100_000_000_000
                ):
                    raise ValueError(
                        "Budget must be between 1 and 100000000000 USD cents."
                    )
                current = {
                    "theme": theme,
                    "monthly_usd_cents": budget,
                    "usage_command_enabled": command_enabled,
                }
                db.execute(
                    "INSERT OR REPLACE INTO settings VALUES (1, ?)",
                    (json.dumps(current),),
                )
        return current

    def prompts(self, draft: dict | None = None, remove: str = "") -> list[dict]:
        """Read, append, or delete prompt revisions atomically.

        Args:
            draft: Optional revision using the native name/model/instructions/input/options fields.
            remove: Optional local prompt ID to delete with its history.

        Returns:
            All revisions, including a newly saved revision if provided.

        Raises:
            ValueError: Limits, content, or the optimistic version check fail.
        """
        with sqlite3.connect(self.path, timeout=5) as db:
            db.execute("BEGIN IMMEDIATE")
            rows = db.execute("SELECT value FROM prompts ORDER BY rowid").fetchall()
            revisions = [json.loads(row[0]) for row in rows]
            if remove:
                if not any(r["id"] == remove for r in revisions):
                    raise ValueError("Prompt no longer exists.")
                db.execute("DELETE FROM prompts WHERE id = ?", (remove,))
                return [r for r in revisions if r["id"] != remove]
            if draft is not None:
                if not isinstance(draft, dict):
                    raise ValueError("Expected a prompt object.")
                clean = {}
                for field in ("name", "model", "instructions", "input"):
                    val = draft.get(field, "")
                    if not isinstance(val, str) or len(val) > (
                        256 if field in ("name", "model") else 65536
                    ):
                        raise ValueError(f"Invalid prompt {field}.")
                    clean[field] = val
                if not clean["name"].strip() or not clean["model"].strip():
                    raise ValueError("Prompt name and model are required.")
                options = draft.get("options", {})
                if isinstance(options, str):
                    options = json.loads(options)
                if not isinstance(options, dict) or len(json.dumps(options)) > 65536:
                    raise ValueError("Prompt options must be a JSON object.")
                clean["options"] = options
                prompt_id = draft.get("id", "")
                latest = max(
                    (r["version"] for r in revisions if r["id"] == prompt_id), default=0
                )
                if (
                    type(draft.get("version", 0)) is not int
                    or draft.get("version", 0) != latest
                    or (prompt_id and not latest)
                ):
                    raise ValueError(
                        "Prompt changed in another editor. Refresh before saving."
                    )
                if latest >= 100 or (
                    not prompt_id and len({r["id"] for r in revisions}) >= 100
                ):
                    raise ValueError(
                        "Prompt catalog limit reached (100 prompts, 100 versions each)."
                    )
                clean.update(
                    id=prompt_id or f"local_{uuid.uuid4().hex}",
                    version=latest + 1,
                    modified=int(time.time()),
                )
                if len(json.dumps(revisions + [clean]).encode()) > 8 * 1024 * 1024:
                    raise ValueError("Prompt catalog exceeds 8 MiB.")
                db.execute(
                    "INSERT INTO prompts VALUES (?, ?, ?)",
                    (
                        clean["id"],
                        clean["version"],
                        json.dumps(clean, ensure_ascii=False),
                    ),
                )
                revisions.append(clean)
        return revisions
