"""Tests for commitclerk. Standard library only — run with:

    python -m unittest discover -s tests
"""

import os
import sys
import unittest

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

import commitclerk  # noqa: E402


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
                self.assertTrue(commitclerk._is_doc(path))

    def test_known_doc_basenames_without_extension(self):
        for path in ("LICENSE", "CHANGELOG", "CONTRIBUTING", "CODEOWNERS"):
            with self.subTest(path=path):
                self.assertTrue(commitclerk._is_doc(path))

    def test_anything_under_a_docs_directory(self):
        self.assertTrue(commitclerk._is_doc("docs/api/schema.json"))
        self.assertTrue(commitclerk._is_doc("website/docs/intro.html"))

    def test_windows_separators_are_normalised(self):
        self.assertTrue(commitclerk._is_doc(r"docs\api\schema.json"))
        self.assertTrue(commitclerk._is_doc(r"src\README.md"))

    def test_case_insensitive(self):
        self.assertTrue(commitclerk._is_doc("ReadMe.MD"))
        self.assertTrue(commitclerk._is_doc("Docs/Intro.md"))

    def test_code_is_not_documentation(self):
        for path in ("commitclerk.py", "src/main.go", "run-commit.cmd", "Makefile"):
            with self.subTest(path=path):
                self.assertFalse(commitclerk._is_doc(path))

    def test_docs_in_a_filename_is_not_a_docs_directory(self):
        self.assertFalse(commitclerk._is_doc("src/docs_loader.py"))


class TestIsDocOnly(unittest.TestCase):
    def test_all_docs(self):
        self.assertTrue(commitclerk.is_doc_only(["README.md", "CHANGELOG.md"]))

    def test_mixed_code_and_docs_is_not_doc_only(self):
        self.assertFalse(commitclerk.is_doc_only(["README.md", "commitclerk.py"]))

    def test_empty_list_is_not_doc_only(self):
        self.assertFalse(commitclerk.is_doc_only([]))


class TestTruncate(unittest.TestCase):
    def test_short_diff_is_untouched(self):
        diff = "diff --git a/x b/x\n+hello\n"
        self.assertEqual(commitclerk.truncate(diff, 1000), diff)

    def test_diff_at_the_limit_is_untouched(self):
        diff = "x" * 10
        self.assertEqual(commitclerk.truncate(diff, 10), diff)

    def test_long_diff_is_cut_and_marked(self):
        result = commitclerk.truncate("x" * 100, 10)
        self.assertTrue(result.startswith("x" * 10))
        self.assertNotIn("x" * 11, result)
        self.assertIn("truncated", result)


_HEAD_CUT_NOTE = "\n\n[...diff truncated for context length...]"


def _file_chunk(name: str, body_lines: int) -> str:
    """A minimal but realistically shaped single-file diff chunk."""
    return (
        f"diff --git a/{name} b/{name}\n"
        f"index 1111111..2222222 100644\n"
        f"--- a/{name}\n"
        f"+++ b/{name}\n"
        f"@@ -1,{body_lines} +1,{body_lines} @@\n"
        + "".join(f"+line {i} in {name}\n" for i in range(body_lines))
    )


class TestSplitDiff(unittest.TestCase):
    def test_splits_on_file_boundaries(self):
        diff = _file_chunk("a.py", 2) + _file_chunk("b.py", 3)
        chunks = commitclerk.split_diff(diff)
        self.assertEqual(len(chunks), 2)
        self.assertTrue(chunks[0].startswith("diff --git a/a.py"))
        self.assertTrue(chunks[1].startswith("diff --git a/b.py"))
        self.assertEqual("".join(chunks), diff)

    def test_empty_diff_yields_no_chunks(self):
        self.assertEqual(commitclerk.split_diff(""), [])

    def test_added_line_that_looks_like_a_header_does_not_split(self):
        # A diff of this very project can contain "+diff --git ..." as content.
        diff = "diff --git a/a.md b/a.md\n@@ -1 +1 @@\n+diff --git a/fake b/fake\n"
        self.assertEqual(len(commitclerk.split_diff(diff)), 1)


