"""Tests for scripts/package_tracker.py.

Run: python3 -m pytest tests/test_package_tracker.py
Fixture component directories live in a temporary tree; dnf and questionary
are mocked, so no network access or terminal is needed.
"""

import importlib.util
import subprocess
import sys
from pathlib import Path
from unittest import mock

import pytest
import yaml

ROOT = Path(__file__).resolve().parent.parent
_spec = importlib.util.spec_from_file_location("package_tracker", ROOT / "scripts" / "package_tracker.py")
pt = importlib.util.module_from_spec(_spec)
sys.modules["package_tracker"] = pt
_spec.loader.exec_module(pt)

BASE_YML = '''# SPDX-License-Identifier: MIT-0
---
# Blueprint component "base" (fixture).
label: "Base system"
# repo comment stays put
repo_urls:
  - "https://example.test/epel"
services:
  - "sshd"
kernel_args: []
packages:
  - "@system-tools"
  - "zsh"
  - "bash"
# trailing comment after the list
'''

NVIDIA_YML = '''# SPDX-License-Identifier: MIT-0
---
label: "NVIDIA stack"
repo_urls: []
services: []
kernel_args: ["nouveau.modeset=0"]
fragment: nvidia.toml
packages:
  - nvtop
  - "nvidia-driver"
'''

ONE_YML = '''---
label: "One package"
packages:
  - "only"
'''


def make_tree(root: Path) -> Path:
    files = root / "roles" / "osbuild" / "files"
    for target, comps in {
        "rocky/10/x86_64": {"base": BASE_YML, "nvidia": NVIDIA_YML, "single": ONE_YML},
        "fedora/43/x86_64": {"base": BASE_YML.replace('"zsh"', '"fish"'), "nvidia": NVIDIA_YML},
    }.items():
        comp_dir = files / target / "components"
        comp_dir.mkdir(parents=True)
        for name, text in comps.items():
            (comp_dir / f"{name}.yml").write_text(text)
    return root


@pytest.fixture
def tree(tmp_path):
    return make_tree(tmp_path)


@pytest.fixture
def store(tree):
    return pt.ComponentStore(pt.discover_targets(tree)["rocky/10/x86_64"])


def run(tree, *argv):
    return pt.main(["--repo-root", str(tree), *argv])


def text(store, name):
    return (store.directory / f"{name}.yml").read_text()


# -- discovery and targets ------------------------------------------------------


def test_discover_targets_finds_every_components_dir(tree):
    assert list(pt.discover_targets(tree)) == ["fedora/43/x86_64", "rocky/10/x86_64"]


def test_discover_targets_on_the_real_tree():
    targets = pt.discover_targets(ROOT)
    assert {"rocky/10/x86_64", "rocky/9/x86_64", "almalinux/10/x86_64", "fedora/43/x86_64"} <= set(targets)


def test_missing_target_exits_2_and_lists_targets(tree, capsys):
    assert run(tree, "list") == 2
    out = capsys.readouterr().out
    assert "--target is required" in out
    assert "rocky/10/x86_64" in out and "fedora/43/x86_64" in out


def test_unknown_target_exits_2(tree, capsys):
    assert run(tree, "list", "--target", "debian/12/x86_64") == 2
    assert "unknown" in capsys.readouterr().out


def test_unique_prefix_selects_target(tree, capsys):
    assert run(tree, "list", "--target", "rocky/10") == 0
    assert "rocky/10/x86_64" in capsys.readouterr().out


# -- list and search -----------------------------------------------------------


def test_list_prints_label_and_count(tree, capsys):
    assert run(tree, "list", "--target", "rocky/10/x86_64") == 0
    out = capsys.readouterr().out
    assert "base" in out and "3" in out and "Base system" in out
    assert "NVIDIA stack" in out and "One package" in out


def test_search_without_target_covers_all_targets(tree, capsys):
    assert run(tree, "search", "zsh") == 0
    out = capsys.readouterr().out
    assert "rocky/10/x86_64/base: zsh" in out
    assert "fedora" not in out


def test_search_hits_in_several_targets(tree, capsys):
    assert run(tree, "search", "nvtop") == 0
    out = capsys.readouterr().out
    assert "rocky/10/x86_64/nvidia: nvtop" in out
    assert "fedora/43/x86_64/nvidia: nvtop" in out


