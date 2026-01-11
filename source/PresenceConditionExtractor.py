import re
from dataclasses import dataclass
from typing import List, Tuple, Optional, Dict


# ----------------------------
# Helpers: expression handling
# ----------------------------

_DEFINED_PAREN_RE = re.compile(r"\bdefined\s*\(\s*([A-Za-z_]\w*)\s*\)")
_DEFINED_BARE_RE  = re.compile(r"\bdefined\s+([A-Za-z_]\w*)\b")

def _normalize_defined(expr: str) -> str:
    """
    Normalize 'defined(X)' and 'defined X' to 'X' (CPP boolean atom),
    preserving explicit negations like '!defined(X)' -> '!X'.
    """
    e = expr.strip()
    # First normalize "defined(X)" -> "X"
    e = _DEFINED_PAREN_RE.sub(r"\1", e)
    # Then normalize "defined X" -> "X"
    e = _DEFINED_BARE_RE.sub(r"\1", e)
    # Normalize "! defined(X)" forms (after defined normalization it may become "!X" already)
    e = re.sub(r"!\s+", "!", e)
    # Collapse whitespace
    e = re.sub(r"\s+", " ", e).strip()
    return e


def _paren_wrap(expr: str) -> str:
    expr = expr.strip()
    if not expr:
        return expr
    # Avoid double parentheses in trivial cases; still safe to wrap.
    return f"({expr})"


def _neg(expr: str) -> str:
    """
    Logical negation with parentheses to preserve precedence.
    """
    expr = expr.strip()
    if not expr:
        return "!(/*empty*/)"
    return f"!{_paren_wrap(expr)}"


def _and_all(parts: List[str]) -> str:
    parts = [p.strip() for p in parts if p and p.strip()]
    if not parts:
        return "TRUE"
    if len(parts) == 1:
        return parts[0]
    return " && ".join(parts)


# -----------------------------------------
# Phase A: sanitize comments/strings (safe)
# -----------------------------------------

def _sanitize_c_text(text: str) -> str:
    """
    Remove C comments and string/char literals by replacing characters with spaces,
    preserving newlines and overall layout (line numbers remain stable).

    This prevents braces/parentheses inside comments/strings from breaking scans.
    """
    out = []
    i = 0
    n = len(text)

    IN_NONE = 0
    IN_LINE_COMMENT = 1
    IN_BLOCK_COMMENT = 2
    IN_STRING = 3
    IN_CHAR = 4

    state = IN_NONE
    while i < n:
        c = text[i]

        if state == IN_NONE:
            if c == "/" and i + 1 < n and text[i + 1] == "/":
                state = IN_LINE_COMMENT
                out.append(" ")
                out.append(" ")
                i += 2
                continue
            if c == "/" and i + 1 < n and text[i + 1] == "*":
                state = IN_BLOCK_COMMENT
                out.append(" ")
                out.append(" ")
                i += 2
                continue
            if c == '"':
                state = IN_STRING
                out.append(" ")
                i += 1
                continue
            if c == "'":
                state = IN_CHAR
                out.append(" ")
                i += 1
                continue

            out.append(c)
            i += 1
            continue

        if state == IN_LINE_COMMENT:
            # Keep newline, blank everything else
            if c == "\n":
                state = IN_NONE
                out.append("\n")
            else:
                out.append(" ")
            i += 1
            continue

        if state == IN_BLOCK_COMMENT:
            if c == "*" and i + 1 < n and text[i + 1] == "/":
                out.append(" ")
                out.append(" ")
                i += 2
                state = IN_NONE
            else:
                out.append("\n" if c == "\n" else " ")
                i += 1
            continue

        if state == IN_STRING:
            # Handle escapes
            if c == "\\" and i + 1 < n:
                out.append(" ")
                out.append(" ")
                i += 2
                continue
            if c == '"':
                out.append(" ")
                i += 1
                state = IN_NONE
            else:
                out.append("\n" if c == "\n" else " ")
                i += 1
            continue

        if state == IN_CHAR:
            if c == "\\" and i + 1 < n:
                out.append(" ")
                out.append(" ")
                i += 2
                continue
            if c == "'":
                out.append(" ")
                i += 1
                state = IN_NONE
            else:
                out.append("\n" if c == "\n" else " ")
                i += 1
            continue

    return "".join(out)


