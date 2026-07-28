"""Tests for commitclerk. Standard library only — run with:

    python -m unittest discover -s tests
"""

from __future__ import annotations  # `str | None` in a signature, on Python 3.8

import email.message
import io
import json
import os
import pathlib
import shutil
import subprocess
import sys
import tempfile
import unittest
import urllib.error
from unittest import mock

_ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
# Point $COMMITCLERK_SOURCE at `dist` to run this same suite against the built
# single-file artifact instead of the package. CI does exactly that, which is what
# makes the concatenation trustworthy rather than merely syntactically valid.
sys.path.insert(0, os.path.join(_ROOT, os.environ.get("COMMITCLERK_SOURCE", "")))

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


class TestDocGuardNote(unittest.TestCase):
    """The three states of the documentation guard."""

    def test_no_documentation_means_no_note(self):
        self.assertEqual(commitclerk.doc_guard_note(["app.py", "tests/t.py"]), "")

    def test_documentation_only_keeps_the_strong_note(self):
        note = commitclerk.doc_guard_note(["README.md", "CHANGELOG.md"])
        self.assertIn("every file in this commit is documentation", note)
        self.assertIn("docs:", note)

    def test_a_mixed_commit_now_gets_a_note_at_all(self):
        # The bug this task fixes: one code file used to switch the guard off.
        note = commitclerk.doc_guard_note(["CHANGELOG.md", "app.py"])
        self.assertNotEqual(note, "")
        self.assertIn("changes documentation", note)

    def test_the_mixed_note_names_only_the_documentation_files(self):
        note = commitclerk.doc_guard_note(["CHANGELOG.md", "app.py", "docs/guide.md"])
        self.assertIn("CHANGELOG.md", note)
        self.assertIn("docs/guide.md", note)
        self.assertNotIn("app.py", note)

    def test_the_mixed_note_ties_the_claim_to_the_code(self):
        note = commitclerk.doc_guard_note(["CHANGELOG.md", "app.py"])
        # It must not forbid `feat:` outright — sometimes the code really does
        # implement what the changelog describes.
        self.assertIn("use feat: if they add behaviour", note)
        self.assertIn("ONLY from the non-documentation diff lines", note)

    def test_a_documentation_heavy_commit_says_so(self):
        # 900 lines of changelog, one line of code: the README's own example.
        diff = _file_chunk("CHANGELOG.md", 900) + _file_chunk("app.py", 1)
        note = commitclerk.doc_guard_note(["CHANGELOG.md", "app.py"], diff)
        self.assertIn("99% of the changed lines", note)
        self.assertIn("mostly a documentation edit", note)

    def test_a_code_heavy_commit_does_not_claim_to_be_documentation(self):
        diff = _file_chunk("README.md", 2) + _file_chunk("app.py", 400)
        note = commitclerk.doc_guard_note(["README.md", "app.py"], diff)
        self.assertIn("changes documentation", note)
        self.assertNotIn("mostly a documentation edit", note)

    def test_without_a_diff_the_proportion_is_simply_omitted(self):
        note = commitclerk.doc_guard_note(["README.md", "app.py"])
        self.assertNotIn("% of the changed lines", note)


class TestDocLineShare(unittest.TestCase):
    def test_documentation_share_of_changed_lines(self):
        diff = _file_chunk("README.md", 3) + _file_chunk("app.py", 1)
        self.assertAlmostEqual(commitclerk.doc_line_share(diff), 0.75)

    def test_all_code(self):
        self.assertEqual(commitclerk.doc_line_share(_file_chunk("app.py", 5)), 0.0)

    def test_an_empty_diff_has_no_share(self):
        self.assertIsNone(commitclerk.doc_line_share(""))


class TestClassify(unittest.TestCase):
    def _check(self, cases):
        for path, expected in cases:
            with self.subTest(path=path):
                self.assertEqual(commitclerk.classify(path), expected)

    def test_code_is_the_default(self):
        self._check([
            ("commitclerk.py", "code"),
            ("src/main.go", "code"),
            ("app/models/user.rb", "code"),
        ])

    def test_documentation(self):
        self._check([("README.md", "docs"), ("docs/api/schema.json", "docs")])

    def test_tests(self):
        self._check([
            ("tests/test_commitclerk.py", "test"),
            ("src/user_test.go", "test"),
            ("web/app.spec.ts", "test"),
            ("__tests__/render.js", "test"),
            ("test_helper.py", "test"),
        ])

    def test_generated_files_are_not_code(self):
        self._check([
            ("package-lock.json", "generated"),
            ("poetry.lock", "generated"),
            ("go.sum", "generated"),
            ("dist/bundle.js", "generated"),
            ("api/service_pb2.py", "generated"),
            ("locale/pt_BR.po", "generated"),
            ("src/__snapshots__/App.test.js.snap", "generated"),
        ])

    def test_config_and_build_files(self):
        self._check([
            (".github/workflows/ci.yml", "config"),
            ("pyproject.toml", "config"),
            ("Makefile", "config"),
            ("Dockerfile", "config"),
            (".gitignore", "config"),
            ("tsconfig.json", "config"),
        ])

    def test_vendored_code_is_never_the_subject(self):
        self._check([
            ("vendor/github.com/pkg/errors/errors.go", "vendor"),
            ("node_modules/left-pad/index.js", "vendor"),
            ("third_party/zlib/zlib.c", "vendor"),
        ])

    def test_vendor_beats_every_other_signal(self):
        # A lockfile or a test inside vendor/ is still just vendored noise.
        self.assertEqual(commitclerk.classify("vendor/pkg/package-lock.json"), "vendor")
        self.assertEqual(commitclerk.classify("node_modules/x/test/index_test.js"), "vendor")

    def test_binary_needs_the_diff_to_say_so(self):
        self.assertEqual(commitclerk.classify("docs/logo.png"), "docs")  # under docs/
        self.assertEqual(commitclerk.classify("assets/logo.png"), "code")
        self.assertEqual(
            commitclerk.classify("assets/logo.png", {"assets/logo.png"}), "binary"
        )

    def test_windows_separators_are_normalised(self):
        self.assertEqual(commitclerk.classify(r"tests\test_x.py"), "test")
        self.assertEqual(commitclerk.classify(r"vendor\pkg\x.go"), "vendor")

    def test_a_segment_match_is_not_a_substring_match(self):
        # "spec/" is a test directory; "specs_loader.py" is not.
        self.assertEqual(commitclerk.classify("src/specs_loader.py"), "code")
        self.assertEqual(commitclerk.classify("src/distance.py"), "code")
        self.assertEqual(commitclerk.classify("src/buildings.py"), "code")