def test_search_with_target_and_no_hit(tree, capsys):
    assert run(tree, "search", "fish", "--target", "rocky/10/x86_64") == 1


# -- add -----------------------------------------------------------------------


def test_add_appends_and_keeps_comments(tree, store):
    before = text(store, "base")
    assert run(tree, "add", "--target", "rocky/10/x86_64", "base", "htop", "ripgrep") == 0
    after = text(store, "base")
    assert yaml.safe_load(after)["packages"] == ["@system-tools", "zsh", "bash", "htop", "ripgrep"]
    expected = before.replace('  - "bash"\n', '  - "bash"\n  - "htop"\n  - "ripgrep"\n')
    assert after == expected


def test_add_follows_the_quote_style_of_the_last_item(tree, store):
    run(tree, "add", "--target", "rocky/10/x86_64", "nvidia", "cuda-toolkit")
    assert text(store, "nvidia").endswith('  - "nvidia-driver"\n  - "cuda-toolkit"\n')
    plain = store.directory / "plain.yml"
    plain.write_text('label: "Plain"\npackages:\n  - alpha\n  - beta\n')
    store.add("plain", ["gamma", "@grp"])
    assert plain.read_text() == 'label: "Plain"\npackages:\n  - alpha\n  - beta\n  - gamma\n  - "@grp"\n'


def test_add_existing_package_changes_nothing(tree, store, capsys):
    before = text(store, "base")
    assert run(tree, "add", "--target", "rocky/10/x86_64", "base", "zsh") == 0
    assert text(store, "base") == before
    assert "already in base" in capsys.readouterr().out


def test_add_duplicate_in_other_component_is_refused_with_warning(tree, store, capsys):
    before = text(store, "base")
    assert run(tree, "add", "--target", "rocky/10/x86_64", "base", "nvtop") == 1
    assert text(store, "base") == before
    assert "already in nvidia" in capsys.readouterr().out


def test_add_duplicate_with_force(tree, store, capsys):
    assert run(tree, "add", "--target", "rocky/10/x86_64", "base", "nvtop", "--force") == 0
    assert "nvtop" in yaml.safe_load(text(store, "base"))["packages"]
    assert "also in nvidia" in capsys.readouterr().out


def test_add_to_other_target_is_not_a_duplicate(tree, store):
    assert run(tree, "add", "--target", "fedora/43/x86_64", "base", "zsh") == 0


def test_add_unknown_component_exits_2(tree, capsys):
    assert run(tree, "add", "--target", "rocky/10/x86_64", "nope", "x") == 2
    assert "Available components" in capsys.readouterr().out


def test_add_all_targets_adds_to_every_target(tree):
    assert run(tree, "add", "--all-targets", "base", "htop") == 0
    for target in ("rocky/10/x86_64", "fedora/43/x86_64"):
        store = pt.ComponentStore(pt.discover_targets(tree)[target])
        assert yaml.safe_load(text(store, "base"))["packages"][-1] == "htop"


def test_add_all_targets_skips_targets_without_the_component(tree, store, capsys):
    assert run(tree, "add", "--all-targets", "single", "extra") == 0
    assert yaml.safe_load(text(store, "single"))["packages"] == ["only", "extra"]
    assert "fedora/43/x86_64 has no component 'single'; skipped" in capsys.readouterr().out


def test_add_all_targets_unknown_component_exits_2(tree, capsys):
    assert run(tree, "add", "--all-targets", "nope", "x") == 2
    assert "No target has a component 'nope'" in capsys.readouterr().out


def test_add_all_targets_returns_worst_exit_code(tree, store):
    # zsh is already in rocky base (no change); nvtop is in nvidia in both targets (refused)
    assert run(tree, "add", "--all-targets", "base", "nvtop") == 1
    assert "nvtop" not in yaml.safe_load(text(store, "base"))["packages"]


def test_add_all_targets_with_target_is_an_error(tree):
    with pytest.raises(SystemExit):
        run(tree, "add", "--all-targets", "--target", "rocky/10/x86_64", "base", "htop")


def test_add_all_targets_invalid_name_changes_nothing(tree, store):
    before = text(store, "base")
    assert run(tree, "add", "--all-targets", "base", "ok", "a/b") == 2
    assert text(store, "base") == before


@pytest.mark.parametrize("bad", ["--installroot=/x", "-x", "", "a/b"])
def test_add_rejects_option_like_names(store, bad):
    with pytest.raises(pt.TrackerError):
        store.add("base", [bad])


