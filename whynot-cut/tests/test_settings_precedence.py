"""3.0 T3.5: userConfig (language, approval, whisper_model, Magnific budget and key) and the settings precedence.

Highest wins, key by key: client `.local.md` > machine `.local.md` (clients folder, then ~) > userConfig (plugin options:
CLAUDE_PLUGIN_OPTION_* > the SessionStart pointer file > settings.json pluginConfigs) > defaults. Invalid values are
ignored with a warning. The Magnific API key never reaches a file, the pointer, a warning or the settings output.
Never touches the real ~/.whynot-cut or ~/.claude: HOME / USERPROFILE / CLAUDE_CONFIG_DIR point to temp folders.
Run:
    bash tools/test.sh -p test_settings_precedence.py
"""
import sys as _sys
_sys.dont_write_bytecode = True  # keep the plugin folder free of __pycache__
import _isolation  # noqa: F401,E402  G79: sandbox the engine home first (tests/_isolation.py)
import json
import os
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path
from unittest import mock

SK = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(SK / "engine" / "reel"))

from lib import plat, settings as S  # noqa: E402

CTX = SK / "hooks" / "session_context.py"
CLI = SK / "engine" / "reel" / "cli.py"
SECRET = "mgf-SECRET-0123456789"
OPT_ENV = plat.USER_OPTION_ENV + ("WHYNOT_OPTIONS_FILE", "CLAUDE_CONFIG_DIR", "WHYNOT_CLIENTS_ROOT",
                                  "CLAUDE_PLUGIN_OPTION_CLIENTS_ROOT", "REEL_CLIENTS_ROOT")


def write(path: Path, text: str) -> Path:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(text, encoding="utf-8")
    return path


def prefs(folder: Path, **kv) -> Path:
    """<folder>/.claude/whynot-cut.local.md holding exactly kv."""
    body = "".join(f"{k}: {str(v).lower() if isinstance(v, bool) else v}\n" for k, v in kv.items())
    return write(folder / ".claude" / S.FILE, f"---\n{body}---\nnotes of {folder.name}\n")


class Base(unittest.TestCase):
    """A fake machine: HOME, a clients folder, a client folder inside it, and no plugin options anywhere."""

    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        t = Path(self.tmp.name).resolve()
        self.user = t / "user"
        self.clients = self.user / "clients"          # under the fake home: the chain climbs no higher than it
        self.client = self.clients / "Client A"
        for d in (self.user, self.client):
            d.mkdir(parents=True)
        env = {k: v for k, v in os.environ.items() if k not in OPT_ENV}
        env.update(HOME=str(self.user), USERPROFILE=str(self.user), CLAUDE_CONFIG_DIR=str(self.user / ".claude"))
        self.patch = mock.patch.dict(os.environ, env, clear=True)
        self.patch.start()
        self.pointer = self.user / ".whynot-cut" / "plugin-options.json"
        self.addCleanup(self.patch.stop)
        self.addCleanup(self.tmp.cleanup)

    def opt(self, **kv):
        """Plugin options as Claude Code gives them to hooks."""
        for k, v in kv.items():
            os.environ["CLAUDE_PLUGIN_OPTION_" + k.upper()] = str(v)

    def machine(self, **kv):
        return prefs(self.user, **kv)

    def clients_file(self, **kv):
        os.environ["WHYNOT_CLIENTS_ROOT"] = str(self.clients)
        return prefs(self.clients, **kv)

    def load(self, folder=None):
        return S.load(folder or self.client)