class TestBinaryPaths(unittest.TestCase):
    def test_reads_the_binary_marker(self):
        diff = (
            "diff --git a/a.py b/a.py\n@@ -1 +1 @@\n-x\n+y\n"
            "diff --git a/pic.png b/pic.png\nindex 1..2 100644\n"
            "Binary files a/pic.png and b/pic.png differ\n"
        )
        self.assertEqual(commitclerk.binary_paths(diff), {"pic.png"})

    def test_reads_a_binary_patch(self):
        diff = "diff --git a/f.bin b/f.bin\nindex 1..2 100644\nGIT binary patch\nzzz\n"
        self.assertEqual(commitclerk.binary_paths(diff), {"f.bin"})

    def test_a_text_only_diff_has_none(self):
        self.assertEqual(commitclerk.binary_paths(_file_chunk("a.py", 3)), set())


class TestClassMix(unittest.TestCase):
    def test_counts_are_ordered_by_significance(self):
        classes = {
            "a.py": "code", "b.py": "code",
            "tests/t.py": "test", "package-lock.json": "generated",
        }
        self.assertEqual(commitclerk.class_mix(classes), "generated 1, test 1, code 2")

    def test_absent_classes_are_omitted(self):
        self.assertEqual(commitclerk.class_mix({"README.md": "docs"}), "docs 1")

    def test_no_files_no_mix(self):
        self.assertEqual(commitclerk.class_mix({}), "")


class TestClassifyFiles(unittest.TestCase):
    def test_maps_every_file_and_keeps_order(self):
        files = ["commitclerk.py", "README.md", "tests/test_x.py"]
        self.assertEqual(
            list(commitclerk.classify_files(files)),
            files,
        )

    def test_the_diff_supplies_the_binary_class(self):
        diff = "diff --git a/pic.png b/pic.png\nBinary files a/pic.png and b/pic.png differ\n"
        classes = commitclerk.classify_files(["pic.png", "app.py"], diff)
        self.assertEqual(classes, {"pic.png": "binary", "app.py": "code"})


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


class TestPartiallyStaged(unittest.TestCase):
    def test_finds_files_that_are_staged_and_also_dirty(self):
        staged = ["app.py", "README.md", "tests/t.py"]
        unstaged = ["app.py", "notes.txt"]
        self.assertEqual(commitclerk.partially_staged(staged, unstaged), ["app.py"])

    def test_a_clean_working_tree_has_none(self):
        self.assertEqual(commitclerk.partially_staged(["app.py"], []), [])

    def test_unstaged_files_that_are_not_staged_are_not_reported(self):
        # Untouched-by-this-commit files are none of our business.
        self.assertEqual(commitclerk.partially_staged(["app.py"], ["other.py"]), [])

    def test_staged_order_is_preserved(self):
        staged = ["z.py", "a.py"]
        self.assertEqual(commitclerk.partially_staged(staged, ["a.py", "z.py"]), staged)


class TestUnstagedWarning(unittest.TestCase):
    def test_nothing_to_warn_about(self):
        self.assertEqual(commitclerk.unstaged_warning([]), "")

    def test_names_the_files_and_explains_the_consequence(self):
        note = commitclerk.unstaged_warning(["app.py"])
        self.assertIn("app.py", note)
        self.assertIn("staged version", note)
        self.assertIn("1 staged file has", note)

    def test_plural_reads_correctly(self):
        self.assertIn("2 staged files have", commitclerk.unstaged_warning(["a.py", "b.py"]))

    def test_a_long_list_is_truncated(self):
        note = commitclerk.unstaged_warning([f"f{i}.py" for i in range(9)], limit=3)
        self.assertIn("f0.py, f1.py, f2.py, and 6 more", note)
        self.assertNotIn("f8.py", note)

    def test_the_warning_is_ascii(self):
        # It goes to a terminal whose encoding we do not control.
        self.assertTrue(commitclerk.unstaged_warning(["a.py", "b.py"]).isascii())


