"""Tests for the availability verification in scripts/package_tracker.py.

Run: python3 -m unittest tests.test_package_tracker
dnf is mocked; no network access is needed.
"""

import importlib.util
import shutil
import subprocess
import tempfile
import unittest
from pathlib import Path
from unittest import mock

ROOT = Path(__file__).resolve().parent.parent
_spec = importlib.util.spec_from_file_location("package_tracker", ROOT / "scripts" / "package_tracker.py")
pt = importlib.util.module_from_spec(_spec)
_spec.loader.exec_module(pt)


def _proc(stdout="", returncode=0, stderr=""):
    return subprocess.CompletedProcess([], returncode, stdout=stdout, stderr=stderr)


class RepoVerifierTest(unittest.TestCase):
    def test_reports_repo_for_found_and_none_for_missing(self):
        v = pt.RepoVerifier("Rocky")
        with mock.patch.object(pt.subprocess, "run", return_value=_proc("cmake rocky-appstream\nmeson rocky-crb\n")) as run:
            result = v.check(["cmake", "meson", "docker-ce-cli-nope"])
        self.assertEqual(result, {"cmake": "rocky-appstream", "meson": "rocky-crb", "docker-ce-cli-nope": None})
        self.assertEqual(run.call_count, 1)

    def test_names_are_trailing_args_and_no_shell(self):
        v = pt.RepoVerifier("Rocky")
        with mock.patch.object(pt.subprocess, "run", return_value=_proc("")) as run:
            v.check(["a", "b"])
        cmd = run.call_args.args[0]
        self.assertIsInstance(cmd, list)
        self.assertEqual(cmd[-2:], ["a", "b"])
        self.assertNotIn("shell", run.call_args.kwargs)

    def test_cache_avoids_second_call(self):
        v = pt.RepoVerifier("Fedora")
        with mock.patch.object(pt.subprocess, "run", return_value=_proc("git fedora\n")) as run:
            v.check(["git"])
            v.check(["git"])
        self.assertEqual(run.call_count, 1)

    def test_groups_are_skipped_not_queried(self):
        v = pt.RepoVerifier("Rocky")
        with mock.patch.object(pt.subprocess, "run") as run:
            result = v.check(["@development"])
        run.assert_not_called()
        self.assertEqual(result["@development"], pt.SKIPPED_GROUP)

    def test_dnf_failure_raises_instead_of_reporting_missing(self):
        v = pt.RepoVerifier("Rocky")
        with mock.patch.object(pt.subprocess, "run", return_value=_proc(returncode=1, stderr="Failed to download metadata")):
            with self.assertRaises(RuntimeError):
                v.check(["cmake"])

    def test_rejects_option_like_or_blank_names(self):
        v = pt.RepoVerifier("Rocky")
        for bad in ("--installroot=/x", "a b", ""):
            with self.assertRaises(ValueError):
                v.check([bad])

    def test_unknown_distro(self):
        with self.assertRaises(ValueError):
            pt.RepoVerifier("Debian")

    def test_profiles_cover_every_distro(self):
        self.assertEqual(set(pt.REPO_PROFILES), set(pt.DISTROS))


class CliAddTest(unittest.TestCase):
    def setUp(self):
        self.tmp = Path(tempfile.mkdtemp())
        shutil.copytree(ROOT / "vars", self.tmp / "vars")
        self.manager = pt.TaxonomyManager(repo_root=self.tmp)
        self.addCleanup(shutil.rmtree, self.tmp)

    def _pkgs(self, distro):
        return [p for _, _, p in self.manager.all_taxonomy_packages(distro)]

    def test_unavailable_package_is_not_added(self):
        with mock.patch.object(pt.RepoVerifier, "dnf_available", return_value=True), \
             mock.patch.object(pt.RepoVerifier, "check", return_value={"zzz-fake": None}):
            pt.cli_add_package(self.manager, "Rocky", "System", "base", "zzz-fake")
        self.assertNotIn("zzz-fake", self._pkgs("Rocky"))

    def test_available_package_is_added(self):
        with mock.patch.object(pt.RepoVerifier, "dnf_available", return_value=True), \
             mock.patch.object(pt.RepoVerifier, "check", return_value={"zzz-real": "epel"}):
            pt.cli_add_package(self.manager, "Rocky", "System", "base", "zzz-real")
        self.assertIn("zzz-real", self._pkgs("Rocky"))

    def test_no_verify_adds_without_calling_dnf(self):
        with mock.patch.object(pt.RepoVerifier, "check") as check:
            pt.cli_add_package(self.manager, "Rocky", "System", "base", "zzz-raw", verify=False)
        check.assert_not_called()
        self.assertIn("zzz-raw", self._pkgs("Rocky"))

    def test_all_adds_only_where_available(self):
        def fake_check(verifier, names):
            return {n: ("epel" if verifier.distro == "Rocky" else None) for n in names}

        with mock.patch.object(pt.RepoVerifier, "dnf_available", return_value=True), \
             mock.patch.object(pt.RepoVerifier, "check", autospec=True, side_effect=fake_check):
            pt.cli_add_package(self.manager, "All", "System", "base", "zzz-rockyonly")
        self.assertIn("zzz-rockyonly", self._pkgs("Rocky"))
        self.assertNotIn("zzz-rockyonly", self._pkgs("Fedora"))
        self.assertNotIn("zzz-rockyonly", self._pkgs("AlmaLinux"))

    def test_dnf_error_adds_nothing(self):
        with mock.patch.object(pt.RepoVerifier, "dnf_available", return_value=True), \
             mock.patch.object(pt.RepoVerifier, "check", side_effect=RuntimeError("net down")):
            pt.cli_add_package(self.manager, "Rocky", "System", "base", "zzz-x")
        self.assertNotIn("zzz-x", self._pkgs("Rocky"))


class CliVerifyTest(unittest.TestCase):
    def setUp(self):
        self.tmp = Path(tempfile.mkdtemp())
        shutil.copytree(ROOT / "vars", self.tmp / "vars")
        self.manager = pt.TaxonomyManager(repo_root=self.tmp)
        self.addCleanup(shutil.rmtree, self.tmp)

    def test_exit_codes(self):
        with mock.patch.object(pt.RepoVerifier, "dnf_available", return_value=True):
            with mock.patch.object(pt.RepoVerifier, "check", return_value={"a": "epel"}):
                self.assertEqual(pt.cli_verify(self.manager, "Rocky", "a"), 0)
            with mock.patch.object(pt.RepoVerifier, "check", return_value={"a": None}):
                self.assertEqual(pt.cli_verify(self.manager, "Rocky", "a"), 1)
            with mock.patch.object(pt.RepoVerifier, "check", side_effect=RuntimeError("x")):
                self.assertEqual(pt.cli_verify(self.manager, "Rocky", "a"), 2)
        with mock.patch.object(pt.RepoVerifier, "dnf_available", return_value=False):
            self.assertEqual(pt.cli_verify(self.manager, "Rocky", "a"), 2)


if __name__ == "__main__":
    unittest.main()