class TestPrecedence(Base):
    def test_defaults_only(self):
        st = self.load()
        self.assertEqual((st["language"], st["approval"], st["whisper_model"], st["magnific_budget_credits"]),
                         ("ar", "ask", "large-v3", 300))
        self.assertIs(st["panel_link"], True)
        self.assertIsNone(st["_file"])
        self.assertEqual(st["_problems"], [])
        self.assertEqual(set(st["_sources"].values()), {"default"})

    def test_user_config_from_the_environment(self):
        self.opt(language="en", approval="auto", whisper_model="small", magnific_budget_credits=150)
        st = self.load()
        self.assertEqual((st["language"], st["approval"], st["whisper_model"], st["magnific_budget_credits"]),
                         ("en", "auto", "small", 150))
        self.assertEqual({st["_sources"][k] for k in plat.USER_OPTION_KEYS}, {"userConfig"})
        self.assertEqual(st["_where"]["approval"], "plugin option")
        self.assertIsNone(st["_file"])
        self.assertEqual(st["_problems"], [])

    def test_user_config_from_the_pointer_then_settings_json(self):
        write(self.user / ".claude" / "settings.json", json.dumps({"pluginConfigs": {
            "whynot-cut@thewhynot-ai": {"options": {"language": "en", "approval": "auto", "whisper_model": "medium",
                                                    "magnific_budget_credits": 50}}}}))
        st = self.load()
        self.assertEqual((st["language"], st["approval"], st["whisper_model"], st["magnific_budget_credits"]),
                         ("en", "auto", "medium", 50))                       # settings.json: numbers stay numbers
        write(self.pointer, json.dumps({"engine_home": "", "clients_root": "", "language": "ar",
                                        "whisper_model": "large-v3-turbo", "approval": ""}))
        st = self.load()
        self.assertEqual((st["language"], st["whisper_model"]), ("ar", "large-v3-turbo"))   # pointer beats settings.json
        self.assertEqual(st["approval"], "auto")                  # "" in the pointer = unset: the next source decides
        self.opt(language="en")
        self.assertEqual(self.load()["language"], "en")                    # the environment beats the pointer

    def test_each_layer_wins_over_the_next(self):
        self.opt(language="en", approval="auto", whisper_model="small", magnific_budget_credits=10)
        self.assertEqual(self.load()["whisper_model"], "small")                    # userConfig over the default
        self.machine(whisper_model="medium")
        self.assertEqual(self.load()["whisper_model"], "medium")                   # ~ file over userConfig
        self.clients_file(whisper_model="large-v3-turbo")
        st = self.load()
        self.assertEqual((st["whisper_model"], st["_sources"]["whisper_model"]), ("large-v3-turbo", "machine"))
        self.assertEqual(st["_where"]["whisper_model"], str(self.clients / ".claude" / S.FILE))   # clients folder over ~
        prefs(self.client, whisper_model="large-v3")
        st = self.load()
        self.assertEqual((st["whisper_model"], st["_sources"]["whisper_model"]), ("large-v3", "client"))
        self.assertEqual(st["_file"], str(self.client / ".claude" / S.FILE))          # client over the machine

    def test_a_layer_that_does_not_set_a_key_lets_the_next_one_decide(self):
        self.opt(approval="auto", magnific_budget_credits=90)
        self.machine(language="en", whisper_model="medium")
        prefs(self.client, approval="ask")
        st = self.load()
        self.assertEqual((st["approval"], st["language"], st["whisper_model"], st["magnific_budget_credits"]),
                         ("ask", "en", "medium", 90))
        self.assertEqual((st["_sources"]["approval"], st["_sources"]["language"], st["_sources"]["whisper_model"],
                          st["_sources"]["magnific_budget_credits"]), ("client", "machine", "machine", "userConfig"))
        self.assertEqual(st["_sources"]["panel_link"], "default")
        self.assertEqual([f["layer"] for f in st["_files"]], ["client", "machine"])

    def test_nearest_client_file_wins_over_a_parent_and_machine_files_come_last(self):
        sub = self.client / "deep" / "er"
        sub.mkdir(parents=True)
        prefs(self.client, language="en", approval="auto")
        prefs(sub, language="ar")
        self.machine(approval="ask", whisper_model="small")
        st = S.load(sub)
        self.assertEqual((st["language"], st["approval"], st["whisper_model"]), ("ar", "auto", "small"))
        self.assertEqual([f["layer"] for f in st["_files"]], ["client", "client", "machine"])

    def test_home_on_the_folder_chain_counts_as_machine(self):
        """A client folder under ~ still ranks the ~ file as machine-wide, below the clients folder's file."""
        under = self.user / "Documents" / "Client B"
        under.mkdir(parents=True)
        self.machine(language="en")
        os.environ["WHYNOT_CLIENTS_ROOT"] = str(self.user / "Documents")
        prefs(self.user / "Documents", language="ar")
        st = S.load(under)
        self.assertEqual(st["language"], "ar")
        self.assertEqual([f["layer"] for f in st["_files"]], ["machine", "machine"])
        self.assertEqual(S.find(under), self.user / "Documents" / ".claude" / S.FILE)

    def test_missing_layers_are_fine(self):
        self.assertEqual(self.load(self.user / "nowhere" / "yet")["language"], "ar")   # a folder that does not exist
        write(self.pointer, "{ not json")                                                # a broken pointer
        write(self.user / ".claude" / "settings.json", "[1, 2")                          # a broken settings.json
        st = self.load()
        self.assertEqual((st["language"], st["_problems"]), ("ar", []))

    def test_panel_link_follows_the_chain(self):
        self.assertIs(self.load()["panel_link"], True)
        self.machine(panel_link=True)
        prefs(self.client, panel_link=False)
        st = self.load()
        self.assertIs(st["panel_link"], False)
        self.assertEqual(st["_sources"]["panel_link"], "client")
        self.assertIs(S.load(self.clients)["panel_link"], True)           # outside that client: the machine file

    def test_clients_root_is_not_layered(self):
        """clients_root keeps its rule: the plugin option (plat.clients_root_setting) wins; the file value is data."""
        self.machine(clients_root=str(self.clients))
        self.assertEqual(self.load()["clients_root"], str(self.clients))
        self.assertEqual(self.load()["_sources"]["clients_root"], "machine")