def test_add_rejects_names_with_spaces(tree, store):
    with pytest.raises(pt.TrackerError):
        store.add("base", ["bad name"])


def test_add_accepts_comma_separated_names(tree, store):
    run(tree, "add", "--target", "rocky/10/x86_64", "base", "aa,bb")
    assert yaml.safe_load(text(store, "base"))["packages"][-2:] == ["aa", "bb"]


def test_add_group_gets_quotes_when_style_is_unquoted(tree, store):
    run(tree, "add", "--target", "rocky/10/x86_64", "nvidia", "@some-group")
    assert "@some-group" in yaml.safe_load(text(store, "nvidia"))["packages"]


# -- verify --------------------------------------------------------------------


def test_add_verify_skips_unavailable_packages(tree, store, capsys):
    with mock.patch.object(pt.RepoVerifier, "dnf_available", return_value=True), \
         mock.patch.object(pt.RepoVerifier, "check", return_value={"zzz-fake": None, "real": "epel"}):
        rc = run(tree, "add", "--target", "rocky/10/x86_64", "base", "zzz-fake", "real", "--verify")
    packages = yaml.safe_load(text(store, "base"))["packages"]
    assert rc == 1
    assert "real" in packages and "zzz-fake" not in packages
    assert "not in any rocky/10/x86_64 repo" in capsys.readouterr().out


def test_add_verify_skips_groups(tree, store):
    with mock.patch.object(pt.RepoVerifier, "dnf_available", return_value=True), \
         mock.patch.object(pt.subprocess, "run") as run_:
        assert run(tree, "add", "--target", "rocky/10/x86_64", "base", "@grp", "--verify") == 0
    run_.assert_not_called()
    assert "@grp" in yaml.safe_load(text(store, "base"))["packages"]


def test_add_verify_without_dnf_adds_nothing(tree, store):
    before = text(store, "base")
    with mock.patch.object(pt.RepoVerifier, "dnf_available", return_value=False):
        assert run(tree, "add", "--target", "rocky/10/x86_64", "base", "x", "--verify") == 2
    assert text(store, "base") == before


def test_add_verify_dnf_error_adds_nothing(tree, store):
    before = text(store, "base")
    with mock.patch.object(pt.RepoVerifier, "dnf_available", return_value=True), \
         mock.patch.object(pt.RepoVerifier, "check", side_effect=RuntimeError("net down")):
        assert run(tree, "add", "--target", "rocky/10/x86_64", "base", "x", "--verify") == 2
    assert text(store, "base") == before


def test_verifier_uses_target_base_repos_and_component_urls(store):
    verifier = pt.verifier_for(store, "rocky/10/x86_64")
    ids = [repo_id for repo_id, _ in verifier.profile]
    assert ids[:2] == ["rocky-baseos", "rocky-appstream"]
    assert any(url == "https://example.test/epel" for _, url in verifier.profile)


def test_cli_verify_exit_codes(tree):
    args = ("verify", "--target", "rocky/10/x86_64", "base")
    with mock.patch.object(pt.RepoVerifier, "dnf_available", return_value=True):
        with mock.patch.object(pt.RepoVerifier, "check", side_effect=lambda names: {n: "epel" for n in names}):
            assert run(tree, *args) == 0
        with mock.patch.object(pt.RepoVerifier, "check", side_effect=lambda names: {n: None for n in names}):
            assert run(tree, *args) == 1
        with mock.patch.object(pt.RepoVerifier, "check", side_effect=RuntimeError("x")):
            assert run(tree, *args) == 2
    with mock.patch.object(pt.RepoVerifier, "dnf_available", return_value=False):
        assert run(tree, *args) == 2


# -- remove --------------------------------------------------------------------


def test_remove_deletes_lines_and_keeps_comments(tree, store):
    before = text(store, "base")
    assert run(tree, "remove", "--target", "rocky/10/x86_64", "base", "zsh") == 0
    assert text(store, "base") == before.replace('  - "zsh"\n', "")


def test_remove_absent_package_warns(tree, store, capsys):
    before = text(store, "base")
    assert run(tree, "remove", "--target", "rocky/10/x86_64", "base", "nope") == 1
    assert text(store, "base") == before
    assert "'nope' is not in base" in capsys.readouterr().out


