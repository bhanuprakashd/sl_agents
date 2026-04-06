"""Obsidian Vault tools — read, write, search, and manage notes in an Obsidian vault.

Provides agents with persistent, human-readable knowledge storage for ADRs,
design docs, research notes, runbooks, and cross-session memory.
Requires OBSIDIAN_VAULT_PATH env var pointing to the vault directory.
"""

import json
import os
from pathlib import Path


def _vault_path() -> Path | None:
    """Return the configured vault path, or None if not set."""
    raw = os.environ.get("OBSIDIAN_VAULT_PATH")
    if not raw:
        return None
    p = Path(raw)
    return p if p.is_dir() else None


def _safe_path(note_path: str) -> Path | None:
    """Resolve a note path safely within the vault, preventing traversal."""
    vault = _vault_path()
    if vault is None:
        return None
    resolved = (vault / note_path).resolve()
    if not str(resolved).startswith(str(vault.resolve())):
        return None
    return resolved


def vault_read_note(path: str) -> str:
    """Read a note from the Obsidian vault.

    Args:
        path: Relative path within the vault (e.g. 'ADRs/001-tech-stack.md').

    Returns:
        The note content as a string, or an error message.
    """
    resolved = _safe_path(path)
    if resolved is None:
        return "[vault error] OBSIDIAN_VAULT_PATH not set or path invalid"
    if not resolved.is_file():
        return f"[vault error] Note not found: {path}"
    return resolved.read_text(encoding="utf-8")


def vault_write_note(path: str, content: str) -> str:
    """Create or overwrite a note in the Obsidian vault.

    Args:
        path: Relative path within the vault (e.g. 'Research/market-analysis.md').
        content: Full markdown content for the note.

    Returns:
        Confirmation message with the note path.
    """
    resolved = _safe_path(path)
    if resolved is None:
        return "[vault error] OBSIDIAN_VAULT_PATH not set or path invalid"
    resolved.parent.mkdir(parents=True, exist_ok=True)
    resolved.write_text(content, encoding="utf-8")
    return f"Note written: {path}"


def vault_append_note(path: str, content: str) -> str:
    """Append content to an existing note in the Obsidian vault.

    Args:
        path: Relative path within the vault.
        content: Markdown content to append at the end of the note.

    Returns:
        Confirmation message.
    """
    resolved = _safe_path(path)
    if resolved is None:
        return "[vault error] OBSIDIAN_VAULT_PATH not set or path invalid"
    if not resolved.is_file():
        return f"[vault error] Note not found: {path}. Use vault_write_note to create it."
    existing = resolved.read_text(encoding="utf-8")
    resolved.write_text(existing.rstrip() + "\n\n" + content, encoding="utf-8")
    return f"Content appended to: {path}"


def vault_search(query: str, folder: str = "") -> str:
    """Search notes in the Obsidian vault by keyword.

    Args:
        query: Search term to find in note content and filenames.
        folder: Optional subfolder to limit search scope (e.g. 'ADRs').

    Returns:
        List of matching notes with context snippets.
    """
    vault = _vault_path()
    if vault is None:
        return "[vault error] OBSIDIAN_VAULT_PATH not set"
    search_root = vault / folder if folder else vault
    if not search_root.is_dir():
        return f"[vault error] Folder not found: {folder}"

    query_lower = query.lower()
    results = []
    for md_file in search_root.rglob("*.md"):
        rel = md_file.relative_to(vault)
        try:
            text = md_file.read_text(encoding="utf-8")
        except (OSError, UnicodeDecodeError):
            continue
        if query_lower in text.lower() or query_lower in str(rel).lower():
            # Extract a context snippet around the first match
            idx = text.lower().find(query_lower)
            if idx >= 0:
                start = max(0, idx - 80)
                end = min(len(text), idx + len(query) + 80)
                snippet = text[start:end].replace("\n", " ").strip()
                results.append(f"- **{rel}**: ...{snippet}...")
            else:
                results.append(f"- **{rel}**: (filename match)")
        if len(results) >= 20:
            break

    if not results:
        return f"No notes found matching '{query}'"
    return f"Found {len(results)} notes:\n" + "\n".join(results)


def vault_list_notes(folder: str = "", recursive: bool = True) -> str:
    """List notes in the Obsidian vault.

    Args:
        folder: Subfolder to list (e.g. 'ADRs'). Empty string for vault root.
        recursive: Whether to include subfolders.

    Returns:
        List of note paths relative to the vault root.
    """
    vault = _vault_path()
    if vault is None:
        return "[vault error] OBSIDIAN_VAULT_PATH not set"
    list_root = vault / folder if folder else vault
    if not list_root.is_dir():
        return f"[vault error] Folder not found: {folder}"

    glob_fn = list_root.rglob if recursive else list_root.glob
    notes = sorted(str(f.relative_to(vault)) for f in glob_fn("*.md"))
    if not notes:
        return f"No notes found in '{folder or '/'}'"
    return f"{len(notes)} notes:\n" + "\n".join(f"- {n}" for n in notes[:50])


def vault_delete_note(path: str) -> str:
    """Delete a note from the Obsidian vault (moves to .trash/ for safety).

    Args:
        path: Relative path within the vault.

    Returns:
        Confirmation message.
    """
    resolved = _safe_path(path)
    if resolved is None:
        return "[vault error] OBSIDIAN_VAULT_PATH not set or path invalid"
    if not resolved.is_file():
        return f"[vault error] Note not found: {path}"
    vault = _vault_path()
    trash = vault / ".trash"
    trash.mkdir(exist_ok=True)
    dest = trash / resolved.name
    resolved.rename(dest)
    return f"Note moved to trash: {path} → .trash/{resolved.name}"
