"""
Module for analyzing C source code to locate function definitions.

This utility reads a C source file and provides functionality to search
for the definition of a specific function based on pattern matching.

Classes:
    SourceCodeAnalyzer -- Provides methods for parsing and locating C functions.
"""

from __future__ import annotations

import re
from typing import Iterable, Optional, Tuple

class SourceCodeAnalyzer:
    """
    Backward-compatible source loader plus a legacy regex-based function finder.

    Note:
        The production pipeline currently uses this class only as a source loader
        (`.source_code`). Function-boundary extraction is implemented by
        `PresenceConditionExtractor`.
    """
    _FALLBACK_ENCODINGS: Tuple[str, ...] = ("utf-8", "cp1252", "latin-1")

    def __init__(self, source_code_path: str):
        """
        Initializes the analyzer with a given C source file path.

        Args:
            source_code_path (str): Path to the C source file.
        """
        self.source_code_path = source_code_path
        self.source_code = self._load_source_code()

    @classmethod
    def _encodings_to_try(cls) -> Iterable[str]:
        return cls._FALLBACK_ENCODINGS

    def _read_with_encoding(self, encoding: str) -> str:
        with open(self.source_code_path, "r", encoding=encoding) as file:
            return file.read()

    def _load_source_code(self) -> str:
        """
        Loads the entire content of the C source file.

        Returns:
            str: Contents of the file as a string.

        Raises:
            Exception: If the file cannot be read.
        """
        last_error = None

        for encoding in self._encodings_to_try():
            try:
                content = self._read_with_encoding(encoding)
                if encoding != "utf-8":
                    print(
                        f"Warning: loaded '{self.source_code_path}' using fallback encoding '{encoding}'."
                    )
                return content
            except UnicodeDecodeError as e:
                last_error = e
                continue
            except Exception as e:
                print(f"Error loading source code: {e}")
                raise

        print(f"Error loading source code: {last_error}")
        raise last_error

    def _build_legacy_function_pattern(self, function_name: str) -> str:
        return rf'^\s*[\w\s\*]+{function_name}\s*\(.*?\)\s*\{{'

    def find_function_definition(self, function_name: str) -> Optional[re.Match]:
        """
        Searches for the definition of a specified function in the loaded source code.

        Args:
            function_name (str): Name of the function to search for.

        Returns:
            Optional[re.Match]: Match object representing the function declaration,
            or None if the function is not found.
        """
        pattern = self._build_legacy_function_pattern(function_name)
        match = re.search(pattern, self.source_code, re.MULTILINE | re.DOTALL)
        if match:
            print(f"Function '{function_name}' found in file '{self.source_code_path}'.")
            return match
        else:
            print(f"Function '{function_name}' NOT found in file '{self.source_code_path}'.")
            return None
