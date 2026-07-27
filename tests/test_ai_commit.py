"""Tests for ai_commit. Standard library only — run with:

    python -m unittest discover -s tests
"""

import os
import sys
import unittest

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

import ai_commit  # noqa: E402


class TestIsDoc(unittest.TestCase):
    def test_documentation_extensions(self):
        for path in (
            "README.md",
            "docs/guide.mdx",
            "notes.rst",
            "NOTES.txt",
            "manual.adoc",
        ):
            with self.subTest(path=path):
                self.assertTrue(ai_commit._is_doc(path))

    def test_known_doc_basenames_without_extension(self):
        for path in ("LICENSE", "CHANGELOG", "CONTRIBUTING", "CODEOWNERS"):
            with self.subTest(path=path):
                self.assertTrue(ai_commit._is_doc(path))

    def test_anything_under_a_docs_directory(self):
        self.assertTrue(ai_commit._is_doc("docs/api/schema.json"))
        self.assertTrue(ai_commit._is_doc("website/docs/intro.html"))

    def test_windows_separators_are_normalised(self):
        self.assertTrue(ai_commit._is_doc(r"docs\api\schema.json"))
        self.assertTrue(ai_commit._is_doc(r"src\README.md"))

    def test_case_insensitive(self):
        self.assertTrue(ai_commit._is_doc("ReadMe.MD"))
        self.assertTrue(ai_commit._is_doc("Docs/Intro.md"))

    def test_code_is_not_documentation(self):
        for path in ("ai_commit.py", "src/main.go", "run-commit.cmd", "Makefile"):
            with self.subTest(path=path):
                self.assertFalse(ai_commit._is_doc(path))

    def test_docs_in_a_filename_is_not_a_docs_directory(self):
        self.assertFalse(ai_commit._is_doc("src/docs_loader.py"))


class TestIsDocOnly(unittest.TestCase):
    def test_all_docs(self):
        self.assertTrue(ai_commit.is_doc_only(["README.md", "CHANGELOG.md"]))

    def test_mixed_code_and_docs_is_not_doc_only(self):
        self.assertFalse(ai_commit.is_doc_only(["README.md", "ai_commit.py"]))

    def test_empty_list_is_not_doc_only(self):
        self.assertFalse(ai_commit.is_doc_only([]))


class TestTruncate(unittest.TestCase):
    def test_short_diff_is_untouched(self):
        diff = "diff --git a/x b/x\n+hello\n"
        self.assertEqual(ai_commit.truncate(diff, 1000), diff)

    def test_diff_at_the_limit_is_untouched(self):
        diff = "x" * 10
        self.assertEqual(ai_commit.truncate(diff, 10), diff)

    def test_long_diff_is_cut_and_marked(self):
        result = ai_commit.truncate("x" * 100, 10)
        self.assertTrue(result.startswith("x" * 10))
        self.assertNotIn("x" * 11, result)
        self.assertIn("truncated", result)


class TestSystemPrompt(unittest.TestCase):
    def test_body_only_prompt_forbids_a_title(self):
        prompt = ai_commit._system_prompt(body_only=True)
        self.assertIn("ONLY the body", prompt)
        self.assertIn("No title line", prompt)

    def test_full_prompt_asks_for_title_and_bullets(self):
        prompt = ai_commit._system_prompt(body_only=False)
        self.assertIn("<title>", prompt)
        self.assertIn("<bullet>", prompt)

    def test_both_prompts_carry_the_shared_rules(self):
        for body_only in (True, False):
            with self.subTest(body_only=body_only):
                prompt = ai_commit._system_prompt(body_only=body_only)
                self.assertIn("imperative", prompt)
                self.assertIn("Conventional Commits", prompt)
                self.assertIn("docs:", prompt)


if __name__ == "__main__":
    unittest.main()