class TestBudgetDiff(unittest.TestCase):
    def test_diff_within_budget_is_untouched(self):
        diff = _file_chunk("a.py", 2)
        self.assertEqual(commitclerk.budget_diff(diff, 10_000), diff)

    def test_every_file_survives_an_oversized_diff(self):
        # Head-truncation would drop z.py entirely: it sorts last and the first
        # file alone blows the budget.
        diff = _file_chunk("a.py", 500) + _file_chunk("m.py", 500) + _file_chunk("z.py", 500)
        result = commitclerk.budget_diff(diff, 2_000)
        for name in ("a.py", "m.py", "z.py"):
            with self.subTest(name=name):
                self.assertIn(f"diff --git a/{name} b/{name}", result)
                self.assertIn(f"line 0 in {name}", result)

    def test_result_respects_the_limit_and_marks_what_it_dropped(self):
        diff = _file_chunk("a.py", 500) + _file_chunk("z.py", 500)
        result = commitclerk.budget_diff(diff, 2_000)
        self.assertLessEqual(len(result), 2_000)
        self.assertIn("lines truncated ...]", result)

    def test_a_small_file_is_kept_whole_next_to_a_huge_one(self):
        diff = _file_chunk("huge.py", 2_000) + _file_chunk("tiny.py", 2)
        result = commitclerk.budget_diff(diff, 3_000)
        self.assertIn("line 0 in tiny.py", result)
        self.assertIn("line 1 in tiny.py", result)

    def test_single_file_falls_back_to_head_truncation(self):
        result = commitclerk.budget_diff(_file_chunk("a.py", 500), 400)
        self.assertLessEqual(len(result), 400 + len(_HEAD_CUT_NOTE))
        self.assertIn("truncated", result)

    def test_headers_alone_over_budget_still_respects_the_limit(self):
        diff = "".join(_file_chunk(f"f{i}.py", 5) for i in range(200))
        result = commitclerk.budget_diff(diff, 500)
        self.assertLessEqual(len(result), 500 + len(_HEAD_CUT_NOTE))


class TestProgName(unittest.TestCase):
    def test_git_subcommand_is_shown_as_git_clerk(self):
        self.assertEqual(commitclerk.prog_name("/usr/local/bin/git-clerk"), "git clerk")
        self.assertEqual(commitclerk.prog_name(r"C:\Python\Scripts\git-clerk.exe"), "git clerk")

    def test_console_scripts_keep_their_own_name(self):
        self.assertEqual(commitclerk.prog_name("/usr/local/bin/clerk"), "clerk")
        self.assertEqual(commitclerk.prog_name(r"C:\Python\Scripts\commitclerk.exe"), "commitclerk")

    def test_direct_invocation_and_empty_argv(self):
        self.assertEqual(commitclerk.prog_name("commitclerk.py"), "commitclerk")
        self.assertEqual(commitclerk.prog_name(""), "clerk")


class TestSystemPrompt(unittest.TestCase):
    def test_body_only_prompt_forbids_a_title(self):
        prompt = commitclerk._system_prompt(body_only=True)
        self.assertIn("ONLY the body", prompt)
        self.assertIn("No title line", prompt)

    def test_full_prompt_asks_for_title_and_bullets(self):
        prompt = commitclerk._system_prompt(body_only=False)
        self.assertIn("<title>", prompt)
        self.assertIn("<bullet>", prompt)

    def test_both_prompts_carry_the_shared_rules(self):
        for body_only in (True, False):
            with self.subTest(body_only=body_only):
                prompt = commitclerk._system_prompt(body_only=body_only)
                self.assertIn("imperative", prompt)
                self.assertIn("Conventional Commits", prompt)
                self.assertIn("docs:", prompt)


if __name__ == "__main__":
    unittest.main()
