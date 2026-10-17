"""Guard: the engine CLI started by its path (no interpreter word), in PowerShell and Bash, goes through the same reel
gate rules as `python cli.py` / `reel`. Reviewer finding (3.0 P4): `& "D:\\...\\engine\\reel\\cli.py" approve-plan`
reached check_argv as the bare name `cli.py`, so a subagent skipped every gate (approve-plan, transcript-verify, ...).
The whole class is covered: quoted / unquoted / relative / forward or back slashes / mixed case / no `.py` / byte-code
/ 8.3 short path / hard link, through `&`, `.`, cmd /c, Invoke-Expression, Start-Process, [Diagnostics.Process]::Start,
variables set in the same command (and fail-closed for ones the guard cannot see), Bash `./cli.py`, `/d/...`,
`bash -c`, wrappers and `eval`. Another project's `cli.py` stays allowed.
Case list: D:/ClaudeData/Temp/wnc-p4/psguard/cases.md
Run:  tools/test.sh -p test_guard_ps_direct.py
"""
import sys as _sys
_sys.dont_write_bytecode = True  # keep the plugin folder free of __pycache__
import _isolation  # noqa: F401,E402  G79: sandbox the engine home first (tests/_isolation.py)
import ctypes
import os
import tempfile
import unittest
from pathlib import Path

from test_plugin import GUARD, SK, ClientFixture, hook

AGENT, OTHER, QC = "whynot-cut:story-editor", "other-plugin:helper", "whynot-cut:qc-reviewer"
SUBS = ("approve-plan --root . --video-id C0001", "transcript-verify --root . --video-id C0001")
MORE = ("auto-approve --root . --video-id C0001", "settings --init", "handoff --root . --video-id C0001 --delivered",
        "lock --root . --release", "reels-select --root . --episode E1 --pick 1",
        "ref-style --root . --adopt C0001 --yes", "verify --root . --video-id C0001 --record pass")
REAL = SK / "engine" / "reel" / "cli.py"          # the real engine CLI (its path has spaces)
IS_WIN = os.name == "nt"


def msys(p) -> str:
    """D:\\a\\b -> /d/a/b (Git Bash)."""
    s = str(p).replace("\\", "/")
    return "/" + s[0].lower() + s[2:] if len(s) > 1 and s[1] == ":" else s


def arr(s: str) -> str:
    """'approve-plan --root .' -> 'approve-plan','--root','.' (a PowerShell array)."""
    return ",".join(f"'{w}'" for w in s.split())


class Base(ClientFixture):
    def setUp(self):
        super().setUp()
        self.etmp = tempfile.TemporaryDirectory()
        self.plug = Path(self.etmp.name) / "wnc" / "whynot-cut"        # a fake plugin tree, no spaces in its path
        self.reel_dir = self.plug / "engine" / "reel"
        (self.reel_dir / "lib").mkdir(parents=True)
        (self.reel_dir / "__pycache__").mkdir()
        (self.plug / "bin").mkdir()
        self.F = self.reel_dir / "cli.py"
        self.F.write_text("# fake engine CLI\n", encoding="utf-8")
        self.PYC = self.reel_dir / "__pycache__" / "cli.cpython-312.pyc"
        self.PYC.write_bytes(b"\0")
        for n in ("reel", "reel.cmd"):
            (self.plug / "bin" / n).write_text("", encoding="utf-8")

    def tearDown(self):
        self.etmp.cleanup()
        super().tearDown()

    def run_tool(self, tool, cmd, agent=None, cwd=None):
        p = {"tool_name": tool, "tool_input": {"command": cmd}, "cwd": str(cwd or self.root)}
        if agent:
            p["agent_type"] = agent
        return hook(GUARD, p)[0]

    def gated(self, tool, forms, cwd=None, subs=SUBS, lead=True):
        """Every form, with each gated subcommand: a subagent (this plugin's and another's) is blocked; the lead is
        not (the gate rules are the subagents')."""
        for f in forms:
            for s in subs:
                cmd = f.replace("{S}", s).replace("{A}", arr(s))
                with self.subTest(tool=tool, cmd=cmd, agent=AGENT):
                    self.assertEqual(self.run_tool(tool, cmd, AGENT, cwd), 2)
            cmd = f.replace("{S}", subs[0]).replace("{A}", arr(subs[0]))
            with self.subTest(tool=tool, cmd=cmd, agent=OTHER):
                self.assertEqual(self.run_tool(tool, cmd, OTHER, cwd), 2)
            if lead:
                with self.subTest(tool=tool, cmd=cmd, agent="lead"):
                    self.assertEqual(self.run_tool(tool, cmd, None, cwd), 0)

    def allowed(self, tool, cmds, agent=AGENT, cwd=None):
        for c in cmds:
            with self.subTest(tool=tool, cmd=c, agent=agent):
                self.assertEqual(self.run_tool(tool, c, agent, cwd), 0)


