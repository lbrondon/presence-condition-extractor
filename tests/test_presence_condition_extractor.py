import sys
import unittest
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
SOURCE_DIR = ROOT / "source"
if str(SOURCE_DIR) not in sys.path:
    sys.path.insert(0, str(SOURCE_DIR))

from PresenceConditionExtractor import PresenceConditionExtractor  # noqa: E402


class PresenceConditionExtractorTests(unittest.TestCase):
    def test_returns_true_for_unconditional_call(self):
        src = (
            "void callee(void) {}\n"
            "int caller(void) {\n"
            "  callee();\n"
            "  return 0;\n"
            "}\n"
        )
        extractor = PresenceConditionExtractor(src)
        self.assertEqual(extractor.extract_pc_from_caller_context("caller", "callee"), ["TRUE"])

    def test_handles_ifndef_as_negated_atom(self):
        src = (
            "void callee(void) {}\n"
            "int caller(void) {\n"
            "#ifndef FEATURE_X\n"
            "  callee();\n"
            "#endif\n"
            "  return 0;\n"
            "}\n"
        )
        extractor = PresenceConditionExtractor(src)
        self.assertEqual(extractor.extract_pc_from_caller_context("caller", "callee"), ["!FEATURE_X"])

    def test_parses_multiline_preprocessor_directive(self):
        src = (
            "void callee(void) {}\n"
            "int caller(void) {\n"
            "#if defined(FOO) \\\n"
            " || defined(BAR)\n"
            "  callee();\n"
            "#endif\n"
            "  return 0;\n"
            "}\n"
        )
        extractor = PresenceConditionExtractor(src)
        self.assertEqual(extractor.extract_pc_from_caller_context("caller", "callee"), ["FOO || BAR"])

    def test_normalizes_defined_without_parentheses(self):
        src = (
            "void callee(void) {}\n"
            "int caller(void) {\n"
            "#if defined FOO\n"
            "  callee();\n"
            "#endif\n"
            "  return 0;\n"
            "}\n"
        )
        extractor = PresenceConditionExtractor(src)
        self.assertEqual(extractor.extract_pc_from_caller_context("caller", "callee"), ["FOO"])

    def test_ignores_comment_and_string_false_positives(self):
        src = (
            "void callee(void) {}\n"
            "int caller(void) {\n"
            "  // callee(); in comment\n"
            "  char *s = \"#if X callee() { }\";\n"
            "#if FLAG\n"
            "  callee();\n"
            "#endif\n"
            "  return 0;\n"
            "}\n"
        )
        extractor = PresenceConditionExtractor(src)
        self.assertEqual(extractor.extract_pc_from_caller_context("caller", "callee"), ["FLAG"])

    def test_preserves_multiple_calls_on_same_line_in_core_extractor(self):
        src = (
            "void callee(void) {}\n"
            "int caller(void) {\n"
            "  callee(); callee();\n"
            "  return 0;\n"
            "}\n"
        )
        extractor = PresenceConditionExtractor(src)
        self.assertEqual(extractor.extract_pc_from_caller_context("caller", "callee"), ["TRUE", "TRUE"])

    def test_handles_nested_else_branch_condition(self):
        src = (
            "void callee(void) {}\n"
            "int caller(void) {\n"
            "#if OUTER\n"
            "#if INNER\n"
            "  return 1;\n"
            "#else\n"
            "  callee();\n"
            "#endif\n"
            "#endif\n"
            "  return 0;\n"
            "}\n"
        )
        extractor = PresenceConditionExtractor(src)
        self.assertEqual(extractor.extract_pc_from_caller_context("caller", "callee"), ["OUTER && !(INNER)"])

    def test_finds_function_with_attribute_after_signature(self):
        src = (
            "void callee(void) {}\n"
            "int caller(void) __attribute__((unused))\n"
            "{\n"
            "  callee();\n"
            "  return 0;\n"
            "}\n"
        )
        extractor = PresenceConditionExtractor(src)
        self.assertEqual(extractor.extract_pc_from_caller_context("caller", "callee"), ["TRUE"])

    def test_treats_keyword_callee_as_not_found(self):
        src = (
            "int caller(void) {\n"
            "  if (1) {\n"
            "    return 1;\n"
            "  }\n"
            "  return 0;\n"
            "}\n"
        )
        extractor = PresenceConditionExtractor(src)
        self.assertEqual(extractor.extract_pc_from_caller_context("caller", "if"), ["CALL_NOT_FOUND"])

    def test_finds_caller_with_multiline_signature_and_macro_attribute(self):
        src = (
            "#define ATTR(x)\n"
            "void callee(void) {}\n"
            "static int\n"
            "caller(\n"
            "    int a,\n"
            "    int b\n"
            ") ATTR((unused))\n"
            "{\n"
            "  callee();\n"
            "  return a + b;\n"
            "}\n"
        )
        extractor = PresenceConditionExtractor(src)
        self.assertEqual(extractor.extract_pc_from_caller_context("caller", "callee"), ["TRUE"])

    def test_function_bounds_ignore_braces_in_comments_and_strings(self):
        src = (
            "void callee(void) {}\n"
            "int caller(void) {\n"
            "  /* fake brace: { */\n"
            "  const char *s = \"not a real } brace\";\n"
            "  callee();\n"
            "  return 0;\n"
            "}\n"
            "int other(void) { return 1; }\n"
        )
        extractor = PresenceConditionExtractor(src)
        self.assertEqual(extractor.extract_pc_from_caller_context("caller", "callee"), ["TRUE"])
        self.assertEqual(extractor.extract_pc_from_caller_context("other", "callee"), ["CALL_NOT_FOUND"])


if __name__ == "__main__":
    unittest.main()
