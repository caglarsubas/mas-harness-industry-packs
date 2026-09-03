from __future__ import annotations

import re
import unittest
from pathlib import Path


ROOT = Path(__file__).resolve().parents[2]
FORK_GUARD = "github.event_name != 'pull_request' || github.event.pull_request.head.repo.fork == false"


class IndustryRunnerTrustContract(unittest.TestCase):
    def test_public_fork_guard_precedes_self_hosted_runner_selection(self) -> None:
        workflow = (ROOT / ".github/workflows/verify.yml").read_text(encoding="utf-8")
        self.assertEqual(workflow.count(FORK_GUARD), 1)
        self.assertLess(
            workflow.index(FORK_GUARD),
            workflow.index(
                "runs-on: [self-hosted, harness-engineering, ephemeral, credential-free]"
            ),
        )

    def test_workflow_cannot_select_packet_or_consume_secrets(self) -> None:
        workflow = (ROOT / ".github/workflows/verify.yml").read_text(encoding="utf-8")
        self.assertNotIn("HARNESS_TASK_PACKET:", workflow)
        self.assertNotRegex(workflow, re.compile(r"\$\{\{\s*secrets\.", re.IGNORECASE))
        self.assertIn("pull_request:", workflow)
        self.assertIn("branches: [main]", workflow)


if __name__ == "__main__":
    unittest.main()