class TestPowerShellDirect(Base):
    def test_P1_P5_absolute_path_forms(self):
        E, F = str(REAL), str(self.F)
        self.gated("PowerShell", [f'& "{E}" {{S}}', f"& '{E}' {{S}}", f"{F} {{S}}", f'& "{F}" {{S}}',
                                  f'& "{E.replace(chr(92), "/")}" {{S}}', f'& "{F.upper()}" {{S}}',
                                  f'& "{str(self.plug).upper()}\\Engine\\REEL\\Cli.Py" {{S}}'])

    def test_P1_more_gates(self):
        self.gated("PowerShell", [f'& "{REAL}" {{S}}'], subs=MORE)

    def test_P6_relative_paths(self):
        self.gated("PowerShell", [".\\cli.py {S}", "& .\\cli.py {S}", "./cli.py {S}"], cwd=self.reel_dir)
        self.gated("PowerShell", [".\\engine\\reel\\cli.py {S}", "& 'engine/reel/cli.py' {S}"], cwd=self.plug)
        self.gated("PowerShell", ["..\\cli.py {S}", '& "..\\..\\reel\\cli.py" {S}'], cwd=self.reel_dir / "lib")

    def test_P7_P8_P9_dot_source_no_extension_bytecode(self):
        F = str(self.F)
        self.gated("PowerShell", [f'. "{F}" {{S}}', f'. "{REAL}" {{S}}', f'& "{F[:-3]}" {{S}}',
                                  f'& "{self.PYC}" {{S}}', f'python "{self.PYC}" {{S}}', f'py -3 "{self.PYC}" {{S}}'])

    def test_P10_P11_cmd_and_invoke_expression(self):
        E, F = str(REAL), str(self.F)
        self.gated("PowerShell", [f'cmd /c "{E}" {{S}}', f"cmd /c {F} {{S}}", f'cmd.exe /c "{F} {{S}}"',
                                  f"Invoke-Expression \"& '{E}' {{S}}\"", f"iex '& \"{F}\" {{S}}'",
                                  f'$s = "& \'{F}\' {{S}}"; iex $s'])

    def test_P12_start_process(self):
        E, F = str(REAL), str(self.F)
        self.gated("PowerShell", [
            f'Start-Process -FilePath "{E}" -ArgumentList "{{S}}"',
            f"Start-Process python -ArgumentList '\"{E}\" {{S}}'",
            f"Start-Process python -ArgumentList '{F}',{{A}}",
            f"Start-Process -Wait -NoNewWindow -FilePath python -ArgumentList @('{F}',{{A}})",
            f'saps {F} -Wait -NoNewWindow -ArgumentList "{{S}}"',
            f'start python "{F} {{S}}"',
            f'Start-Process -File "{F}" -Arg "{{S}}"',
            f'Start-Process -FilePath:"{F}" -ArgumentList:"{{S}}"',
            f'Start-Process python -WorkingDirectory "{self.reel_dir}" -ArgumentList "cli.py {{S}}"',
            f'cmd /c start "" "{F}" {{S}}',
            f'cmd /c start "my title" /b python "{F}" {{S}}'])

    def test_P13_P14_variables(self):
        E, F = str(REAL), str(self.F)
        self.gated("PowerShell", [f'$c = "{E}"; & $c {{S}}', f"$c = '{F}'; python $c {{S}}",
                                  f"$c = '{F}'; & \"$c\" {{S}}", f"$py = 'python'; $c = '{F}'; & $py $c {{S}}",
                                  f'$root = "{self.plug}"; & "$root\\engine\\reel\\cli.py" {{S}}'])
        # set in an earlier call: the guard cannot see the value, so a gated subcommand after it is refused
        self.gated("PowerShell", ["& $cli {S}", "& $py $cli {S}", "& ${cli} {S}", "& $env:WNC_CLI {S}",
                                  "& $cfg.cli {S}", f"& (Join-Path '{self.plug}' 'engine\\reel\\cli.py') {{S}}",
                                  "& (Get-Command python) $cli {S}", f"& (gcm python) -X utf8 '{F}' {{S}}"])

    def test_P15_dotnet_process_start(self):
        E, F = str(REAL), str(self.F)
        self.gated("PowerShell", [f'[Diagnostics.Process]::Start("{E}", "{{S}}")',
                                  f"[System.Diagnostics.Process]::Start('python', '\"{F}\" {{S}}')",
                                  f"$c = '{F}'; [System.Diagnostics.Process]::Start($c, '{{S}}')"])

    def test_P16_P17_windows_name_forms_and_launcher(self):
        F, b = str(self.F), self.plug / "bin"
        self.gated("PowerShell", [f'& "{F}." {{S}}', f'& "{F} " {{S}}', f"& '{F}::$DATA' {{S}}",
                                  f'& "{b / "reel.cmd"}" {{S}}', f'& "{b / "reel"}" {{S}}',
                                  f'& "{str(b / "REEL.CMD")}." {{S}}'])

    @unittest.skipUnless(IS_WIN, "8.3 short names are a Windows thing")
    def test_P18_short_path(self):
        buf = ctypes.create_unicode_buffer(1024)
        n = ctypes.windll.kernel32.GetShortPathNameW(str(REAL), buf, 1024)
        if not n:
            self.skipTest("no short name")
        self.gated("PowerShell", [f'& "{buf.value}" {{S}}', f'python "{buf.value}" {{S}}'])

    def test_P19_hard_link_under_another_name(self):
        link = Path(self.etmp.name) / "x.py"
        try:
            os.link(REAL, link)
        except OSError as e:
            self.skipTest(f"no hard link: {e}")
        self.gated("PowerShell", [f'python "{link}" {{S}}', f'& "{link}" {{S}}'])
        self.gated("Bash", [f'python "{msys(link)}" {{S}}', f'"{msys(link)}" {{S}}'])

    def test_P20_P21_extras_for_the_lead_and_qc(self):
        E = str(REAL)
        for agent in (None, AGENT):
            self.assertEqual(self.run_tool("PowerShell", f'& "{E}" ae-build --root .', agent), 2)
            self.assertEqual(self.run_tool("PowerShell", f'& "{E}" ae-build --root . --extras', agent), 0)
        self.assertEqual(self.run_tool("PowerShell", f'& "{E}" ppro-build --root .', QC), 2)
        self.assertEqual(self.run_tool("PowerShell", f'& "{E}" ppro-build --root .', AGENT), 0)