class TestBadValues(Base):
    def test_bad_file_value_is_ignored_with_a_warning_and_the_next_layer_applies(self):
        self.opt(whisper_model="small")
        f = prefs(self.client, whisper_model="turbo", approval="auto")
        st = self.load()
        self.assertEqual((st["whisper_model"], st["approval"]), ("small", "auto"))   # the good key of that file still counts
        self.assertEqual(len(st["_problems"]), 1)
        self.assertIn(str(f), st["_problems"][0])
        self.assertIn("whisper_model", st["_problems"][0])
        self.assertIn("'turbo'", st["_problems"][0])

    def test_bad_value_with_nothing_below_gives_the_default(self):
        prefs(self.client, whisper_model="turbo", language="fr", approval="maybe")
        st = self.load()
        self.assertEqual((st["whisper_model"], st["language"], st["approval"]), ("large-v3", "ar", "ask"))
        self.assertEqual(len(st["_problems"]), 3)
        self.assertEqual(set(st["_sources"][k] for k in ("whisper_model", "language", "approval")), {"default"})

    def test_bad_plugin_option_gives_the_default_and_a_warning(self):
        self.opt(language="fr", approval="always", whisper_model="tiny", magnific_budget_credits="lots")
        st = self.load()
        self.assertEqual((st["language"], st["approval"], st["whisper_model"], st["magnific_budget_credits"]),
                         ("ar", "ask", "large-v3", 300))
        self.assertEqual(len(st["_problems"]), 4)
        self.assertTrue(all(p.startswith("plugin option ") for p in st["_problems"]), st["_problems"])

    def test_budget_values(self):
        for text, want in (("0", 0), ("250", 250), ("12.5", 12.5), (" 40 ", 40)):
            with self.subTest(text):
                self.opt(magnific_budget_credits=text)
                st = self.load()
                self.assertEqual((st["magnific_budget_credits"], st["_problems"]), (want, []))
        for bad in ("-5", "abc", "nan", "1e400", "true"):
            with self.subTest(bad):
                self.opt(magnific_budget_credits=bad)
                st = self.load()
                self.assertEqual(st["magnific_budget_credits"], 300)
                self.assertEqual(len(st["_problems"]), 1)
        prefs(self.client, magnific_budget_credits=0)                     # a file may switch Magnific off
        self.assertEqual(self.load()["magnific_budget_credits"], 0)

    def test_empty_plugin_options_are_unset_not_invalid(self):
        self.opt(language="", approval="  ", whisper_model="", magnific_budget_credits="")
        st = self.load()
        self.assertEqual((st["language"], st["_problems"]), ("ar", []))

    def test_bad_boolean_preference(self):
        prefs(self.client, panel_link="maybe")
        st = self.load()
        self.assertIs(st["panel_link"], True)
        self.assertEqual(len(st["_problems"]), 1)

    def test_a_file_that_is_not_utf8_is_skipped_and_the_rest_applies(self):
        self.machine(language="en")
        d = self.client / ".claude"
        d.mkdir()
        (d / S.FILE).write_bytes(b"---\nlanguage: ar\neditor_name: Ren\xe9\n---\n")
        st = self.load()
        self.assertEqual(st["language"], "en")                           # the client file is dropped, the machine's stays
        self.assertEqual(len(st["_problems"]), 1)
        self.assertIn("line 3", st["_problems"][0])


