# SPDX-License-Identifier: GPL-3.0-or-later
# © 2026 The Why Not AI (thewhynot.ai)
"""Phase 4 Task 41 (L-T3): `.github/workflows/security.yml`, checked as text (like test_security_watch.py).

Cases (lane work folder `L-T3/cases.md`): triggers are only `sec-*` / `v3.0.0-*` tags and a manual run; read-only token;
no secrets; Linux only with a 10-minute cap; every action pinned by full SHA (the same SHA the macOS workflow uses);
only `npm ci` / hashed installs; the scan step is the single local entry point and no step may swallow its exit code.
Run:  tools/test.sh -p test_security_scan_workflow.py
"""
import sys as _sys
_sys.dont_write_bytecode = True
import _isolation  # noqa: F401,E402
import re
import unittest
from pathlib import Path

REPO = Path(__file__).resolve().parents[2]
WF = REPO / ".github" / "workflows" / "security.yml"
MAC = REPO / ".github" / "workflows" / "macos.yml"


def code_lines(text):
    return [l for l in text.splitlines() if l.strip() and not l.lstrip().startswith("#")]


class SecurityWorkflow(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.text = WF.read_text(encoding="utf-8")
        cls.code = "\n".join(code_lines(cls.text))

    def test_triggers_are_only_the_two_tag_patterns_and_a_manual_run(self):
        on = re.search(r"(?ms)^on:\n(.*?)^(?=\S)", self.text).group(1)
        self.assertIn('tags: ["sec-*", "v3.0.0-*"]', on)
        self.assertIn("workflow_dispatch:", on)
        for bad in ("branches", "pull_request", "pull_request_target", "schedule", "workflow_run", "issue", "release", "public"):
            self.assertNotIn(bad, on, bad)
        self.assertEqual(len(re.findall(r"(?m)^  \w[\w_]*:", on)), 2, on)  # push + workflow_dispatch only

    def test_token_is_read_only_everywhere_and_no_secrets(self):
        self.assertRegex(self.code, r"(?m)^permissions:\n  contents: read\n")
        self.assertEqual(len(re.findall(r"(?m)^\s*permissions:", self.code)), 1)  # no job-level widening
        for bad in ("secrets.", "secrets:", "GITHUB_TOKEN", "id-token", "pull_request_target", "write"):
            self.assertNotIn(bad, self.code, bad)

    def test_linux_only_with_a_ten_minute_cap(self):
        runs_on = re.findall(r"runs-on:\s*(\S+)", self.code)
        self.assertTrue(runs_on)
        for r in runs_on:
            self.assertEqual(r, "ubuntu-24.04")
        for bad in ("macos", "windows", "ubuntu-latest", "self-hosted", "matrix"):
            self.assertNotIn(bad, self.code)
        jobs = len(re.findall(r"(?m)^  \w[\w-]*:\n    runs-on:", self.code))
        caps = [int(x) for x in re.findall(r"timeout-minutes:\s*(\d+)", self.code)]
        self.assertEqual(len(caps), jobs)
        self.assertTrue(all(c <= 10 for c in caps), caps)

    def test_every_action_is_pinned_by_full_sha_and_is_one_the_macos_workflow_already_uses(self):
        uses = re.findall(r"uses:\s*(\S+)(.*)", self.code)
        self.assertTrue(uses)
        mac = MAC.read_text(encoding="utf-8")
        for ref, rest in uses:
            self.assertRegex(ref, r"^actions/[\w-]+@[0-9a-f]{40}$", ref)
            self.assertRegex(rest, r"#\s*v\d", "a version comment next to the SHA")
            self.assertIn(ref, mac, "same pinned SHA as macos.yml: " + ref)

    def test_checkout_reads_full_history_and_keeps_no_credentials(self):
        self.assertIn("fetch-depth: 0", self.code)
        self.assertIn("persist-credentials: false", self.code)

    def test_no_curl_pipe_shell_no_unhashed_installs_no_sudo_no_artifacts(self):
        for bad in ("| sh", "| bash", "curl ", "wget ", "sudo ", "npm install", "npm i ", "pip install", "upload-artifact",
                    "actions/cache", "continue-on-error", "|| true", "if: always()", "if: failure()"):
            self.assertNotIn(bad, self.code, bad)

    def test_the_steps_are_the_pinned_installer_and_the_single_scan_entry_point(self):
        self.assertIn("python3 tools/security/install_tools.py", self.code)
        scan = re.search(r"python3 tools/security/scan\.py (.*)", self.code).group(1)
        self.assertIn("--all", scan)
        self.assertIn("--history", scan)
        self.assertIn("npm ci --ignore-scripts", self.code)

    def test_the_tools_home_is_the_runners_temp_folder_before_anything_installs(self):
        self.assertRegex(self.code, r'WNC_SEC_TOOLS=\$\{RUNNER_TEMP\}/sec-tools" >> "\$\{GITHUB_ENV\}"')
        self.assertLess(self.code.index("WNC_SEC_TOOLS"), self.code.index("install_tools.py"))

    def test_the_scan_step_writes_nothing_into_the_checkout_and_names_its_gate(self):
        scan = re.search(r"python3 tools/security/scan\.py (.*)", self.code).group(1)
        self.assertIn("--no-report", scan)
        self.assertIn('--raw "${RUNNER_TEMP}/sec-raw"', scan)
        self.assertIn('--gate "ci-${GITHUB_REF_NAME}"', scan)
        self.assertEqual(len(re.findall(r"python3 tools/security/", self.code)), 2)  # installer + scan both through python3

    def test_metrics_and_telemetry_are_off(self):
        self.assertIn('SEMGREP_SEND_METRICS: "off"', self.code)
        self.assertIn('DO_NOT_TRACK: "1"', self.code)

    def test_the_header_states_the_cost_and_the_dispatch_limit(self):
        head = self.text.split("name:")[0]
        self.assertIn("docs/ci.md", head)
        self.assertIn("default branch", head)
        self.assertIn("never uploaded", head.replace("nothing is uploaded", "never uploaded"))

    def test_scan_exit_codes_are_documented_and_all_non_zero_fail_the_job(self):
        head = self.text.split("name:")[0]
        for code in ("0 clean", "1 new High/Critical", "3 degraded", "4 a scanner is"):
            self.assertIn(code, head)


if __name__ == "__main__":
    unittest.main()
