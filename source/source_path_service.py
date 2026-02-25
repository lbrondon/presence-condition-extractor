from __future__ import annotations

from path_resolver import is_regular_file, resolve_source_path


def resolve_existing_source_path(projects_dir: str, project: str, file_field: str) -> str:
    """
    Resolve a source path from CSV metadata and ensure the result is a regular file.

    Returns:
        Absolute/relative resolved path if it exists as a regular file; otherwise "".
    """
    resolved = resolve_source_path(projects_dir, project, file_field)
    if not resolved or not is_regular_file(resolved):
        return ""
    return resolved