class TestSecrets(Base):
    def test_the_api_key_never_appears_in_the_settings(self):
        self.opt(magnific_api_key=SECRET, language="fr")           # + a warning to scan
        st = self.load()
        self.assertIs(st["magnific_api_key_set"], True)
        self.assertNotIn(SECRET, json.dumps(st, ensure_ascii=False, default=str))
        self.assertNotIn("magnific_api_key", {k for k in st if k != "magnific_api_key_set"})
        self.assertIs(S.load(self.client)["magnific_api_key_set"], True)
        os.environ.pop("CLAUDE_PLUGIN_OPTION_MAGNIFIC_API_KEY")
        self.assertIs(self.load()["magnific_api_key_set"], False)

    def test_a_key_typed_into_a_preferences_file_is_dropped_and_never_echoed(self):
        prefs(self.client, magnific_api_key=SECRET, language="en")
        st = self.load()
        self.assertEqual(st["language"], "en")                       # the rest of the file still applies
        self.assertIs(st["magnific_api_key_set"], False)             # a file never provides the key
        self.assertNotIn("magnific_api_key", {k for k in st if k != "magnific_api_key_set"})
        self.assertNotIn(SECRET, json.dumps(st, ensure_ascii=False, default=str))
        self.assertTrue(any("keep the Magnific key in the plugin options" in p for p in st["_problems"]))
        _, _, problems = S.read_file(self.client / ".claude" / S.FILE)
        self.assertNotIn(SECRET, " ".join(problems))

    def test_plugin_options_never_returns_secrets_and_secret_option_reads_only_the_environment(self):
        self.opt(magnific_api_key=SECRET)
        write(self.pointer, json.dumps({"magnific_api_key": "from-the-pointer", "engine_home": ""}))
        write(self.user / ".claude" / "settings.json", json.dumps({"pluginConfigs": {
            "whynot-cut@thewhynot-ai": {"options": {"magnific_api_key": "from-settings"}}}}))
        self.assertNotIn("magnific_api_key", plat.plugin_options(plat.USER_OPTION_KEYS))
        self.assertEqual(plat.secret_option("magnific_api_key"), SECRET)
        os.environ.pop("CLAUDE_PLUGIN_OPTION_MAGNIFIC_API_KEY")
        self.assertEqual(plat.secret_option("magnific_api_key"), "")      # never the pointer or settings.json

    def test_render_and_save_cannot_write_it(self):
        text = S.render({"language": "en", "magnific_api_key": SECRET, "magnific_api_key_set": True,
                         "_where": {}, "_problems": []})
        self.assertIn("language", text)
        self.assertNotIn("magnific_api_key_set", text)
        # an unknown key is kept for forward compatibility, but the CLI only accepts DEFAULTS keys (checked below)

    def test_the_session_hook_writes_the_options_to_the_pointer_but_never_the_key(self):
        env = dict(os.environ, CLAUDE_PLUGIN_ROOT=str(SK), CLAUDE_ENV_FILE=str(self.user / "env.sh"),
                   CLAUDE_PLUGIN_DATA=str(self.user / "data"), CLAUDE_PLUGIN_OPTION_LANGUAGE="en",
                   CLAUDE_PLUGIN_OPTION_APPROVAL="auto", CLAUDE_PLUGIN_OPTION_WHISPER_MODEL="large-v3-turbo",
                   CLAUDE_PLUGIN_OPTION_MAGNIFIC_BUDGET_CREDITS="120", CLAUDE_PLUGIN_OPTION_MAGNIFIC_API_KEY=SECRET)
        r = subprocess.run([sys.executable, "-B", str(CTX)], input=json.dumps({"cwd": str(self.user)}),
                           capture_output=True, text=True, encoding="utf-8", env=env)
        self.assertEqual(r.returncode, 0, r.stderr)
        d = json.loads(self.pointer.read_text(encoding="utf-8"))
        self.assertEqual((d["language"], d["approval"], d["whisper_model"], d["magnific_budget_credits"]),
                         ("en", "auto", "large-v3-turbo", "120"))
        self.assertIn("engine_home", d)
        for f in (self.pointer, self.user / "env.sh"):
            if f.exists():
                self.assertNotIn(SECRET, f.read_text(encoding="utf-8"), f)
        self.assertNotIn(SECRET, r.stdout + r.stderr)
        # and the engine reads those back as the userConfig layer, from the pointer alone
        for k in OPT_ENV[:len(plat.USER_OPTION_ENV)]:
            os.environ.pop(k, None)
        os.environ["WHYNOT_OPTIONS_FILE"] = str(self.pointer)
        st = self.load()
        self.assertEqual((st["language"], st["approval"], st["whisper_model"], st["magnific_budget_credits"]),
                         ("en", "auto", "large-v3-turbo", 120))
        self.assertEqual({st["_sources"][k] for k in plat.USER_OPTION_KEYS}, {"userConfig"})