class TestChunkPath(unittest.TestCase):
    def test_reads_the_b_side(self):
        self.assertEqual(commitclerk.chunk_path(_file_chunk("src/app.py", 1)), "src/app.py")

    def test_a_rename_reports_its_new_name(self):
        chunk = "diff --git a/old.py b/new.py\nsimilarity index 98%\nrename from old.py\n"
        self.assertEqual(commitclerk.chunk_path(chunk), "new.py")

    def test_a_chunk_without_a_header_has_no_path(self):
        self.assertIsNone(commitclerk.chunk_path("@@ -1 +1 @@\n+x\n"))


class TestCountChanges(unittest.TestCase):
    def test_counts_added_and_removed_lines(self):
        chunk = "@@ -1,2 +1,3 @@\n-old\n+new\n+extra\n context\n"
        self.assertEqual(commitclerk.count_changes(chunk), (2, 1))

    def test_file_headers_are_not_counted_as_changes(self):
        self.assertEqual(commitclerk.count_changes("--- a/x\n+++ b/x\n"), (0, 0))


class TestDemoteDiff(unittest.TestCase):
    def test_a_large_generated_body_is_replaced_by_one_line(self):
        classes = {"package-lock.json": "generated"}
        diff = _file_chunk("package-lock.json", 400)
        result = commitclerk.demote_diff(diff, classes)
        self.assertIn("diff --git a/package-lock.json", result)  # header survives
        self.assertIn("generated file, +400 -0, contents not shown", result)
        self.assertNotIn("line 5 in package-lock.json", result)
        self.assertLess(len(result), len(diff) / 10)

    def test_code_is_never_demoted(self):
        diff = _file_chunk("app.py", 400)
        classes = {"app.py": "code"}
        self.assertEqual(commitclerk.demote_diff(diff, classes), diff)

    def test_vendored_code_is_demoted_too(self):
        diff = _file_chunk("vendor/pkg/x.go", 400)
        classes = {"vendor/pkg/x.go": "vendor"}
        self.assertIn("vendor file,", commitclerk.demote_diff(diff, classes))

    def test_a_small_generated_change_is_left_alone(self):
        # A two-line lockfile bump is cheaper to send than to explain.
        diff = _file_chunk("go.sum", 2)
        classes = {"go.sum": "generated"}
        self.assertEqual(commitclerk.demote_diff(diff, classes), diff)

    def test_a_commit_of_nothing_but_generated_files_still_names_them(self):
        diff = _file_chunk("package-lock.json", 400) + _file_chunk("yarn.lock", 400)
        classes = {"package-lock.json": "generated", "yarn.lock": "generated"}
        result = commitclerk.demote_diff(diff, classes)
        self.assertIn("package-lock.json", result)
        self.assertIn("yarn.lock", result)

    def test_without_classes_nothing_changes(self):
        diff = _file_chunk("package-lock.json", 400)
        self.assertEqual(commitclerk.demote_diff(diff, {}), diff)

    def test_the_reclaimed_budget_goes_to_the_files_that_matter(self):
        # The payoff: at a budget where the lockfile used to crowd out the fix,
        # the code file now arrives whole.
        diff = _file_chunk("package-lock.json", 2_000) + _file_chunk("app.py", 120)
        classes = {"package-lock.json": "generated", "app.py": "code"}
        budget = 4_000

        without = commitclerk.budget_diff(diff, budget)
        with_demotion = commitclerk.budget_diff(commitclerk.demote_diff(diff, classes), budget)

        self.assertNotIn("line 119 in app.py", without)
        self.assertIn("line 119 in app.py", with_demotion)
        self.assertLessEqual(len(with_demotion), budget)


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


class TestProviderTable(unittest.TestCase):
    _SLOTS = ("label", "default_base", "path", "default_model", "headers", "payload", "extract")

    def test_openai_reads_the_conventional_base_url_variable(self):
        self.assertEqual(commitclerk.PROVIDERS["openai"]["base_env"], "OPENAI_BASE_URL")

    def test_every_provider_fills_every_slot(self):
        for name, spec in commitclerk.PROVIDERS.items():
            for slot in self._SLOTS:
                with self.subTest(provider=name, slot=slot):
                    self.assertIn(slot, spec)

    def test_the_four_adapter_slots_are_callable(self):
        for name, spec in commitclerk.PROVIDERS.items():
            for slot in ("headers", "payload", "extract"):
                with self.subTest(provider=name, slot=slot):
                    self.assertTrue(callable(spec[slot]))

    def test_default_provider_is_registered(self):
        self.assertIn(commitclerk.DEFAULT_PROVIDER, commitclerk.PROVIDERS)

    def test_resolve_known_and_unknown(self):
        self.assertIs(
            commitclerk.resolve_provider("openai"), commitclerk.PROVIDERS["openai"]
        )
        # $CLERK_PROVIDER bypasses argparse's `choices`, so this must not raise.
        self.assertIsNone(commitclerk.resolve_provider("nope"))

    def test_url_joins_base_and_path_without_doubling_the_slash(self):
        spec = {"default_base": "http://localhost:11434/v1/", "path": "/chat/completions"}
        self.assertEqual(
            commitclerk.provider_url(spec), "http://localhost:11434/v1/chat/completions"
        )

    def test_openai_url_is_unchanged(self):
        self.assertEqual(
            commitclerk.provider_url(commitclerk.PROVIDERS["openai"]),
            "https://api.openai.com/v1/chat/completions",
        )

    def test_an_explicit_base_replaces_the_provider_default(self):
        self.assertEqual(
            commitclerk.provider_url(commitclerk.PROVIDERS["openai"], "https://api.groq.com/openai/v1"),
            "https://api.groq.com/openai/v1/chat/completions",
        )


