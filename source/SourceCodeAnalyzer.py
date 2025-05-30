import re
from typing import Optional

class SourceCodeAnalyzer:
    """
    Analyzes C source files to locate function definitions.
    """

    def __init__(self, source_code_path: str):
        """
        Initialize with the path to the source file.
        """
        self.source_code_path = source_code_path
        self.source_code = self._load_source_code()

    def _load_source_code(self) -> str:
        """
        Read and return the content of the source file.
        """
        try:
            with open(self.source_code_path, 'r') as file:
                return file.read()
        except Exception as e:
            print(f"Error loading source code: {e}")
            raise

    def find_function_definition(self, function_name: str) -> Optional[re.Match]:
        """
        Locate the definition of the given function in the source code.
        """
        pattern = rf'^\s*[\w\s\*]+{function_name}\s*\(.*?\)\s*\{{'
        match = re.search(pattern, self.source_code, re.MULTILINE | re.DOTALL)
        if match:
            print(f"Function '{function_name}' found in file '{self.source_code_path}'.")
            return match
        else:
            print(f"Function '{function_name}' NOT found in file '{self.source_code_path}'.")
            return None