class TestFilesHoldOnlyWhatIsSet(Base):
    """`reel settings --init` must not pin defaults or other layers' values into a file: they would shadow the plugin
    options and the machine file."""

    def reel(self, *args):
        env = dict(os.environ)
        r = subprocess.run([sys.executable, "-B", str(CLI), *args], capture_output=True, text=True, encoding="utf-8",
                           env=env)
        return r

    def test_a_new_file_holds_only_the_set_keys(self):
        self.opt(approval="auto", language="en")
        folder = self.client
        r = self.reel("settings", "--init", str(folder), "--set", "whisper_model=medium")
        self.assertEqual(r.returncode, 0, r.stderr)
        fm, _ = S.parse((folder / ".claude" / S.FILE).read_text(encoding="utf-8"))
        self.assertEqual(fm, {"whisper_model": "medium"})
        doc = json.loads(r.stdout)
        self.assertEqual((doc["whisper_model"], doc["approval"], doc["language"]), ("medium", "auto", "en"))
        self.assertEqual(doc["_sources"]["approval"], "userConfig")

    def test_rewriting_keeps_the_files_own_values_and_not_other_layers(self):
        self.machine(language="en", approval="auto")
        prefs(self.client, whisper_model="small")
        r = self.reel("settings", "--init", str(self.client), "--force", "--set", "approval=ask")
        self.assertEqual(r.returncode, 0, r.stderr)
        fm, body = S.parse((self.client / ".claude" / S.FILE).read_text(encoding="utf-8"))
        self.assertEqual(fm, {"approval": "ask", "whisper_model": "small"})           # no language: the machine file's
        self.assertIn("notes of Client A", body)

    def test_an_empty_file_is_valid(self):
        path = S.save(self.client / ".claude" / S.FILE, {})
        self.assertEqual(S.parse(path.read_text(encoding="utf-8"))[0], {})
        self.assertEqual(S.load(self.client)["_problems"], [])

    def test_set_validates_every_new_key(self):
        for bad in ("approval=always", "magnific_budget_credits=-1", "magnific_budget_credits=lots", "panel_link=maybe",
                    "magnific_api_key=anything", "whisper_model=tiny"):
            with self.subTest(bad):
                r = self.reel("settings", "--init", str(self.client), "--set", bad)
                self.assertNotEqual(r.returncode, 0)
                self.assertFalse((self.client / ".claude" / S.FILE).exists())
                self.assertNotIn("anything", r.stderr + r.stdout) if "api_key" in bad else None
        r = self.reel("settings", "--init", str(self.client), "--set", "magnific_budget_credits=250,language=en")
        self.assertEqual(r.returncode, 0, r.stderr)
        self.assertEqual(S.load(self.client)["magnific_budget_credits"], 250)

    def test_reel_settings_shows_where_each_value_comes_from(self):
        self.opt(approval="auto")
        prefs(self.client, language="en")
        doc = json.loads(self.reel("settings", "--root", str(self.client)).stdout)
        self.assertEqual((doc["_sources"]["language"], doc["_sources"]["approval"]), ("client", "userConfig"))
        self.assertEqual(doc["_problems"], [])


