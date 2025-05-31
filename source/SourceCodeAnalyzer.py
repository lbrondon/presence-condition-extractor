"""
Module for analyzing C source code to locate function definitions.

This utility reads a C source file and provides functionality to search
for the definition of a specific function based on pattern matching.

Classes:
    SourceCodeAnalyzer -- Provides methods for parsing and locating C functions.
"""

import re
from typing import Optional

class SourceCodeAnalyzer:
    """
    Analyzes C source files to locate function definitions using regular expressions.
    """

    def __init__(self, source_code_path: str):
        """
        Initializes the analyzer with a given C source file path.

        Args:
            source_code_path (str): Path to the C source file.
        """
        self.source_code_path = source_code_path
        self.source_code = self._load_source_code()

    def _load_source_code(self) -> str:
        """
        Loads the entire content of the C source file.

        Returns:
            str: Contents of the file as a string.

        Raises:
            Exception: If the file cannot be read.
        """
        try:
            with open(self.source_code_path, 'r') as file:
                return file.read()
        except Exception as e:
            print(f"Error loading source code: {e}")
            raise

    def find_function_definition(self, function_name: str) -> Optional[re.Match]:
        """
        Searches for the definition of a specified function in the loaded source code.

        Args:
            function_name (str): Name of the function to search for.

        Returns:
            Optional[re.Match]: Match object representing the function declaration,
            or None if the function is not found.
        """
        pattern = rf'^\s*[\w\s\*]+{function_name}\s*\(.*?\)\s*\{{'
        match = re.search(pattern, self.source_code, re.MULTILINE | re.DOTALL)
        if match:
            print(f"Function '{function_name}' found in file '{self.source_code_path}'.")
            return match
        else:
            print(f"Function '{function_name}' NOT found in file '{self.source_code_path}'.")
            return None