class TestResolveBase(unittest.TestCase):
    def setUp(self):
        self.spec = commitclerk.PROVIDERS["openai"]

    def test_cli_flag_wins_over_environment(self):
        with mock.patch.dict(os.environ, {"OPENAI_BASE_URL": "http://from-env/v1"}):
            self.assertEqual(
                commitclerk.resolve_base(self.spec, "http://from-cli/v1"), "http://from-cli/v1"
            )

    def test_environment_wins_over_provider_default(self):
        with mock.patch.dict(os.environ, {"OPENAI_BASE_URL": "http://from-env/v1"}):
            self.assertEqual(commitclerk.resolve_base(self.spec), "http://from-env/v1")

    def test_falls_back_to_the_provider_default(self):
        with mock.patch.dict(os.environ, {}, clear=True):
            self.assertEqual(commitclerk.resolve_base(self.spec), "https://api.openai.com/v1")

    def test_provider_without_a_base_env_uses_its_default(self):
        self.assertEqual(
            commitclerk.resolve_base({"default_base": "http://localhost:1234/v1"}),
            "http://localhost:1234/v1",
        )


class TestBaseUrlValidation(unittest.TestCase):
    def test_http_and_https_are_accepted(self):
        for base in ("http://localhost:11434/v1", "https://api.openai.com/v1", "HTTPS://X/v1"):
            with self.subTest(base=base):
                self.assertIsNone(commitclerk.base_url_error(base))

    def test_a_missing_scheme_is_reported_not_crashed_on(self):
        # urllib would otherwise fail with "unknown url type", which reads like
        # a bug in the tool rather than a typo in the flag.
        self.assertIn("http://", commitclerk.base_url_error("localhost:11434/v1"))

    def test_a_non_http_scheme_is_rejected(self):
        self.assertIsNotNone(commitclerk.base_url_error("file:///etc/passwd"))
        self.assertIsNotNone(commitclerk.base_url_error("ftp://example.com/v1"))

    def test_a_scheme_with_no_host_is_rejected(self):
        self.assertIn("no host", commitclerk.base_url_error("http://"))
        self.assertIn("no host", commitclerk.base_url_error("https:///"))


class TestResolveModel(unittest.TestCase):
    def setUp(self):
        self.spec = commitclerk.PROVIDERS["openai"]

    def test_cli_flag_wins_over_environment(self):
        with mock.patch.dict(os.environ, {"OPENAI_MODEL": "from-env"}):
            self.assertEqual(commitclerk.resolve_model(self.spec, "from-cli"), "from-cli")

    def test_environment_wins_over_provider_default(self):
        with mock.patch.dict(os.environ, {"OPENAI_MODEL": "from-env"}):
            self.assertEqual(commitclerk.resolve_model(self.spec), "from-env")

    def test_falls_back_to_the_provider_default(self):
        with mock.patch.dict(os.environ, {}, clear=True):
            self.assertEqual(commitclerk.resolve_model(self.spec), commitclerk.DEFAULT_MODEL)

    def test_provider_without_a_model_env_uses_its_default(self):
        spec = {"default_model": "local-model"}
        self.assertEqual(commitclerk.resolve_model(spec), "local-model")


class TestApiKeyResolution(unittest.TestCase):
    def test_missing_required_key_names_the_variable(self):
        with mock.patch.dict(os.environ, {}, clear=True):
            spec = commitclerk.PROVIDERS["openai"]
            self.assertEqual(commitclerk.missing_key_env(spec), "OPENAI_API_KEY")
            self.assertIsNone(commitclerk.api_key_for(spec))

    def test_present_key_is_read_from_the_provider_variable(self):
        with mock.patch.dict(os.environ, {"OPENAI_API_KEY": "sk-test"}):
            spec = commitclerk.PROVIDERS["openai"]
            self.assertIsNone(commitclerk.missing_key_env(spec))
            self.assertEqual(commitclerk.api_key_for(spec), "sk-test")

    def test_keyless_provider_is_never_blocked(self):
        # A local model has no key at all; the guard must not fire for it.
        with mock.patch.dict(os.environ, {}, clear=True):
            self.assertIsNone(commitclerk.missing_key_env({"default_model": "x"}))
            self.assertIsNone(commitclerk.missing_key_env({"key_env": "K", "key_required": False}))


class TestOpenAIAdapter(unittest.TestCase):
    def test_payload_shape(self):
        payload = commitclerk._openai_payload("gpt-4o-mini", "SYSTEM", "USER")
        self.assertEqual(payload["model"], "gpt-4o-mini")
        self.assertEqual(
            [m["role"] for m in payload["messages"]], ["system", "user"]
        )
        self.assertEqual(payload["messages"][0]["content"], "SYSTEM")
        self.assertEqual(payload["messages"][1]["content"], "USER")
        self.assertEqual(payload["temperature"], 0.2)

    def test_extract_reads_the_first_choice(self):
        data = {"choices": [{"message": {"content": "feat: do a thing"}}]}
        self.assertEqual(commitclerk._openai_extract(data), "feat: do a thing")

    def test_headers_use_bearer_authorization(self):
        headers = commitclerk.PROVIDERS["openai"]["headers"]("sk-test")
        self.assertEqual(headers["Authorization"], "Bearer sk-test")