# -----------------------------------------------------
# Phase B: robust function index (multiline signatures)
# -----------------------------------------------------

_IDENT_START = re.compile(r"[A-Za-z_]")
_IDENT_BODY  = re.compile(r"[A-Za-z_0-9]")

def _build_line_starts(text: str) -> List[int]:
    starts = [0]
    for i, ch in enumerate(text):
        if ch == "\n":
            starts.append(i + 1)
    return starts

def _idx_to_line(line_starts: List[int], idx: int) -> int:
    # binary search
    lo, hi = 0, len(line_starts) - 1
    while lo <= hi:
        mid = (lo + hi) // 2
        if line_starts[mid] <= idx:
            lo = mid + 1
        else:
            hi = mid - 1
    return hi  # 0-based line index


def _skip_ws(text: str, i: int) -> int:
    n = len(text)
    while i < n and text[i].isspace():
        i += 1
    return i


def _parse_ident(text: str, i: int) -> Tuple[Optional[str], int]:
    n = len(text)
    if i >= n or not _IDENT_START.match(text[i]):
        return None, i
    j = i + 1
    while j < n and _IDENT_BODY.match(text[j]):
        j += 1
    return text[i:j], j


def _skip_balanced_parens(text: str, i: int) -> int:
    """
    If text[i] == '(', skip until matching ')', supporting nested parentheses.
    Assumes comments/strings already sanitized.
    """
    n = len(text)
    if i >= n or text[i] != "(":
        return i
    depth = 0
    while i < n:
        if text[i] == "(":
            depth += 1
        elif text[i] == ")":
            depth -= 1
            if depth == 0:
                return i + 1
        i += 1
    return i


def _skip_preprocessor_line(text: str, i: int) -> int:
    """
    Skip from '#' to end of (possibly continued) directive line.
    A continuation is recognized by a trailing backslash before newline.
    """
    n = len(text)
    # skip until newline, handling "\" continuation
    while i < n:
        # find end of line
        nl = text.find("\n", i)
        if nl == -1:
            return n
        # check if line ends with backslash (ignoring trailing spaces)
        k = nl - 1
        while k >= i and text[k] in " \t\r":
            k -= 1
        if k >= i and text[k] == "\\":
            i = nl + 1
            continue
        return nl + 1
    return n


def _build_function_index(sanitized_text: str) -> Dict[str, Tuple[int, int]]:
    """
    Build a mapping func_name -> (start_line, end_line) for function *definitions*.
    Works for multiline signatures and '{' on a separate line.

    Strategy (top-level only):
      - At brace_depth == 0, look for IDENT followed by '(' (parameter list).
      - Take IDENT immediately before that '(' as candidate name.
      - After matching ')', skip whitespace and common attribute-like constructs,
        then accept '{' as definition opener (reject if ';' before '{').
      - Then scan matching braces to find end line.

    Notes:
      - Comments/strings must be sanitized first.
      - Preprocessor lines are skipped because they can contain braces/parentheses.
    """
    text = sanitized_text
    line_starts = _build_line_starts(text)
    n = len(text)
    i = 0
    brace_depth = 0

    functions: Dict[str, Tuple[int, int]] = {}

    while i < n:
        c = text[i]

        # skip preprocessor lines
        if c == "#":
            i = _skip_preprocessor_line(text, i)
            continue

        # update brace depth
        if c == "{":
            brace_depth += 1
            i += 1
            continue
        if c == "}":
            brace_depth = max(0, brace_depth - 1)
            i += 1
            continue

        # Only attempt to detect function definitions at top level
        if brace_depth != 0:
            i += 1
            continue

        # Try parse an identifier
        ident, j = _parse_ident(text, i)
        if not ident:
            i += 1
            continue

        # Look ahead for '(' after optional whitespace
        k = _skip_ws(text, j)
        if k >= n or text[k] != "(":
            i = j
            continue

        # Candidate function name is 'ident'
        func_name = ident

        # Parse parameter list
        after_params = _skip_balanced_parens(text, k)
        after_params = _skip_ws(text, after_params)

        # After ')', there can be:
        #   - attributes: __attribute__((...))
        #   - macros with parentheses: CURL_ATTR_NONNULL(...)
        #   - qualifiers: const, noexcept (C++), etc.
        # We'll conservatively skip sequences of IDENT and balanced parens groups.
        t = after_params
        saw_semicolon = False
        saw_lbrace = False

        while t < n:
            t = _skip_ws(text, t)
            if t >= n:
                break

            if text[t] == ";":
                saw_semicolon = True
                t += 1
                break

            if text[t] == "{":
                saw_lbrace = True
                break

            # Skip attribute/macro tokens: IDENT [ ( ... ) ] possibly repeated
            tok, t2 = _parse_ident(text, t)
            if tok:
                t = _skip_ws(text, t2)
                # if followed by '(' -> skip balanced group (attributes/macros)
                if t < n and text[t] == "(":
                    t = _skip_balanced_parens(text, t)
                continue

            # If we see '(' directly (rare), skip it
            if text[t] == "(":
                t = _skip_balanced_parens(text, t)
                continue

            # Other tokens (e.g., '*', ',', etc.) - advance
            t += 1

        # We only accept if we found '{' before ';'
        if (not saw_lbrace) or saw_semicolon:
            i = j
            continue

        # We found a function definition for func_name starting at i (line)
        start_line = _idx_to_line(line_starts, i)

        # Now find the end by matching braces starting from the '{'
        body_i = t
        depth = 0
        p = body_i
        while p < n:
            if text[p] == "#":
                p = _skip_preprocessor_line(text, p)
                continue
            if text[p] == "{":
                depth += 1
            elif text[p] == "}":
                depth -= 1
                if depth == 0:
                    end_line = _idx_to_line(line_starts, p)
                    functions[func_name] = (start_line, end_line)
                    p += 1
                    break
            p += 1

        i = p
        continue

    return functions


