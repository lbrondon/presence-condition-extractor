import re
from typing import List, Optional, Tuple

class PresenceConditionExtractor:
    """
    Presence-condition (PC) extraction for C code guarded by preprocessor directives.

    This class computes the boolean presence condition under which each invocation
    of a target callee occurs within a given caller function, honoring the semantics
    of C preprocessor conditionals:

      - `#if`, `#ifdef`, `#ifndef` push a new conditional frame onto a stack.
      - `#elif` replaces the *current* branch condition at that nesting level.
      - `#else` becomes the conjunction of the negations of *all prior branches*
        in the same conditional chain (i.e., `!b1 && !b2 && ...`).
      - `#endif` pops the current frame.

    Key design choices:
      • Comment removal preserves directive lines so conditional structure is intact.
      • Call-site discovery excludes preprocessor lines (`#...`) to avoid false matches.
      • Multi-line `#if/#elif` conditions ending with a backslash `\` are correctly
        concatenated before normalization.
      • `defined(M)` and `defined M` are both normalized to `M`, and `!defined(M)` to `!M`.

    The public API returns one PC per call site occurrence, preserving the order
    of calls in the caller’s body.

    Usage:
        extractor = PresenceConditionExtractor(source_code_str)
        pcs = extractor.extract_pc_from_caller_context("caller_name", "callee_name")
    """

    # ------------ Initialization & pre-processing ------------

    def __init__(self, source_code: str):
        """
        Build an extractor over the provided C source code.

        Args:
            source_code: Raw C translation unit as a single string. It may contain
                         comments and preprocessor directives.

        Notes:
            The constructor strips both block (`/* ... */`) and line (`// ...`) comments
            while leaving preprocessor lines untouched, then stores a split-by-line
            representation for subsequent analysis.
        """
        self._raw = source_code
        self._clean = self._strip_comments_preserving_directives(source_code)
        self.lines = self._clean.splitlines()

    def _strip_comments_preserving_directives(self, text: str) -> str:
        """
        Remove comments without deleting preprocessor directive lines.

        We first drop `/* ... */` blocks (DOTALL to span lines), then remove `// ...`
        end-of-line comments. Directives like `#if ...` remain intact.

        Args:
            text: Raw C source code.

        Returns:
            The source code with comments removed but directives preserved.
        """
        # remove /* ... */ (multi-line) first
        no_block = re.sub(r"/\*.*?\*/", "", text, flags=re.DOTALL)
        # remove // ... (end-of-line)
        no_line = re.sub(r"//.*?$", "", no_block, flags=re.MULTILINE)
        return no_line

    # ---------------- Public API ------------------

    def extract_pc_from_caller_context(self, caller_name: str, callee_name: str) -> List[str]:
        """
        Compute the presence condition(s) under which the given callee is invoked
        within the specified caller.

        Args:
            caller_name: Name of the function that contains the call(s).
            callee_name: Name of the function being called.

        Returns:
            A list of presence-condition strings, one per call site occurrence,
            in lexical order. If the caller cannot be found, returns
            `["CALLER_NOT_FOUND"]`. If the caller exists but no call to the
            callee appears within its body, returns `["CALL_NOT_FOUND"]`.

        Notes:
            We build a line→PC map once per caller and then read off the PC for
            each call line to ensure consistent `#elif/#else` handling.
        """
        start, end = self._find_function_bounds(caller_name)
        if start is None or end is None:
            return ["CALLER_NOT_FOUND"]

        call_lines = self._find_calls_within_bounds(callee_name, start, end)
        if not call_lines:
            return ["CALL_NOT_FOUND"]

        pcs: List[str] = []
        pc_by_line = self._compute_pc_map(start, end)
        for ln in call_lines:
            pcs.append(pc_by_line.get(ln, "TRUE"))
        return pcs

    # --------------- Function-boundary discovery ----------------

    def _find_function_bounds(self, func_name: str) -> Tuple[Optional[int], Optional[int]]:
        """
        Locate the *definition* (not prototype) of `func_name` and return the
        curly-brace span as (start_index_of_open_brace, end_index_of_matching_close).

        Strategy:
            1) Find a line matching `\\b<name>\\s*\\(` to identify candidate signatures.
            2) From that line forward, ensure we encounter a '{' *before* any ';'
               to distinguish a definition from a prototype.
            3) Perform brace counting from that '{' to find the matching closing brace.

        Args:
            func_name: Function identifier to locate.

        Returns:
            (start_line_index, end_line_index) if found; otherwise (None, None).
        """
        name = re.escape(func_name)
        sig = re.compile(r"\b" + name + r"\s*\(")
        n = len(self.lines)
        i = 0
        while i < n:
            if not sig.search(self.lines[i]):
                i += 1
                continue

            # Search forward for '{' before any ';' to confirm a definition
            j = i
            open_brace = None
            saw_semicolon = False
            while j < n:
                cur = self.lines[j]
                if "{" in cur:
                    open_brace = j
                    break
                if ";" in cur:
                    saw_semicolon = True
                    break
                j += 1

            # If it was a prototype or no '{' found, skip and continue scanning
            if saw_semicolon or open_brace is None:
                i = max(i + 1, j + 1)
                continue

            # Balanced-brace scan to find the function body end
            depth = 0
            k = open_brace
            while k < n:
                depth += self.lines[k].count("{")
                depth -= self.lines[k].count("}")
                if depth == 0:
                    return open_brace, k
                k += 1

            i = max(i + 1, j + 1)

        return None, None

    # --------------- Call-site discovery -----------------

    def _find_calls_within_bounds(self, callee: str, start: int, end: int) -> List[int]:
        """
        Collect line indices for occurrences of `callee(` within [start, end],
        ignoring any line that is itself a preprocessor directive (i.e., begins
        with `#` possibly after whitespace).

        Args:
            callee: Function name being invoked.
            start:  Index of the opening brace of the caller.
            end:    Index of the matching closing brace of the caller.

        Returns:
            List of source line indices where `callee(` appears.
        """
        pat = re.compile(r"\b{}\s*\(".format(re.escape(callee)))
        out: List[int] = []
        for i in range(start, end + 1):
            line = self.lines[i]
            if re.match(r"^\s*#", line):  # skip preprocessor directive lines
                continue
            if pat.search(line):
                out.append(i)
        return out

    # ------------ Preprocessor state machine --------

    class _PPFrame:
        """
        A stack frame representing one active conditional chain at a given
        nesting level.

        Attributes:
            current: The condition currently active for this level (after the
                     last `#if/#elif/#else` seen at this depth).
            alts:    The list of mutually exclusive branch conditions that have
                     appeared in this chain so far (used to build the `#else`
                     as `!b1 && !b2 && ...`).
        """
        __slots__ = ("current", "alts")
        def __init__(self, current: str):
            self.current = current
            self.alts = [current]

    def _normalize_expr(self, expr: str) -> str:
        """
        Normalize a preprocessor boolean expression into a simplified textual form:

          - `defined(M)`  → `M`
          - `defined M`   → `M`         (GNU extension)
          - `!defined(M)` → `!M`

        Args:
            expr: Raw expression text after `#if` or `#elif` (possibly multi-line,
                  after concatenation if line-continued).

        Returns:
            A stripped string with the above normalizations applied.
        """
        # defined(M)  -> M
        expr = re.sub(r"\bdefined\s*\(\s*(\w+)\s*\)", r"\1", expr)
        # !defined(M) -> !M
        expr = re.sub(r"!\s*defined\s*\(\s*(\w+)\s*\)", r"!\1", expr)
        # GNU: defined M -> M
        expr = re.sub(r"\bdefined\s+(\w+)\b", r"\1", expr)
        return expr.strip()

    def _collect_if_or_elif_expr(self, i: int) -> Tuple[str, int]:
        """
        Collect the expression following `#if` or `#elif`, handling line
        continuations that end with backslash (`\`). The accumulated text is
        then normalized.

        Args:
            i: Index of the line that starts with `#if` or `#elif`.

        Returns:
            (normalized_expression, new_index) where `new_index` is the index of
            the last physical line consumed in the continuation group.
        """
        line = self.lines[i]
        m_if   = re.match(r"^\s*#\s*if\s+(.*)$", line)
        m_elif = re.match(r"^\s*#\s*elif\s+(.*)$", line)
        raw = ""
        if m_if:
            raw = m_if.group(1)
        elif m_elif:
            raw = m_elif.group(1)
        else:
            return "", i

        acc = [raw.rstrip("\\").rstrip()]
        j = i
        # Continue while the current line ends with a backslash (line continuation)
        while j < len(self.lines) and self.lines[j].rstrip().endswith("\\"):
            j += 1
            if j >= len(self.lines):
                break
            acc.append(self.lines[j].strip().rstrip("\\").rstrip())

        expr = " ".join(acc)
        expr = self._normalize_expr(expr)
        return expr, j

    def _compute_pc_map(self, start: int, end: int) -> dict:
        """
        Single pass over [start..end] that builds a map: source line → active PC.

        We maintain a stack of `_PPFrame` objects representing the nested
        conditional context. For a non-directive line, the current PC is the
        conjunction of `frame.current` across the stack. For directives:

          - `#if/#ifdef/#ifndef`: push a frame for the new branch.
          - `#elif`:             update the *current* frame’s `current` and append
                                 the alternative to `alts`.
          - `#else`:             compute `!b1 && !b2 && ...` from `alts` so far.
          - `#endif`:            pop one frame.

        Args:
            start: Caller’s opening brace line index.
            end:   Caller’s matching closing brace line index.

        Returns:
            A dict mapping each non-directive source line index in the caller’s
            body to the boolean presence condition active at that point.
        """
        pc_by_line: dict = {}
        stack: List[PresenceConditionExtractor._PPFrame] = []

        i = start
        while i <= end:
            line = self.lines[i]

            # #if ...
            if re.match(r"^\s*#\s*if\b", line):
                expr, i = self._collect_if_or_elif_expr(i)
                if expr == "":
                    expr = "TRUE"
                stack.append(self._PPFrame(expr))
                i += 1
                continue

            # #ifdef NAME
            m_ifdef = re.match(r"^\s*#\s*ifdef\s+(\w+)", line)
            if m_ifdef:
                stack.append(self._PPFrame(m_ifdef.group(1)))
                i += 1
                continue

            # #ifndef NAME
            m_ifndef = re.match(r"^\s*#\s*ifndef\s+(\w+)", line)
            if m_ifndef:
                stack.append(self._PPFrame(f"!{m_ifndef.group(1)}"))
                i += 1
                continue

            # #elif ...
            if re.match(r"^\s*#\s*elif\b", line):
                expr, i = self._collect_if_or_elif_expr(i)
                if stack:
                    frame = stack[-1]
                    frame.current = expr if expr else "TRUE"
                    frame.alts.append(frame.current)
                i += 1
                continue

            # #else
            if re.match(r"^\s*#\s*else\b", line):
                if stack:
                    frame = stack[-1]
                    # else is the conjunction of the negations of all previous branches
                    if frame.alts:
                        neg = [f"!({b})" for b in frame.alts]
                        frame.current = " && ".join(neg)
                    else:
                        frame.current = "TRUE"
                i += 1
                continue

            # #endif
            if re.match(r"^\s*#\s*endif\b", line):
                if stack:
                    stack.pop()
                i += 1
                continue

            # Non-directive line: compute the current PC as the conjunction
            cur_pc = " && ".join(fr.current for fr in stack) if stack else "TRUE"
            pc_by_line[i] = cur_pc if cur_pc else "TRUE"
            i += 1

        return pc_by_line