class TestAnthropicAdapter(unittest.TestCase):
    def setUp(self):
        self.spec = commitclerk.PROVIDERS["anthropic"]

    def test_url_is_the_messages_endpoint(self):
        self.assertEqual(
            commitclerk.provider_url(self.spec), "https://api.anthropic.com/v1/messages"
        )

    def test_headers_use_x_api_key_and_a_pinned_version(self):
        headers = self.spec["headers"]("sk-ant-test")
        self.assertEqual(headers["x-api-key"], "sk-ant-test")
        self.assertEqual(headers["anthropic-version"], commitclerk.ANTHROPIC_VERSION)
        self.assertNotIn("Authorization", headers)

    def test_system_prompt_is_a_top_level_field(self):
        payload = commitclerk._anthropic_payload("claude-haiku-4-5", "SYSTEM", "USER")
        self.assertEqual(payload["system"], "SYSTEM")
        self.assertEqual([m["role"] for m in payload["messages"]], ["user"])
        self.assertEqual(payload["messages"][0]["content"], "USER")

    def test_max_tokens_is_always_sent(self):
        # Unlike Chat Completions, the Messages API rejects a request without it.
        payload = commitclerk._anthropic_payload("claude-haiku-4-5", "s", "u")
        self.assertEqual(payload["max_tokens"], commitclerk.ANTHROPIC_MAX_TOKENS)

    def test_no_temperature_is_sent(self):
        # Current reasoning models return 400 when temperature is present.
        self.assertNotIn("temperature", commitclerk._anthropic_payload("m", "s", "u"))

    def test_extract_reads_a_text_block(self):
        data = {"content": [{"type": "text", "text": "fix: do a thing"}]}
        self.assertEqual(commitclerk._anthropic_extract(data), "fix: do a thing")

    def test_extract_skips_leading_thinking_blocks(self):
        # content[0] is not necessarily the answer on a reasoning model.
        data = {
            "content": [
                {"type": "thinking", "thinking": "hmm"},
                {"type": "text", "text": "fix: do a thing"},
            ]
        }
        self.assertEqual(commitclerk._anthropic_extract(data), "fix: do a thing")

    def test_extract_of_a_textless_response_is_empty_not_an_exception(self):
        self.assertEqual(commitclerk._anthropic_extract({"content": []}), "")
        self.assertEqual(commitclerk._anthropic_extract({}), "")

    def test_reads_its_own_environment_variables(self):
        with mock.patch.dict(
            os.environ, {"ANTHROPIC_MODEL": "claude-opus-5", "OPENAI_MODEL": "gpt-4o"}
        ):
            self.assertEqual(commitclerk.resolve_model(self.spec), "claude-opus-5")
        with mock.patch.dict(os.environ, {}, clear=True):
            self.assertEqual(commitclerk.missing_key_env(self.spec), "ANTHROPIC_API_KEY")


class TestOllamaPreset(unittest.TestCase):
    def setUp(self):
        self.spec = commitclerk.PROVIDERS["ollama"]

    def test_needs_no_api_key_at_all(self):
        # The whole point of the preset: it must work with nothing configured.
        with mock.patch.dict(os.environ, {}, clear=True):
            self.assertIsNone(commitclerk.missing_key_env(self.spec))
            self.assertIsNone(commitclerk.api_key_for(self.spec))

    def test_sends_no_authorization_header(self):
        self.assertEqual(self.spec["headers"](None), {})

    def test_defaults_to_the_local_server(self):
        with mock.patch.dict(os.environ, {}, clear=True):
            self.assertEqual(
                commitclerk.provider_url(self.spec, commitclerk.resolve_base(self.spec)),
                "http://localhost:11434/v1/chat/completions",
            )

    def test_reuses_the_openai_wire_format(self):
        self.assertIs(self.spec["payload"], commitclerk._openai_payload)
        self.assertIs(self.spec["extract"], commitclerk._openai_extract)

    def test_has_its_own_model_and_base_url_variables(self):
        with mock.patch.dict(
            os.environ, {"OLLAMA_MODEL": "codellama", "OLLAMA_BASE_URL": "http://box:11434/v1"}
        ):
            self.assertEqual(commitclerk.resolve_model(self.spec), "codellama")
            self.assertEqual(commitclerk.resolve_base(self.spec), "http://box:11434/v1")

    def test_a_local_base_url_passes_validation(self):
        self.assertIsNone(commitclerk.base_url_error(self.spec["default_base"]))