# ---------------------------------------------------
# Phase C: CPP-exact presence condition line mapping
# ---------------------------------------------------

@dataclass
class _CondFrame:
    branches_seen: List[str]  # base expressions E1, E2, ... (normalized)
    current_expr: str         # active expression for the current branch (already exclusive)

class PresenceConditionExtractor:
    """
    Presence Condition (PC) extractor for function calls in C code under
    conditional compilation directives.

    This implementation computes *CPP-exact* branch conditions:
      - #elif E_k is active under: (!E_1 && !E_2 && ... && E_k)
      - #else is active under: (!E_1 && !E_2 && ...)

    The returned PC for a call site is the conjunction of all active conditional
    expressions from outer to inner directives. If none applies, PC is TRUE.
    """

    def __init__(self, source_code: str):
        self.source_code = source_code
        self.source_lines = source_code.splitlines()
        self._sanitized = _sanitize_c_text(source_code)
        self._san_lines = self._sanitized.splitlines()

        # Build function index once per file
        self._func_index = _build_function_index(self._sanitized)

        # Build PC map once per file (line -> PC)
        self._pc_at_line = self._build_pc_map_cpp_exact()

    def extract_pc_from_caller_context(self, caller_name: str, callee_name: str) -> List[str]:
        """
        Return all PCs under which callee is called inside caller.
        One PC per call occurrence (order preserved). If multiple calls on a line,
        the same PC repeats.

        Special returns:
          - ["CALLER_NOT_FOUND"] if caller definition not found
          - ["CALL_NOT_FOUND"] if no call site for callee in caller bounds
        """
        bounds = self._func_index.get(caller_name)
        if not bounds:
            return ["CALLER_NOT_FOUND"]

        start, end = bounds
        call_lines = self._find_calls_within_bounds(callee_name, start, end)

        if not call_lines:
            return ["CALL_NOT_FOUND"]

        return [self._pc_at_line[ln] for ln in call_lines]

    # -----------------------
    # PC map (CPP-exact)
    # -----------------------

    def _build_pc_map_cpp_exact(self) -> List[str]:
        """
        Compute PC for each physical line i:
          pc[i] = conjunction of active conditional expressions at that line,
                  or TRUE if no active directives.

        Directive parsing supports multiline directives with trailing backslashes.
        """
        pc_at_line: List[str] = ["TRUE"] * len(self.source_lines)

        active_stack: List[str] = []     # stack of active expressions (already exclusive)
        frame_stack: List[_CondFrame] = []  # frames for each #if nesting

        i = 0
        n = len(self.source_lines)

        def current_pc() -> str:
            return _and_all(active_stack)

        while i < n:
            raw = self.source_lines[i]
            line = raw.lstrip()

            # Assign PC for non-preprocessor lines (preprocessor lines are irrelevant for callsites)
            if not line.startswith("#"):
                pc_at_line[i] = current_pc()
                i += 1
                continue

            # Parse (possibly continued) directive text
            directive_text = line
            j = i
            while directive_text.rstrip().endswith("\\") and (j + 1) < n:
                directive_text = directive_text.rstrip()[:-1] + " " + self.source_lines[j + 1].lstrip()
                j += 1

            # Now interpret directive_text
            m_if = re.match(r"^\#\s*if\s+(.+)$", directive_text)
            m_ifdef = re.match(r"^\#\s*ifdef\s+([A-Za-z_]\w*)\s*$", directive_text)
            m_ifndef = re.match(r"^\#\s*ifndef\s+([A-Za-z_]\w*)\s*$", directive_text)
            m_elif = re.match(r"^\#\s*elif\s+(.+)$", directive_text)
            m_else = re.match(r"^\#\s*else\b", directive_text)
            m_endif = re.match(r"^\#\s*endif\b", directive_text)

            if m_if:
                base = _normalize_defined(m_if.group(1))
                # first branch: condition is base itself
                active_stack.append(base)
                frame_stack.append(_CondFrame(branches_seen=[base], current_expr=base))

            elif m_ifdef:
                base = m_ifdef.group(1)
                active_stack.append(base)
                frame_stack.append(_CondFrame(branches_seen=[base], current_expr=base))

            elif m_ifndef:
                base = f"!{m_ifndef.group(1)}"
                base = _normalize_defined(base)
                active_stack.append(base)
                frame_stack.append(_CondFrame(branches_seen=[base], current_expr=base))

            elif m_elif:
                if not frame_stack or not active_stack:
                    # Malformed file; ignore gracefully
                    pass
                else:
                    base = _normalize_defined(m_elif.group(1))
                    # Exclusive condition: (!E1 && !E2 && ...) && base
                    prev_bases = frame_stack[-1].branches_seen
                    excl_prefix = _and_all([_neg(e) for e in prev_bases])
                    excl = base if excl_prefix == "TRUE" else f"{excl_prefix} && {base}"

                    # Replace top active expression (current branch) with new excl expression
                    active_stack.pop()
                    active_stack.append(excl)

                    # Update frame
                    frame_stack[-1].branches_seen.append(base)
                    frame_stack[-1].current_expr = excl

            elif m_else:
                if not frame_stack or not active_stack:
                    pass
                else:
                    prev_bases = frame_stack[-1].branches_seen
                    else_expr = _and_all([_neg(e) for e in prev_bases])

                    active_stack.pop()
                    active_stack.append(else_expr)

                    frame_stack[-1].current_expr = else_expr

            elif m_endif:
                if active_stack:
                    active_stack.pop()
                if frame_stack:
                    frame_stack.pop()

            # Advance i by the number of physical lines consumed by a continued directive
            i = j + 1

        # Ensure any remaining unset lines are correct (they already are TRUE or set above)
        return pc_at_line

    # -----------------------
    # Call site finder
    # -----------------------

    def _find_calls_within_bounds(self, callee: str, start: int, end: int) -> List[int]:
        """
        Find all call occurrences of `callee` in [start, end], returning the line
        index for each occurrence (multiplicity preserved).

        This detects "call-like" patterns:  <callee> ( ... )
        It intentionally includes macro-like calls (e.g., DEBUGASSERT(...)).
        It ignores preprocessor lines.
        """
        # Quick regex for identifier + '('
        pattern = re.compile(rf"\b{re.escape(callee)}\s*\(")

        # Exclude obvious non-call keywords that also use '('
        keywords = {
            "if", "for", "while", "switch", "return", "sizeof", "typeof", "alignof"
        }
        if callee in keywords:
            # If a CSV lists a keyword as callee, treat as not found
            return []

        hits: List[int] = []
        for ln in range(start, end + 1):
            raw = self.source_lines[ln].lstrip()
            if raw.startswith("#"):
                continue

            # Use sanitized line to avoid matching inside comments/strings
            sline = self._san_lines[ln] if ln < len(self._san_lines) else self.source_lines[ln]

            for _ in pattern.finditer(sline):
                hits.append(ln)

        return hits
