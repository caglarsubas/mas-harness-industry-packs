from __future__ import annotations

import unittest
from pathlib import Path


ROOT = Path(__file__).resolve().parents[2]


class IndustryRunnerTrustContract(unittest.TestCase):
    def test_repository_holds_no_workflow_file(self) -> None:
        workflows = ROOT / ".github" / "workflows"
        self.assertFalse(workflows.is_symlink(), "the workflow folder must not be a link")
        if workflows.exists():
            self.assertTrue(workflows.is_dir(), "the workflow folder must not be a file")
            entries = sorted(entry.relative_to(ROOT).as_posix() for entry in workflows.rglob("*") if entry.is_symlink() or not entry.is_dir())
            self.assertEqual(entries, [], "verification runs only through the hosted verifier; no workflow file may exist")


if __name__ == "__main__":
    unittest.main()