class TestRetryDelay(unittest.TestCase):
    def test_backoff_grows_and_is_jittered(self):
        with mock.patch.object(commitclerk.random, "random", return_value=1.0):
            self.assertAlmostEqual(commitclerk.retry_delay(1), 1.0)
            self.assertAlmostEqual(commitclerk.retry_delay(2), 2.0)
            self.assertAlmostEqual(commitclerk.retry_delay(3), 4.0)
        with mock.patch.object(commitclerk.random, "random", return_value=0.0):
            # Jitter never drops below half the backoff, so a retry still waits.
            self.assertAlmostEqual(commitclerk.retry_delay(2), 1.0)

    def test_backoff_is_capped(self):
        with mock.patch.object(commitclerk.random, "random", return_value=1.0):
            self.assertLessEqual(commitclerk.retry_delay(20), commitclerk.RETRY_MAX_DELAY)

    def test_retry_after_header_wins(self):
        self.assertEqual(commitclerk.retry_delay(1, "7"), 7.0)
        self.assertEqual(commitclerk.retry_delay(1, " 2.5 "), 2.5)

    def test_retry_after_is_capped_too(self):
        self.assertEqual(commitclerk.retry_delay(1, "99999"), commitclerk.RETRY_MAX_DELAY)

    def test_a_date_or_garbage_retry_after_falls_back_to_backoff(self):
        for value in (None, "", "Wed, 21 Oct 2026 07:28:00 GMT", "soon", "-5"):
            with self.subTest(value=value):
                self.assertIsNone(commitclerk.retry_after_seconds(value))
                with mock.patch.object(commitclerk.random, "random", return_value=1.0):
                    self.assertAlmostEqual(commitclerk.retry_delay(1, value), 1.0)


class TestRetryStatuses(unittest.TestCase):
    def test_transient_failures_are_retryable(self):
        for code in (429, 500, 502, 503, 504, 529):
            with self.subTest(code=code):
                self.assertIn(code, commitclerk.RETRY_STATUSES)

    def test_client_errors_are_not(self):
        for code in (400, 401, 403, 404, 422):
            with self.subTest(code=code):
                self.assertNotIn(code, commitclerk.RETRY_STATUSES)


def _http_error(code: int, body: str = "boom", retry_after: str | None = None):
    headers = email.message.Message()
    if retry_after is not None:
        headers["Retry-After"] = retry_after
    return urllib.error.HTTPError(
        "https://example/api", code, "err", headers, io.BytesIO(body.encode("utf-8"))
    )


class _FakeResponse:
    def __init__(self, payload: dict):
        self._body = json.dumps(payload).encode("utf-8")

    def read(self):
        return self._body

    def __enter__(self):
        return self

    def __exit__(self, *exc):
        return False


class TestPostJson(unittest.TestCase):
    """The retry loop, with the network and the clock mocked out."""

    def setUp(self):
        self.payload = {"model": "m", "temperature": 0.2, "messages": []}
        self.slept = []
        patcher = mock.patch.object(commitclerk.time, "sleep", self.slept.append)
        patcher.start()
        self.addCleanup(patcher.stop)
        # The retry notice belongs on a user's terminal, not in the test log.
        self.stderr = io.StringIO()
        stderr_patcher = mock.patch.object(commitclerk.sys, "stderr", self.stderr)
        stderr_patcher.start()
        self.addCleanup(stderr_patcher.stop)

    def _run(self, side_effect, **kwargs):
        with mock.patch.object(
            commitclerk.urllib.request, "urlopen", side_effect=side_effect
        ) as urlopen:
            result = commitclerk.post_json(
                "https://example/api", dict(self.payload), {}, label="Test", **kwargs
            )
        return result, urlopen

    def test_a_successful_call_does_not_sleep(self):
        result, urlopen = self._run([_FakeResponse({"ok": True})])
        self.assertEqual(result, {"ok": True})
        self.assertEqual(urlopen.call_count, 1)
        self.assertEqual(self.slept, [])

    def test_a_rate_limit_is_retried_and_then_succeeds(self):
        result, urlopen = self._run([_http_error(429), _FakeResponse({"ok": True})])
        self.assertEqual(result, {"ok": True})
        self.assertEqual(urlopen.call_count, 2)
        self.assertEqual(len(self.slept), 1)

    def test_retry_after_header_drives_the_wait(self):
        self._run([_http_error(429, retry_after="3"), _FakeResponse({"ok": True})])
        self.assertEqual(self.slept, [3.0])

    def test_the_retry_is_announced_on_stderr(self):
        self._run([_http_error(429, retry_after="3"), _FakeResponse({"ok": True})])
        notice = self.stderr.getvalue()
        self.assertIn("429", notice)
        self.assertIn("3.0s", notice)
        self.assertIn("retry 1 of 2", notice)
        self.assertTrue(notice.isascii(), notice)

    def test_a_client_error_fails_immediately(self):
        with self.assertRaises(SystemExit) as caught:
            self._run([_http_error(401, body="bad key")])
        self.assertIn("401", str(caught.exception))
        self.assertIn("bad key", str(caught.exception))
        self.assertEqual(self.slept, [])

    def test_exhausting_the_retries_reports_the_last_error(self):
        with self.assertRaises(SystemExit) as caught:
            self._run([_http_error(503)] * 3)
        self.assertIn("503", str(caught.exception))
        # Three attempts means two waits, not three.
        self.assertEqual(len(self.slept), 2)

    def test_a_network_blip_is_retried(self):
        result, urlopen = self._run(
            [urllib.error.URLError("connection reset"), _FakeResponse({"ok": True})]
        )
        self.assertEqual(result, {"ok": True})
        self.assertEqual(urlopen.call_count, 2)

    def test_a_refused_connection_is_not_retried(self):
        # `--provider ollama` with no server running: retrying cannot help.
        with self.assertRaises(SystemExit):
            self._run([urllib.error.URLError(ConnectionRefusedError(61, "refused"))])
        self.assertEqual(self.slept, [])

    def test_attempts_is_configurable(self):
        with self.assertRaises(SystemExit):
            self._run([_http_error(429)] * 5, attempts=5)
        self.assertEqual(len(self.slept), 4)


