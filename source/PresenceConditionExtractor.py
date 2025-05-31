"""
Module for extracting presence conditions from C source code.

This class parses C source code and identifies the presence conditions (PCs)
under which a callee function is invoked from within a caller function. It analyzes
conditional compilation directives (#if, #ifdef, #ifndef, etc.) surrounding the call.

Classes:
    PresenceConditionExtractor: Analyzes preprocessor conditionals to extract PCs.
"""

import re
from typing import List

class PresenceConditionExtractor:
    """
    Extracts presence conditions for function calls in C source code based on
    conditional compilation directives.
    """

    def __init__(self, source_code: str):
        """
        Initialize with source code as a string.

        Args:
            source_code (str): Raw C source code.
        """
        self.source_code_lines = source_code.splitlines()

    def _normalize_expression(self, expr: str) -> str:
        """
        Normalize preprocessor expressions by removing 'defined' syntax.

        Args:
            expr (str): Raw expression from preprocessor directive.

        Returns:
            str: Simplified boolean expression.
        """
        expr = re.sub(r'defined\s*\(\s*(\w+)\s*\)', r'\1', expr)
        expr = re.sub(r'!\s*defined\s*\(\s*(\w+)\s*\)', r'!\1', expr)
        return expr.strip()

    def extract_pc_from_caller_context(self, caller_name: str, callee_name: str) -> str:
        """
        Extracts the presence condition (PC) under which the callee is called
        within the given caller function.

        Args:
            caller_name (str): Name of the caller function.
            callee_name (str): Name of the callee function.

        Returns:
            str: Boolean expression representing the PC, or an error message.
        """
        caller_start, caller_end = self._find_function_bounds(caller_name)
        if caller_start is None or caller_end is None:
            return "CALLER_NOT_FOUND"

        callee_line = self._find_call_within_bounds(callee_name, caller_start, caller_end)
        if callee_line is None:
            return "CALL_NOT_FOUND"

        return self._resolve_pc_from_blocks(caller_start, callee_line)

    def _find_function_bounds(self, func_name: str):
        """
        Determine the start and end line indices of a given function.

        Args:
            func_name (str): Function name to search.

        Returns:
            tuple: (start_line, end_line) indices or (None, None) if not found.
        """
        pattern = re.compile(r'\b{}\s*\([^)]*\)\s*\{{'.format(re.escape(func_name)))
        in_func = False
        brace_count = 0
        start, end = None, None

        for i, line in enumerate(self.source_code_lines):
            if not in_func and pattern.search(line):
                start = i
                in_func = True
                brace_count += line.count('{') - line.count('}')
                continue
            if in_func:
                brace_count += line.count('{') - line.count('}')
                if brace_count == 0:
                    end = i
                    break
        return start, end

    def _find_call_within_bounds(self, callee: str, start: int, end: int):
        """
        Search for the callee function call within the bounds of the caller.

        Args:
            callee (str): Name of the function being called.
            start (int): Start line of caller.
            end (int): End line of caller.

        Returns:
            int or None: Line number of the call or None if not found.
        """
        pattern = re.compile(r'\b{}\s*\('.format(re.escape(callee)))
        for i in range(start, end + 1):
            if pattern.search(self.source_code_lines[i]):
                return i
        return None

    def _resolve_pc_from_blocks(self, start: int, line_target: int) -> str:
        """
        Resolve the active presence condition at a given line using the stack
        of encountered preprocessor blocks.

        Args:
            start (int): Start line of the caller function.
            line_target (int): Line of the callee invocation.

        Returns:
            str: Boolean expression of the active PC or "TRUE" if unconditional.
        """
        block_stack: List[str] = []
        branch_stack: List[List[str]] = []

        for i in range(start, line_target + 1):
            line = self.source_code_lines[i].strip()

            if line.startswith("#if "):
                exprs = re.findall(r'#\s*if\s+(.+)', line)
                if exprs:
                    expr = self._normalize_expression(exprs[0])
                    block_stack.append(expr)
                    branch_stack.append([expr])

            elif line.startswith("#ifdef"):
                features = re.findall(r'#\s*ifdef\s+(\w+)', line)
                if features:
                    expr = features[0]
                    block_stack.append(expr)
                    branch_stack.append([expr])

            elif line.startswith("#ifndef"):
                features = re.findall(r'#\s*ifndef\s+(\w+)', line)
                if features:
                    expr = f"!{features[0]}"
                    block_stack.append(expr)
                    branch_stack.append([expr])

            elif line.startswith("#elif"):
                exprs = re.findall(r'#\s*elif\s+(.+)', line)
                if exprs and block_stack and branch_stack:
                    block_stack.pop()
                    new_expr = self._normalize_expression(exprs[0])
                    branch_stack[-1].append(new_expr)
                    block_stack.append(new_expr)

            elif line.startswith("#else"):
                if branch_stack:
                    negated = [f"!({x})" for x in branch_stack[-1]]
                    expr = " && ".join(negated)
                    block_stack.pop()
                    block_stack.append(expr)

            elif line.startswith("#endif"):
                if block_stack:
                    block_stack.pop()
                if branch_stack:
                    branch_stack.pop()

        return " && ".join(block_stack) if block_stack else "TRUE"