def test_remove_last_package_is_refused(tree, store, capsys):
    before = text(store, "single")
    assert run(tree, "remove", "--target", "rocky/10/x86_64", "single", "only") == 2
    assert text(store, "single") == before
    assert "non-empty packages list" in capsys.readouterr().out


def test_remove_everything_at_once_is_refused(tree, store):
    before = text(store, "base")
    assert run(tree, "remove", "--target", "rocky/10/x86_64", "base", "@system-tools", "zsh", "bash") == 2
    assert text(store, "base") == before


def test_remove_handles_unquoted_items(tree, store):
    run(tree, "remove", "--target", "rocky/10/x86_64", "nvidia", "nvtop")
    assert yaml.safe_load(text(store, "nvidia"))["packages"] == ["nvidia-driver"]


# -- repo verifier -------------------------------------------------------------


def _proc(stdout="", returncode=0, stderr=""):
    return subprocess.CompletedProcess([], returncode, stdout=stdout, stderr=stderr)


class TestRepoVerifier:
    def test_reports_repo_for_found_and_none_for_missing(self):
        v = pt.RepoVerifier("rocky/10")
        with mock.patch.object(pt.subprocess, "run", return_value=_proc("cmake rocky-appstream\nmeson rocky-crb\n")) as run_:
            result = v.check(["cmake", "meson", "docker-ce-cli-nope"])
        assert result == {"cmake": "rocky-appstream", "meson": "rocky-crb", "docker-ce-cli-nope": None}
        assert run_.call_count == 1

    def test_names_are_trailing_args_and_no_shell(self):
        v = pt.RepoVerifier("rocky/10")
        with mock.patch.object(pt.subprocess, "run", return_value=_proc("")) as run_:
            v.check(["a", "b"])
        cmd = run_.call_args.args[0]
        assert isinstance(cmd, list) and cmd[-2:] == ["a", "b"]
        assert "shell" not in run_.call_args.kwargs

    def test_extra_repo_urls_become_repofrompath_entries(self):
        v = pt.RepoVerifier("rocky/10", repo_urls=["https://example.test/epel", "https://x.test/metalink?repo=a"])
        cmd = v._command(["a"])
        assert any("https://example.test/epel" in c for c in cmd)
        assert not any("metalink" in c for c in cmd)

    def test_cache_avoids_second_call(self):
        v = pt.RepoVerifier("fedora/43")
        with mock.patch.object(pt.subprocess, "run", return_value=_proc("git fedora\n")) as run_:
            v.check(["git"])
            v.check(["git"])
        assert run_.call_count == 1

    def test_groups_are_skipped_not_queried(self):
        v = pt.RepoVerifier("rocky/10")
        with mock.patch.object(pt.subprocess, "run") as run_:
            result = v.check(["@development"])
        run_.assert_not_called()
        assert result["@development"] == pt.SKIPPED_GROUP

    def test_dnf_failure_raises_instead_of_reporting_missing(self):
        v = pt.RepoVerifier("rocky/10")
        with mock.patch.object(pt.subprocess, "run", return_value=_proc(returncode=1, stderr="Failed")):
            with pytest.raises(RuntimeError):
                v.check(["cmake"])

    @pytest.mark.parametrize("bad", ["--installroot=/x", "a b", ""])
    def test_rejects_option_like_or_blank_names(self, bad):
        with pytest.raises(ValueError):
            pt.RepoVerifier("rocky/10").check([bad])

    def test_unknown_target(self):
        with pytest.raises(ValueError):
            pt.RepoVerifier("debian/12")

    def test_profiles_cover_every_real_target(self):
        for target in pt.discover_targets(ROOT):
            pt.repo_profile(target)


# -- TUI -----------------------------------------------------------------------


class Script:
    """Scripted questionary answers, consumed in order per prompt kind."""

    def __init__(self, **answers):
        self.answers = {k: list(v) for k, v in answers.items()}
        self.asked = []

    def prompt(self, kind):
        def make(message, **kwargs):
            self.asked.append((kind, message, kwargs))
            value = self.answers[kind].pop(0)
            return mock.Mock(ask=lambda: value)
        return make


