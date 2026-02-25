from __future__ import annotations

from SourceCodeAnalyzer import SourceCodeAnalyzer


def load_source_code(source_path: str) -> str:
    """
    Load C source text from disk using the project's backward-compatible loader.

    This preserves current behavior, including encoding fallbacks implemented by
    `SourceCodeAnalyzer`.
    """
    return SourceCodeAnalyzer(source_path).source_code