class TestRepairPayload(unittest.TestCase):
    """Self-healing on a 400 about a parameter we sent."""

    def test_drops_a_rejected_temperature(self):
        payload = {"model": "o3", "temperature": 0.2, "messages": []}
        repaired, what = commitclerk.repair_payload(
            payload,
            "Unsupported value: 'temperature' does not support 0.2 with this model.",
        )
        self.assertNotIn("temperature", repaired)
        self.assertIn("temperature", what)
        # The original is left alone — the caller decides what to send next.
        self.assertIn("temperature", payload)

    def test_renames_a_parameter_when_the_provider_names_the_replacement(self):
        payload = {"model": "o3", "max_tokens": 8192, "messages": []}
        repaired, what = commitclerk.repair_payload(
            payload,
            "Unsupported parameter: 'max_tokens' is not supported with this model. "
            "Use 'max_completion_tokens' instead.",
        )
        self.assertNotIn("max_tokens", repaired)
        self.assertEqual(repaired["max_completion_tokens"], 8192)
        self.assertIn("renamed", what)

    def test_a_required_parameter_is_never_dropped(self):
        # Dropping max_tokens would trade this 400 for "max_tokens: field required".
        payload = {"model": "m", "max_tokens": 8192, "messages": []}
        self.assertIsNone(
            commitclerk.repair_payload(payload, "max_tokens: 8192 > 4096, the maximum allowed")
        )

    def test_the_model_field_is_never_dropped(self):
        payload = {"model": "typo-4o", "messages": []}
        self.assertIsNone(commitclerk.repair_payload(payload, "The model `typo-4o` does not exist"))

    def test_an_unrelated_400_is_not_repairable(self):
        payload = {"model": "m", "temperature": 0.2, "messages": []}
        for body in ("invalid api key", "context_length_exceeded", ""):
            with self.subTest(body=body):
                self.assertIsNone(commitclerk.repair_payload(payload, body))

    def test_a_self_referential_suggestion_is_ignored(self):
        self.assertIsNone(commitclerk.suggested_replacement("use 'temperature' instead", "temperature"))


class TestPostJsonRepair(unittest.TestCase):
    def setUp(self):
        self.slept = []
        patcher = mock.patch.object(commitclerk.time, "sleep", self.slept.append)
        patcher.start()
        self.addCleanup(patcher.stop)
        stderr_patcher = mock.patch.object(commitclerk.sys, "stderr", io.StringIO())
        stderr_patcher.start()
        self.addCleanup(stderr_patcher.stop)

    def _run(self, side_effect, payload=None):
        payload = payload if payload is not None else {"model": "o3", "temperature": 0.2}
        with mock.patch.object(
            commitclerk.urllib.request, "urlopen", side_effect=side_effect
        ) as urlopen:
            result = commitclerk.post_json(
                "https://example/api", payload, {}, label="Test"
            )
        return result, urlopen

    def test_a_rejected_parameter_is_repaired_and_the_call_succeeds(self):
        rejection = _http_error(400, "Unsupported parameter: 'temperature' is not supported")
        result, urlopen = self._run([rejection, _FakeResponse({"ok": True})])
        self.assertEqual(result, {"ok": True})
        self.assertEqual(urlopen.call_count, 2)
        # A permanent error is not a rate limit: repair immediately, do not back off.
        self.assertEqual(self.slept, [])

    def test_the_repaired_request_no_longer_carries_the_parameter(self):
        rejection = _http_error(400, "Unsupported parameter: 'temperature' is not supported")
        sent = []

        def record(req, timeout=None):
            sent.append(json.loads(req.data.decode("utf-8")))
            if len(sent) == 1:
                raise rejection
            return _FakeResponse({"ok": True})

        with mock.patch.object(commitclerk.urllib.request, "urlopen", record):
            commitclerk.post_json(
                "https://example/api", {"model": "o3", "temperature": 0.2}, {}, label="Test"
            )
        self.assertIn("temperature", sent[0])
        self.assertNotIn("temperature", sent[1])

    def test_repair_happens_at_most_once(self):
        body = "Unsupported parameter: 'temperature' is not supported"
        with self.assertRaises(SystemExit) as caught:
            self._run([_http_error(400, body), _http_error(400, body)])
        self.assertIn("400", str(caught.exception))
        self.assertEqual(self.slept, [])

    def test_an_unrepairable_400_still_fails_immediately(self):
        with self.assertRaises(SystemExit) as caught:
            self._run([_http_error(400, "context_length_exceeded")])
        self.assertIn("context_length_exceeded", str(caught.exception))

    def test_a_repair_does_not_consume_the_transient_retry_budget(self):
        rejection = _http_error(400, "Unsupported parameter: 'temperature' is not supported")
        result, urlopen = self._run(
            [rejection, _http_error(429), _http_error(503), _FakeResponse({"ok": True})]
        )
        self.assertEqual(result, {"ok": True})
        self.assertEqual(urlopen.call_count, 4)
        self.assertEqual(len(self.slept), 2)