def tui(monkeypatch, tree, **answers):
    answers["select"] = ["Packages in a component", *answers["select"], "Exit"]
    script = Script(**answers)
    fake = mock.Mock(
        select=script.prompt("select"), checkbox=script.prompt("checkbox"),
        text=script.prompt("text"), confirm=script.prompt("confirm"),
    )
    monkeypatch.setattr(pt, "questionary", fake)
    monkeypatch.setattr(pt.RepoVerifier, "dnf_available", staticmethod(lambda dnf="dnf": False))
    stores = {t: pt.ComponentStore(d) for t, d in pt.discover_targets(tree).items()}
    pt.tui_main_loop(stores, tree)
    script.asked = script.asked[1:-1]  # drop the main-menu prompts
    return script


def test_tui_asks_for_target_only_when_several_exist(monkeypatch, tree):
    script = tui(monkeypatch, tree, select=["rocky/10/x86_64", None, None])
    first = script.asked[0]
    assert "Select target" in first[1]
    assert script.asked[1][1].startswith("rocky/10/x86_64: choose a component")


def test_tui_single_target_skips_target_prompt(monkeypatch, tmp_path):
    only = make_tree(tmp_path)
    import shutil
    shutil.rmtree(only / "roles/osbuild/files/fedora")
    script = tui(monkeypatch, only, select=[None])
    assert "choose a component" in script.asked[0][1]


def test_tui_component_list_shows_label_and_count_and_back(monkeypatch, tree):
    script = tui(monkeypatch, tree, select=["rocky/10/x86_64", None, None])
    choices = script.asked[1][2]["choices"]
    titles = [getattr(c, "title", c) for c in choices]
    assert any("Base system (3)" in str(t) for t in titles)
    assert titles[-1] == "Back"


def test_tui_back_and_exit_use_sentinels_not_none(monkeypatch, tree):
    script = tui(monkeypatch, tree, select=["rocky/10/x86_64", pt._BACK])
    target_choices = script.asked[0][2]["choices"]
    assert target_choices[-1].value == pt._EXIT
    assert script.asked[1][2]["choices"][-1].value == pt._BACK
    assert len(script.asked) == 2


def test_tui_submenu_offers_the_four_actions_and_back_returns(monkeypatch, tree):
    script = tui(monkeypatch, tree, select=["rocky/10/x86_64", "base", "Back", None, None])
    submenu = script.asked[2]
    assert submenu[2]["choices"] == ["Edit packages", "Add packages", "Show details", "Back"]
    assert "choose a component" in script.asked[3][1]


def test_tui_edit_removes_unchecked_after_confirmation(monkeypatch, tree):
    script = tui(
        monkeypatch, tree,
        select=["rocky/10/x86_64", "base", "Edit packages", "Back", None, None],
        checkbox=[["@system-tools", "bash"]],
        confirm=[True],
    )
    checkbox = next(a for a in script.asked if a[0] == "checkbox")
    assert [c.value for c in checkbox[2]["choices"]] == ["@system-tools", "zsh", "bash"]
    assert all(c.checked for c in checkbox[2]["choices"])
    confirm = next(a for a in script.asked if a[0] == "confirm")
    assert "zsh" in confirm[1]
    comp = pt.ComponentStore(pt.discover_targets(tree)["rocky/10/x86_64"]).load("base")
    assert comp.packages == ["@system-tools", "bash"]


def test_tui_edit_declined_confirmation_keeps_file(monkeypatch, tree):
    tui(monkeypatch, tree,
        select=["rocky/10/x86_64", "base", "Edit packages", "Back", None, None],
        checkbox=[["bash"]], confirm=[False])
    comp = pt.ComponentStore(pt.discover_targets(tree)["rocky/10/x86_64"]).load("base")
    assert comp.packages == ["@system-tools", "zsh", "bash"]


def test_tui_add_asks_before_duplicating_another_component(monkeypatch, tree):
    tui(monkeypatch, tree,
        select=["rocky/10/x86_64", "base", "Add packages", "Back", None, None],
        text=["nvtop htop"], confirm=[False])
    comp = pt.ComponentStore(pt.discover_targets(tree)["rocky/10/x86_64"]).load("base")
    assert comp.packages == ["@system-tools", "zsh", "bash", "htop"]


def test_tui_add_duplicate_confirmed_adds_it(monkeypatch, tree):
    tui(monkeypatch, tree,
        select=["rocky/10/x86_64", "base", "Add packages", "Back", None, None],
        text=["nvtop"], confirm=[True])
    comp = pt.ComponentStore(pt.discover_targets(tree)["rocky/10/x86_64"]).load("base")
    assert "nvtop" in comp.packages