class TestBashDirect(Base):
    def test_B1_B2_paths(self):
        E, F = REAL, self.F
        self.gated("Bash", [f'"{msys(E)}" {{S}}', f'"{str(E).replace(chr(92), "/")}" {{S}}', f"{msys(F)} {{S}}",
                            f"{str(F).replace(chr(92), '/')} {{S}}", f'"{msys(F).upper()}" {{S}}'])
        self.gated("Bash", ["./cli.py {S}", "./CLI.py {S}"], cwd=self.reel_dir)
        self.gated("Bash", ["engine/reel/cli.py {S}", "./engine/reel/cli {S}"], cwd=self.plug)

    def test_B1_more_gates(self):
        self.gated("Bash", [f'"{msys(REAL)}" {{S}}'], subs=MORE)

    def test_B3_B4_shells(self):
        F = msys(self.F)
        self.gated("Bash", [f"bash -c '\"{msys(REAL)}\" {{S}}'", f'sh -c "{F} {{S}}"', f'bash "{F}" {{S}}',
                            f"bash -e {F} {{S}}"])

    def test_B5_variables(self):
        F = msys(self.F)
        self.gated("Bash", [f'c="{F}"; "$c" {{S}}', f"c={F}; $c {{S}}", f'c="{F}"; python "$c" {{S}}',
                            f'root="{msys(self.plug)}"; "$root/engine/reel/cli.py" {{S}}'])
        self.gated("Bash", ['"$CLI" {S}', "${CLI} {S}", 'python3 "$CLI" {S}', "$(command -v cli.py) {S}"])

    def test_B6_B9_bytecode_cmd_wrappers_eval(self):
        F = msys(self.F)
        self.gated("Bash", [f'python "{msys(self.PYC)}" {{S}}', f'cmd //c "{self.F} {{S}}"',
                            f'exec "{F}" {{S}}', f'env "{F}" {{S}}', f'timeout 60 "{F}" {{S}}',
                            f"eval '\"{F}\" {{S}}'", f'start python "{F}" {{S}}'])


class TestNotOurs(Base):
    def test_N1_other_projects_cli(self):
        for tool in ("PowerShell", "Bash"):
            self.allowed(tool, ['& "D:\\other\\proj\\cli.py" approve-plan --root .' if tool == "PowerShell"
                                else '"/d/other/proj/cli.py" approve-plan --root .',
                                "python D:/other/cli.py transcript-verify --root .",
                                "python D:/x/reel/cli.py approve-plan" if tool == "Bash"
                                else '& "D:\\x\\reel\\cli.py" approve-plan'])

    def test_N2_allowed_engine_calls_by_path(self):
        E = str(REAL)
        self.allowed("PowerShell", [f'& "{E}" transcript-verify --root . --by agent', f'& "{E}" plan --root .',
                                    f'& "{E}" ref-style --root . --adopt C0001',
                                    f"Start-Process python -ArgumentList '\"{E}\" status'"])
        self.allowed("Bash", [f'"{msys(REAL)}" transcript-verify --root . --by agent', f'"{msys(REAL)}" plan'])

    def test_N3_N4_other_programs(self):
        self.allowed("PowerShell", ["Start-Process notepad", "Start-Process python -ArgumentList 'D:\\other\\cli.py approve-plan'",
                                    '$c = "git"; & $c status', '$c = "D:\\other\\cli.py"; & $c approve-plan',
                                    "& $py D:\\other\\cli.py approve-plan", "(Get-Content notes.txt) | Select-String plan"])
        self.allowed("Bash", ['c=git; "$c" status', 'python "$SCRIPT"', "start notepad"])


if __name__ == "__main__":
    unittest.main()