class TestBuildUserPrompt(unittest.TestCase):
    def test_lists_files_and_the_diff(self):
        prompt = commitclerk.build_user_prompt("DIFFBODY", ["a.py", "b.py"])
        self.assertIn("- a.py", prompt)
        self.assertIn("- b.py", prompt)
        self.assertIn("DIFFBODY", prompt)

    def test_the_guard_note_is_passed_through_verbatim(self):
        self.assertNotIn("GUARD", commitclerk.build_user_prompt("d", ["README.md"]))
        self.assertIn(
            "GUARD", commitclerk.build_user_prompt("d", ["README.md"], guard="GUARD")
        )

    def test_title_is_passed_as_already_chosen(self):
        prompt = commitclerk.build_user_prompt("d", ["a.py"], title="fix: x")
        self.assertIn("fix: x", prompt)
        self.assertIn("do not repeat it", prompt)

    def test_the_change_summary_is_included_before_the_diff(self):
        prompt = commitclerk.build_user_prompt(
            "DIFFBODY", ["a.py"], summary=" rename old.py => a.py (94%)"
        )
        self.assertIn("Change summary", prompt)
        self.assertIn("rename old.py => a.py (94%)", prompt)
        # It must survive a trimmed diff, so it goes first.
        self.assertLess(prompt.index("Change summary"), prompt.index("DIFFBODY"))

    def test_no_summary_means_no_empty_heading(self):
        self.assertNotIn("Change summary", commitclerk.build_user_prompt("d", ["a.py"]))

    def test_each_file_is_annotated_with_its_class(self):
        files = ["app.py", "package-lock.json"]
        prompt = commitclerk.build_user_prompt(
            "d", files, classes=commitclerk.classify_files(files)
        )
        self.assertIn("- app.py (code)", prompt)
        self.assertIn("- package-lock.json (generated)", prompt)
        self.assertIn("Class mix: generated 1, code 1", prompt)

    def test_without_classes_the_file_list_is_plain(self):
        prompt = commitclerk.build_user_prompt("d", ["app.py"])
        self.assertIn("- app.py\n", prompt)
        self.assertNotIn("Class mix", prompt)


def _git(repo, *args):
    subprocess.run(
        ["git", "-c", "user.email=t@example.com", "-c", "user.name=Test", *args],
        cwd=repo, check=True, capture_output=True, text=True,
    )


@unittest.skipUnless(shutil.which("git"), "git is not installed")
class TestStagedSummary(unittest.TestCase):
    """What `get_staged_summary` recovers that the diff body cannot show."""

    @classmethod
    def setUpClass(cls):
        repo = tempfile.mkdtemp()
        # LIFO: chdir back first, then remove the tree — Windows will not delete a
        # directory that is still the process's cwd. ignore_errors because git
        # leaves read-only objects behind.
        cls.addClassCleanup(shutil.rmtree, repo, True)
        cls.addClassCleanup(os.chdir, os.getcwd())
        _git(repo, "init", "-q", ".")
        for name, content in (
            ("old.py", b"".join(b"line %d\n" % i for i in range(10))),
            ("dead.txt", b"gone\n"),
            ("pic.bin", b"a\x00\x01\x02b"),
        ):
            pathlib.Path(repo, name).write_bytes(content)
        _git(repo, "add", "-A")
        _git(repo, "commit", "-qm", "init")

        # One staged change containing every fact a unified diff hides.
        _git(repo, "mv", "old.py", "new.py")
        pathlib.Path(repo, "pic.bin").write_bytes(b"c\x00\x09\x0ad" * 3)
        _git(repo, "rm", "-q", "dead.txt")
        pathlib.Path(repo, "added.md").write_text("plain\n")
        _git(repo, "add", "-A")

        os.chdir(repo)
        cls.summary = commitclerk.get_staged_summary()
        cls.diff = commitclerk.get_staged_diff()

    def test_a_rename_is_reported_as_a_rename(self):
        self.assertIn("rename old.py => new.py", self.summary)

    def test_a_creation_and_a_deletion_are_named(self):
        self.assertIn("create mode", self.summary)
        self.assertIn("added.md", self.summary)
        self.assertIn("delete mode", self.summary)
        self.assertIn("dead.txt", self.summary)

    def test_binary_sizes_appear_only_in_the_summary(self):
        # The diff says "Binary files ... differ" and nothing about size.
        self.assertIn("Bin 5 -> 15 bytes", self.summary)
        self.assertNotIn("15 bytes", self.diff)

    def test_the_summary_is_small_enough_to_always_send(self):
        self.assertLessEqual(len(self.summary), commitclerk.MAX_SUMMARY_CHARS)

    def test_an_oversized_summary_is_capped(self):
        capped = commitclerk.truncate("x" * 5_000, commitclerk.MAX_SUMMARY_CHARS)
        self.assertLessEqual(len(capped), commitclerk.MAX_SUMMARY_CHARS + 60)
        self.assertIn("truncated", capped)


if __name__ == "__main__":
    unittest.main()