def test_tui_show_details_prints_all_fields(monkeypatch, tree, capsys):
    monkeypatch.setattr(pt, "console", None)
    tui(monkeypatch, tree, select=["rocky/10/x86_64", "nvidia", "Show details", "Back", None, None])
    out = capsys.readouterr().out
    for needle in ("NVIDIA stack", "nouveau.modeset=0", "nvidia.toml", "repo_urls", "services"):
        assert needle in out


# -- playbook component selection ---------------------------------------------

PLAYBOOK = """---
- name: Fixture
  hosts: builder
  vars:
    osbuild_distro: "rocky-10.2"
    osbuild_blueprint_components:
      - base
      # keep this comment
      - nvidia
    osbuild_only_generate: true
"""


@pytest.fixture
def playbook(tree):
    path = tree / "playbooks" / "fixture.yml"
    path.parent.mkdir()
    path.write_text(PLAYBOOK)
    return path


def test_playbook_add_and_remove_change_only_the_list(tree, playbook):
    assert run(tree, "playbook", str(playbook), "add", "single", "--after", "base") == 0
    assert playbook.read_text() == PLAYBOOK.replace("      - base\n", "      - base\n      - single\n")
    assert run(tree, "playbook", str(playbook), "remove", "single", "nvidia") == 0
    assert playbook.read_text() == PLAYBOOK.replace("      # keep this comment\n      - nvidia\n", "      # keep this comment\n").replace("      - base\n      # keep", "      - base\n      # keep")


def test_playbook_add_unknown_component_is_refused(tree, playbook, capsys):
    assert run(tree, "playbook", str(playbook), "add", "nope") == 2
    assert playbook.read_text() == PLAYBOOK
    assert "No such component for rocky/10/x86_64" in capsys.readouterr().out


def test_playbook_cannot_be_emptied(tree, playbook):
    assert run(tree, "playbook", str(playbook), "remove", "base", "nvidia") == 2
    assert playbook.read_text() == PLAYBOOK


def test_playbook_list_marks_selected(tree, playbook, capsys):
    assert run(tree, "playbook", str(playbook), "list") == 0
    out = capsys.readouterr().out
    assert "[x] base" in out and "[ ] single" in out and "rocky/10/x86_64" in out


def test_playbook_add_is_idempotent(tree, playbook):
    run(tree, "playbook", str(playbook), "add", "base")
    assert playbook.read_text() == PLAYBOOK


def test_every_shipped_playbook_list_parses_and_names_real_components():
    targets = pt.discover_targets(ROOT)
    for path in (ROOT / "playbooks").glob("osbuild-*.yml"):
        pb = pt.PlaybookSelection(path)
        store = pt.ComponentStore(targets[pb.target()])
        assert set(pb.components) <= set(store.names()), path.name


def test_every_example_intent_list_parses_and_names_real_components():
    targets = pt.discover_targets(ROOT)
    examples = sorted((ROOT / "profiles" / "examples").glob("*.yml"))
    assert examples
    for path in examples:
        pb = pt.PlaybookSelection(path)
        store = pt.ComponentStore(targets[pb.target()])
        assert set(pb.components) <= set(store.names()), path.name


def test_intent_component_list_add_changes_only_the_list(tmp_path):
    src = ROOT / "profiles" / "examples" / "rocky-10-2-workstation-components.yml"
    intent = tmp_path / "mine.yml"
    intent.write_text(src.read_text())
    pb = pt.PlaybookSelection(intent)
    assert pb.target() == "rocky/10/x86_64"
    assert pb.add(["nvidia"], after="cockpit") == ["nvidia"]
    pb.save()
    assert intent.read_text() == src.read_text().replace("    - cockpit\n", "    - cockpit\n    - nvidia\n")


def test_tui_playbook_editor_applies_checkbox_changes(monkeypatch, tree, playbook):
    script = Script(
        select=["Components in a playbook", str(playbook), "Exit"],
        checkbox=[["base", "single"]],
        confirm=[True],
    )
    fake = mock.Mock(select=script.prompt("select"), checkbox=script.prompt("checkbox"),
                     text=script.prompt("text"), confirm=script.prompt("confirm"))
    monkeypatch.setattr(pt, "questionary", fake)
    stores = {t: pt.ComponentStore(d) for t, d in pt.discover_targets(tree).items()}
    pt.tui_main_loop(stores, tree)
    assert pt.PlaybookSelection(playbook).components == ["base", "single"]
