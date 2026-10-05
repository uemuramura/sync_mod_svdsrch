from __future__ import annotations

import sys
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "TA-syncgitmdsearch" / "bin"))

from ta_syncgitmdsearch.md_parser import extract_spl
from ta_syncgitmdsearch.names import search_name_from_path
from ta_syncgitmdsearch.redact import redact_text
from ta_syncgitmdsearch.splunk_rest import _status_from_splunk_exception
from ta_syncgitmdsearch.url_util import validate_git_url


class MdParserTests(unittest.TestCase):
    def test_spl_fence(self):
        result = extract_spl(
            "# Title\n\n```spl\nindex=main | stats count\n```\n"
        )
        self.assertTrue(result.ok)
        self.assertEqual(result.source, "fence.spl")
        self.assertEqual(result.spl, "index=main | stats count")

    def test_frontmatter_search_wins(self):
        markdown = """---
search: |
  index=os
  | stats count by host
---

```spl
index=main | head 1
```
"""
        result = extract_spl(markdown)
        self.assertTrue(result.ok)
        self.assertEqual(result.source, "frontmatter.search")
        self.assertIn("index=os", result.spl)

    def test_main_fence_among_many(self):
        markdown = """```spl
index=main | head 1
```

```spl main
index=main | stats count by sourcetype
```
"""
        result = extract_spl(markdown)
        self.assertEqual(result.source, "fence.spl-main")
        self.assertIn("sourcetype", result.spl)

    def test_multiple_spl_without_main_is_error(self):
        markdown = """```spl
index=a
```

```spl
index=b
```
"""
        result = extract_spl(markdown)
        self.assertFalse(result.ok)
        self.assertEqual(result.error, "multiple_spl_blocks")

    def test_combine_spl_blocks(self):
        markdown = """---
combine_spl_blocks: true
---

```spl
index=main
```

```spl
| stats count
```
"""
        result = extract_spl(markdown)
        self.assertTrue(result.ok)
        self.assertEqual(result.source, "fence.spl.combined")
        self.assertIn("| stats count", result.spl)

    def test_html_comment(self):
        markdown = """```bash
echo hi
```

<!-- spl:start -->
index=web | stats count
<!-- spl:end -->
"""
        result = extract_spl(markdown)
        self.assertEqual(result.source, "html_comment")
        self.assertEqual(result.spl, "index=web | stats count")

    def test_heading_search(self):
        markdown = """# Notes

## サーチ

```
index=main | timechart count
```
"""
        result = extract_spl(markdown)
        self.assertEqual(result.source, "heading")
        self.assertEqual(result.spl, "index=main | timechart count")

    def test_unlabeled_single_fence(self):
        result = extract_spl("```\nindex=main | head 10\n```\n")
        self.assertTrue(result.ok)
        self.assertEqual(result.source, "fence.unlabeled")
        self.assertEqual(result.warning, "unlabeled_fence")

    def test_skip(self):
        result = extract_spl("---\nskip: true\n---\n\n```spl\nindex=main\n```\n")
        self.assertTrue(result.ok)
        self.assertTrue(result.skip)

    def test_no_spl(self):
        result = extract_spl("# just docs\n\nNo search here.\n")
        self.assertFalse(result.ok)
        self.assertEqual(result.error, "no_spl_found")

    def test_example_files(self):
        examples = ROOT / "examples"
        error_count = extract_spl((examples / "error_count.md").read_text(encoding="utf-8"))
        self.assertTrue(error_count.ok)
        self.assertEqual(error_count.source, "fence.spl")
        scheduled = extract_spl((examples / "scheduled_login_failures.md").read_text(encoding="utf-8"))
        self.assertEqual(scheduled.source, "frontmatter.search")
        self.assertTrue(scheduled.metadata.get("is_scheduled"))


class NameTests(unittest.TestCase):
    def test_filename(self):
        self.assertEqual(search_name_from_path("searches/error_count.md"), "error_count")

    def test_invalid_chars(self):
        self.assertEqual(search_name_from_path("a/b:c.md"), "b_c")


class UrlTests(unittest.TestCase):
    def test_https_ok(self):
        url = validate_git_url("https://github.com/org/repo.git")
        self.assertEqual(url, "https://github.com/org/repo.git")

    def test_rejects_embedded_credentials(self):
        with self.assertRaises(ValueError):
            validate_git_url("https://user:token@github.com/org/repo.git")

    def test_rejects_http(self):
        with self.assertRaises(ValueError):
            validate_git_url("http://github.com/org/repo.git")

    def test_rejects_file(self):
        with self.assertRaises(ValueError):
            validate_git_url("file:///tmp/repo")

    def test_rejects_metadata_ip(self):
        with self.assertRaises(ValueError):
            validate_git_url("https://169.254.169.254/repo.git")

    def test_scp_syntax(self):
        url = validate_git_url("git@github.com:org/repo.git")
        self.assertEqual(url, "git@github.com:org/repo.git")


class RedactTests(unittest.TestCase):
    def test_secret_and_url(self):
        text = redact_text(
            "fatal https://alice:s3cret@github.com/org/repo.git token=s3cret",
            ["s3cret"],
        )
        self.assertNotIn("s3cret", text)
        self.assertIn("***:***@", text)


class SplunkRestTests(unittest.TestCase):
    def test_resource_not_found_is_404(self):
        class ResourceNotFound(Exception):
            pass

        self.assertEqual(
            _status_from_splunk_exception(ResourceNotFound("[HTTP 404] missing")),
            404,
        )


if __name__ == "__main__":
    unittest.main()