class TestManifest(unittest.TestCase):
    """plugin.json userConfig and the engine agree, so a default never drifts between the two."""

    @classmethod
    def setUpClass(cls):
        cls.uc = json.loads((SK / ".claude-plugin" / "plugin.json").read_text(encoding="utf-8"))["userConfig"]

    def test_the_declared_options(self):
        for k, opts in (("language", ["ar", "en"]), ("approval", ["ask", "auto"]),
                        ("whisper_model", ["large-v3", "large-v3-turbo", "medium", "small"])):
            self.assertEqual(self.uc[k]["type"], "string", k)
            self.assertEqual(self.uc[k]["options"], opts, k)
            self.assertEqual(set(self.uc[k]["options"]), S.CHOICES[k], k)
            self.assertEqual(self.uc[k]["default"], S.DEFAULTS[k], k)
            self.assertIs(self.uc[k]["required"], False, k)
        self.assertEqual((self.uc["language"]["default"], self.uc["approval"]["default"],
                          self.uc["whisper_model"]["default"]), ("ar", "ask", "large-v3"))
        b = self.uc["magnific_budget_credits"]
        self.assertEqual((b["type"], b["default"], b["min"]), ("number", 300, 0))
        self.assertEqual(S.DEFAULTS["magnific_budget_credits"], 300)

    def test_the_api_key_is_sensitive_and_optional(self):
        k = self.uc["magnific_api_key"]
        self.assertIs(k["sensitive"], True)
        self.assertIs(k["required"], False)
        self.assertNotIn("default", k)
        self.assertNotIn("magnific_api_key", S.DEFAULTS)

    def test_every_option_the_engine_reads_is_declared(self):
        for k in plat.USER_OPTION_KEYS + plat.SECRET_OPTION_KEYS:
            self.assertIn(k, self.uc, k)
        self.assertEqual(plat.USER_OPTION_ENV[0], "CLAUDE_PLUGIN_OPTION_LANGUAGE")
        for k in ("clients_root", "engine_home"):
            self.assertIn(k, self.uc)                                       # the two T1.9 options are untouched


class TestPrefsLine(Base):
    """The SessionStart text names the plugin options when no file exists (so `approval: auto` set there is honoured)."""

    def ctx(self):
        import importlib.util
        spec = importlib.util.spec_from_file_location("wnc_session_context_t35", CTX)
        m = importlib.util.module_from_spec(spec)
        spec.loader.exec_module(m)
        return m

    def test_none_yet_without_files_or_options(self):
        self.assertIn("none yet", self.ctx().prefs_line(self.load()))

    def test_plugin_options_alone_are_reported(self):
        self.opt(approval="auto", language="ar", whisper_model="small")
        line = self.ctx().prefs_line(self.load())
        self.assertIn("plugin options", line)
        self.assertIn("Approval: auto", line)
        self.assertIn("standing preference in plugin option", line)
        self.assertIn("Arabic", line)
        self.assertIn("Whisper: small", line)

    def test_a_file_that_sets_approval_is_named(self):
        self.opt(approval="ask")
        f = prefs(self.client, approval="auto")
        line = self.ctx().prefs_line(self.load())
        self.assertIn(f"standing preference in {f}", line)


if __name__ == "__main__":
    unittest.main()
