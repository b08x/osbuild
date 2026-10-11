#!/usr/bin/env python3
"""osbuild package tracker.

Lists, searches, adds and removes packages in the component files that the
osbuild role composes blueprints from:

    roles/osbuild/files/<distro>/<major>/<arch>/components/<name>.yml

A *target* is one <distro>/<major>/<arch> directory (for example
``rocky/10/x86_64``). Edits change only the ``packages:`` list of one component
file. Comments, key order and the order of existing packages stay as they are;
new packages are appended.

Commands (``--target`` is required except for ``search``):

    list   --target T
    search NAME [--target T]
    add    --target T COMPONENT PKG... [--verify] [--force]
    remove --target T COMPONENT PKG...
    verify --target T [COMPONENT]
    playbook PLAYBOOK list|add|remove [COMPONENT...] [--target T] [--after C]
    tui
"""

from __future__ import annotations

import argparse
import re
import shutil
import subprocess
import sys
from dataclasses import dataclass
from pathlib import Path
from typing import Dict, Iterable, List, Optional, Sequence, Tuple

import yaml

try:
    import questionary
    from questionary import Choice, Separator
except ImportError:
    questionary = None

try:
    from rich.console import Console
    from rich.panel import Panel
    from rich.table import Table
except ImportError:
    Console = None

console = Console() if Console else None

REPO_ROOT = Path(__file__).resolve().parent.parent
FILES_SUBDIR = Path("roles") / "osbuild" / "files"


# =============================================================================
# Component files
# =============================================================================


class TrackerError(Exception):
    """A user-facing error: bad target, unknown component, unusable file."""


def discover_targets(root: Path) -> Dict[str, Path]:
    """Return {"rocky/10/x86_64": <components dir>} for every components directory."""
    files = root / FILES_SUBDIR
    targets: Dict[str, Path] = {}
    for comp_dir in sorted(files.glob("*/*/*/components")):
        if comp_dir.is_dir():
            targets["/".join(comp_dir.relative_to(files).parts[:3])] = comp_dir
    return targets


def resolve_target(targets: Dict[str, Path], wanted: Optional[str]) -> str:
    """Return the key of the target named by --target.

    A prefix that matches one target (``rocky/10``) is accepted. Raises
    TrackerError, listing the available targets, when the value is missing,
    unknown or ambiguous.
    """
    available = ", ".join(targets) or "(none found)"
    if not wanted:
        raise TrackerError(f"--target is required. Available targets: {available}")
    wanted = wanted.strip("/")
    if wanted in targets:
        return wanted
    matches = [t for t in targets if t.startswith(wanted + "/")]
    if len(matches) == 1:
        return matches[0]
    problem = "is ambiguous" if matches else "is unknown"
    raise TrackerError(f"--target '{wanted}' {problem}. Available targets: {available}")


@dataclass
class Component:
    """One component file, as parsed."""

    name: str
    path: Path
    label: str
    packages: List[str]
    repo_urls: List[str]
    services: List[str]
    kernel_args: List[str]
    fragment: str


_ITEM = re.compile(r"""^(?P<indent>\s*)-\s+(?P<quote>["']?)(?P<name>[^"'#\s][^"'#]*?)(?P=quote)\s*(?:#.*)?$""")
_PACKAGES_KEY = re.compile(r"^packages:\s*(?:#.*)?$")
_NEEDS_QUOTES = re.compile(r"^[@*&!%`|>{}\[\],#?:-]")
_VALID_NAME = re.compile(r"^@?[A-Za-z0-9][A-Za-z0-9._+:@-]*$")


def validate_package_name(name: str) -> str:
    """Return ``name`` or raise TrackerError when it cannot be a package name."""
    if not _VALID_NAME.match(name):
        raise TrackerError(f"Invalid package name: {name!r}")
    return name


class ComponentStore:
    """Reads and edits the component files of one target directory."""

    def __init__(self, directory: Path):
        self.directory = Path(directory)

    def _path(self, name: str) -> Path:
        return self.directory / f"{name}.yml"

    def names(self) -> List[str]:
        return sorted(p.stem for p in self.directory.glob("*.yml"))

    def load(self, name: str) -> Component:
        path = self._path(name)
        if not path.is_file():
            raise TrackerError(
                f"Unknown component '{name}'. Available components: {', '.join(self.names())}"
            )
        data = yaml.safe_load(path.read_text()) or {}
        if not isinstance(data, dict) or not isinstance(data.get("packages"), list):
            raise TrackerError(f"{path}: no packages list")
        return Component(
            name=name,
            path=path,
            label=str(data.get("label", "")),
            packages=[str(p) for p in data["packages"]],
            repo_urls=[str(u) for u in data.get("repo_urls") or []],
            services=[str(s) for s in data.get("services") or []],
            kernel_args=[str(a) for a in data.get("kernel_args") or []],
            fragment=str(data.get("fragment") or ""),
        )

    def components(self) -> Dict[str, Component]:
        return {name: self.load(name) for name in self.names()}

    def find(self, package: str, exact: bool = True) -> List[str]:
        """Names of the components that contain ``package`` (substring when not exact)."""
        needle = package.lower()
        return [
            c.name
            for c in self.components().values()
            if any((p.lower() == needle) if exact else (needle in p.lower()) for p in c.packages)
        ]

    def conflicts(self, component: str, packages: Iterable[str]) -> Dict[str, List[str]]:
        """Packages that another component of this target already carries."""
        others = {n: c for n, c in self.components().items() if n != component}
        found: Dict[str, List[str]] = {}
        for pkg in packages:
            owners = [n for n, c in others.items() if pkg in c.packages]
            if owners:
                found[pkg] = owners
        return found

    # -- text editing ---------------------------------------------------------

    @staticmethod
    def _block(lines: List[str], path: Path) -> Tuple[int, List[int]]:
        """Return (index of the ``packages:`` line, indexes of its item lines)."""
        for start, line in enumerate(lines):
            if _PACKAGES_KEY.match(line):
                break
        else:
            raise TrackerError(f"{path}: packages must be a block list ('packages:' on its own line)")
        items: List[int] = []
        for idx in range(start + 1, len(lines)):
            line = lines[idx]
            if _ITEM.match(line):
                items.append(idx)
            elif line.strip() and not line.lstrip().startswith("#"):
                break
        if not items:
            raise TrackerError(f"{path}: packages list is empty or not a block list")
        return start, items

    def add(self, component: str, packages: Sequence[str]) -> Tuple[List[str], List[str]]:
        """Append packages to the component file.

        Returns (added, already present). Nothing is written when every
        package is already there.
        """
        comp = self.load(component)
        present = set(comp.packages)
        added: List[str] = []
        skipped: List[str] = []
        for pkg in dict.fromkeys(validate_package_name(p) for p in packages):
            (skipped if pkg in present else added).append(pkg)
        if not added:
            return added, skipped

        text = comp.path.read_text()
        lines = text.split("\n")
        _, items = self._block(lines, comp.path)
        last = _ITEM.match(lines[items[-1]])
        indent, quote = last.group("indent"), last.group("quote")
        new_lines = []
        for pkg in added:
            q = quote or ('"' if _NEEDS_QUOTES.match(pkg) else "")
            new_lines.append(f"{indent}- {q}{pkg}{q}")
        lines[items[-1] + 1:items[-1] + 1] = new_lines
        self._write(comp, "\n".join(lines), expect=present | set(added))
        return added, skipped

    def remove(self, component: str, packages: Sequence[str]) -> Tuple[List[str], List[str]]:
        """Remove packages from the component file.

        Returns (removed, absent). Raises TrackerError, writing nothing, when
        the removal would leave the component without packages.
        """
        comp = self.load(component)
        wanted = list(dict.fromkeys(packages))
        removed = [p for p in wanted if p in comp.packages]
        absent = [p for p in wanted if p not in comp.packages]
        if not removed:
            return removed, absent
        remaining = [p for p in comp.packages if p not in removed]
        if not remaining:
            raise TrackerError(
                f"Refusing to remove the last packages of '{component}': "
                "a component needs a non-empty packages list"
            )

        text = comp.path.read_text()
        lines = text.split("\n")
        _, items = self._block(lines, comp.path)
        drop = {i for i in items if _ITEM.match(lines[i]).group("name") in removed}
        kept = [line for i, line in enumerate(lines) if i not in drop]
        self._write(comp, "\n".join(kept), expect=set(remaining))
        return removed, absent

    @staticmethod
    def _write(comp: Component, text: str, expect: set) -> None:
        """Write ``text`` after checking it parses to the expected package set."""
        data = yaml.safe_load(text)
        if not isinstance(data, dict) or set(map(str, data.get("packages") or [])) != expect:
            raise TrackerError(f"{comp.path}: edit would corrupt the file; nothing written")
        comp.path.write_text(text)


# =============================================================================
# Repository availability verification
# =============================================================================

# Base repos of each target, as image-builder resolves them. The repos a
# component adds on top come from its repo_urls. Entries are (repo id, URL).
BASE_REPOS: Dict[str, List[Tuple[str, str]]] = {
    "rocky/10": [
        ("rocky-baseos", "https://dl.rockylinux.org/pub/rocky/10/BaseOS/x86_64/os/"),
        ("rocky-appstream", "https://dl.rockylinux.org/pub/rocky/10/AppStream/x86_64/os/"),
        ("copr-syncopated", "https://download.copr.fedorainfracloud.org/results/b08x/syncopated/epel-10-x86_64/"),
    ],
    "rocky/9": [
        ("rocky-baseos", "https://dl.rockylinux.org/pub/rocky/9/BaseOS/x86_64/os/"),
        ("rocky-appstream", "https://dl.rockylinux.org/pub/rocky/9/AppStream/x86_64/os/"),
    ],
    "almalinux/10": [
        ("almalinux-baseos", "https://repo.almalinux.org/almalinux/10/BaseOS/x86_64/os/"),
        ("almalinux-appstream", "https://repo.almalinux.org/almalinux/10/AppStream/x86_64/os/"),
        ("almalinux-crb", "https://repo.almalinux.org/almalinux/10/CRB/x86_64/os/"),
        ("copr-syncopated", "https://download.copr.fedorainfracloud.org/results/b08x/syncopated/epel-10-x86_64/"),
    ],
    "fedora/43": [
        ("fedora", "https://dl.fedoraproject.org/pub/fedora/linux/releases/43/Everything/x86_64/os/"),
        ("fedora-updates", "https://dl.fedoraproject.org/pub/fedora/linux/updates/43/Everything/x86_64/"),
        ("copr-syncopated", "https://download.copr.fedorainfracloud.org/results/b08x/syncopated/fedora-43-x86_64/"),
    ],
}

REPO_ID_PREFIX = "ptv-"

# Value reported for names the verifier does not look up.
SKIPPED_GROUP = "skipped: comps group"


def repo_profile(target: str, repo_urls: Iterable[str] = ()) -> List[Tuple[str, str]]:
    """Base repos of ``target`` (``rocky/10/x86_64`` or ``rocky/10``) plus extra URLs.

    Extra URLs get ids from their host and path. Metalinks cannot be passed
    to ``--repofrompath`` as base URLs and are left out.
    """
    key = "/".join(target.split("/")[:2])
    if key not in BASE_REPOS:
        raise ValueError(f"No repository profile for target '{target}'")
    profile = list(BASE_REPOS[key])
    seen = {url.rstrip("/") for _, url in profile}
    for url in repo_urls:
        if "metalink" in url or url.rstrip("/") in seen:
            continue
        seen.add(url.rstrip("/"))
        slug = re.sub(r"[^A-Za-z0-9]+", "-", re.sub(r"^\w+://", "", url)).strip("-")[:48]
        profile.append((f"x-{slug}", url))
    return profile


class RepoVerifier:
    """Check that package names exist in the repos a target's builds use.

    One ``dnf repoquery`` call (argument list, no shell) resolves every
    requested name; results are cached per name. Names that look like options
    are rejected up front because dnf5 does not accept a ``--`` separator.
    """

    def __init__(
        self,
        target: str,
        arch: str = "x86_64",
        dnf: str = "dnf",
        repo_urls: Iterable[str] = (),
    ):
        self.target = target
        self.arch = arch
        self.dnf = dnf
        self.profile = repo_profile(target, repo_urls)
        self.cache: Dict[str, Optional[str]] = {}

    @staticmethod
    def dnf_available(dnf: str = "dnf") -> bool:
        return shutil.which(dnf) is not None

    def _command(self, names: List[str]) -> List[str]:
        cmd = [self.dnf, "repoquery", "--quiet", f"--forcearch={self.arch}"]
        for repo_id, url in self.profile:
            # The prefix keeps ids from colliding with repos configured on the
            # host (e.g. "fedora"); --repo then limits the query to these.
            cmd += [f"--repofrompath={REPO_ID_PREFIX}{repo_id},{url}", f"--repo={REPO_ID_PREFIX}{repo_id}"]
        cmd += ["--latest-limit=1", "--qf", "%{name} %{repoid}\n", *names]
        return cmd

    def check(self, packages: List[str]) -> Dict[str, Optional[str]]:
        """Return {package: repo id providing it, or None when unavailable}.

        Comps groups (``@name``) are reported as SKIPPED_GROUP. Raises
        RuntimeError when dnf fails, so a network error is not mistaken for
        a missing package.
        """
        result: Dict[str, Optional[str]] = {}
        todo: List[str] = []
        for pkg in packages:
            if pkg in self.cache:
                result[pkg] = self.cache[pkg]
            elif pkg.startswith("@"):
                result[pkg] = SKIPPED_GROUP
            elif not pkg or pkg.startswith("-") or any(c.isspace() for c in pkg):
                raise ValueError(f"Invalid package name: {pkg!r}")
            else:
                todo.append(pkg)

        if todo:
            proc = subprocess.run(self._command(todo), capture_output=True, text=True, check=False)
            if proc.returncode != 0:
                raise RuntimeError(
                    f"dnf repoquery failed for {self.target} (rc={proc.returncode}): "
                    f"{proc.stderr.strip()[-300:]}"
                )
            found: Dict[str, str] = {}
            for line in proc.stdout.splitlines():
                parts = line.split()
                if len(parts) == 2:
                    found.setdefault(parts[0], parts[1].removeprefix(REPO_ID_PREFIX))
            for pkg in todo:
                self.cache[pkg] = found.get(pkg)
                result[pkg] = self.cache[pkg]
        return result


def verifier_for(store: ComponentStore, target: str) -> RepoVerifier:
    """A RepoVerifier over the target's base repos and every component's repo_urls."""
    urls = [u for c in store.components().values() for u in c.repo_urls]
    return RepoVerifier(target, repo_urls=urls)


# =============================================================================
# CLI commands
# =============================================================================


def _say(kind: str, msg: str):
    """Print a status line: kind is ok, warn or err."""
    styles = {"ok": ("✓", "bold green"), "warn": ("!", "yellow"), "err": ("✗", "bold red")}
    mark, style = styles[kind]
    if console:
        console.print(f"[{style}]{mark}[/{style}] {msg}", highlight=False, soft_wrap=True)
    else:
        print(f"{mark} {msg}")


def parse_packages(raw: Sequence[str]) -> List[str]:
    """Split names given as separate arguments or comma-separated lists."""
    names: List[str] = []
    for item in raw:
        names += [p for p in re.split(r"[,\s]+", item) if p]
    return list(dict.fromkeys(names))


def cli_list(store: ComponentStore, target: str) -> int:
    components = store.components()
    width = max((len(n) for n in components), default=0)
    print(f"{target}: {len(components)} components, {sum(len(c.packages) for c in components.values())} packages")
    for name, comp in components.items():
        print(f"  {name:<{width}}  {len(comp.packages):>4}  {comp.label}")
    return 0


def cli_search(stores: Dict[str, ComponentStore], query: str) -> int:
    hits = 0
    for target, store in stores.items():
        for comp in store.components().values():
            for pkg in comp.packages:
                if query.lower() in pkg.lower():
                    print(f"{target}/{comp.name}: {pkg}")
                    hits += 1
    if not hits:
        _say("warn", f"No package matching '{query}'")
        return 1
    return 0


def cli_add(
    store: ComponentStore,
    target: str,
    component: str,
    packages: Sequence[str],
    verify: bool = False,
    force: bool = False,
) -> int:
    """Add packages to a component. Returns 0 when all were added or present.

    1 when some were refused (not in the repos, or in another component
    without --force); 2 when the command could not run.
    """
    names = [validate_package_name(p) for p in packages]
    store.load(component)

    availability: Dict[str, Optional[str]] = {}
    if verify:
        if not RepoVerifier.dnf_available():
            _say("err", "dnf not found; cannot verify (drop --verify to add unverified)")
            return 2
        try:
            availability = verifier_for(store, target).check(names)
        except RuntimeError as exc:
            _say("err", f"{exc}; nothing added")
            return 2

    refused = 0
    to_add: List[str] = []
    here = set(store.load(component).packages)
    conflicts = store.conflicts(component, names)
    for name in names:
        if name in here:
            _say("warn", f"'{name}' is already in {component}")
        elif verify and availability.get(name, SKIPPED_GROUP) is None:
            _say("warn", f"'{name}' is not in any {target} repo; not added")
            refused += 1
        elif name in conflicts and not force:
            _say(
                "warn",
                f"'{name}' is already in {', '.join(conflicts[name])}; not added (use --force to add it anyway)",
            )
            refused += 1
        else:
            if name in conflicts:
                _say("warn", f"'{name}' is also in {', '.join(conflicts[name])}")
            to_add.append(name)

    added, _ = store.add(component, to_add)
    for name in added:
        repo = availability.get(name)
        where = f" [{repo}]" if repo and repo != SKIPPED_GROUP else ""
        _say("ok", f"Added '{name}' to {target}/{component}{where}")
    return 1 if refused else 0


def cli_remove(store: ComponentStore, target: str, component: str, packages: Sequence[str]) -> int:
    removed, absent = store.remove(component, [validate_package_name(p) for p in packages])
    for name in removed:
        _say("ok", f"Removed '{name}' from {target}/{component}")
    for name in absent:
        _say("warn", f"'{name}' is not in {component}")
    return 0 if removed or not absent else 1


def cli_verify(store: ComponentStore, target: str, component: Optional[str] = None) -> int:
    """Check a component (or the whole target) against the target's repos.

    Returns 0 when every name is available, 1 when some are missing, 2 when
    verification could not run.
    """
    if not RepoVerifier.dnf_available():
        _say("err", "dnf not found; cannot verify availability")
        return 2
    components = {component: store.load(component)} if component else store.components()
    locations: Dict[str, List[str]] = {}
    for comp in components.values():
        for pkg in comp.packages:
            locations.setdefault(pkg, []).append(comp.name)
    try:
        availability = verifier_for(store, target).check(list(locations))
    except RuntimeError as exc:
        _say("err", str(exc))
        return 2
    missing = sorted(n for n, repo in availability.items() if repo is None)
    checked = sum(1 for r in availability.values() if r != SKIPPED_GROUP)
    _say("ok" if not missing else "warn", f"{target}: {checked - len(missing)}/{checked} available")
    for name in missing:
        print(f"    missing: {name}  ({', '.join(locations[name])})")
    return 1 if missing else 0


# =============================================================================
# Playbook component selection
# =============================================================================

_COMPONENTS_KEY = re.compile(r"^(?P<indent>\s*)osbuild_blueprint_components:\s*(?:#.*)?$")
_DISTRO_LINE = re.compile(r"""^\s*osbuild_distro:\s*["']?(?P<distro>[a-z]+)-(?P<ver>\d+)""", re.M)
_ARCH_LINE = re.compile(r"""^\s*osbuild_arch:\s*["']?(?P<arch>[\w]+)""", re.M)
_NAME_ITEM = re.compile(r"^(?P<indent>\s*)-\s+(?P<name>[A-Za-z0-9][\w.-]*)\s*(?:#.*)?$")


class PlaybookSelection:
    """The ``osbuild_blueprint_components`` block list of one playbook file.

    Edits touch only that list's item lines; everything else stays byte for byte.
    """

    def __init__(self, path: Path):
        self.path = Path(path)
        self.lines = self.path.read_text().split("\n")
        self._start = next((i for i, l in enumerate(self.lines) if _COMPONENTS_KEY.match(l)), None)
        if self._start is None:
            raise TrackerError(f"{self.path}: no 'osbuild_blueprint_components:' block list found")
        self._items = self._scan()
        if not self._items:
            raise TrackerError(f"{self.path}: osbuild_blueprint_components is not a block list of names")

    def _scan(self) -> List[int]:
        items: List[int] = []
        for idx in range(self._start + 1, len(self.lines)):
            line = self.lines[idx]
            if _NAME_ITEM.match(line):
                items.append(idx)
            elif line.strip() and not line.lstrip().startswith("#"):
                break
        return items

    @property
    def components(self) -> List[str]:
        return [_NAME_ITEM.match(self.lines[i]).group("name") for i in self._items]

    def target(self) -> Optional[str]:
        """``<distro>/<major>/<arch>`` from the playbook's osbuild_distro, if it sets one."""
        text = "\n".join(self.lines)
        m = _DISTRO_LINE.search(text)
        if not m:
            return None
        arch = _ARCH_LINE.search(text)
        return f"{m['distro']}/{m['ver']}/{arch['arch'] if arch else 'x86_64'}"

    def add(self, names: Sequence[str], after: Optional[str] = None) -> List[str]:
        """Append names (or insert after ``after``). Returns the names actually added."""
        new = [n for n in dict.fromkeys(names) if n not in self.components]
        if not new:
            return new
        at = self._items[-1]
        if after:
            if after not in self.components:
                raise TrackerError(f"--after '{after}' is not selected in {self.path.name}")
            at = self._items[self.components.index(after)]
        indent = _NAME_ITEM.match(self.lines[at]).group("indent")
        self.lines[at + 1:at + 1] = [f"{indent}- {n}" for n in new]
        self._items = self._scan()
        return new

    def remove(self, names: Sequence[str]) -> List[str]:
        """Remove names. Refuses to empty the list. Returns the names removed."""
        gone = [n for n in dict.fromkeys(names) if n in self.components]
        if gone and len(gone) == len(self.components):
            raise TrackerError("Refusing to remove every component from the playbook")
        drop = {i for i in self._items if _NAME_ITEM.match(self.lines[i]).group("name") in gone}
        self.lines = [l for i, l in enumerate(self.lines) if i not in drop]
        self._start = next(i for i, l in enumerate(self.lines) if _COMPONENTS_KEY.match(l))
        self._items = self._scan()
        return gone

    def save(self) -> None:
        text = "\n".join(self.lines)
        reread = [m.group("name") for l in text.split("\n")[self._start + 1:] if (m := _NAME_ITEM.match(l))]
        if reread[: len(self.components)] != self.components:
            raise TrackerError(f"{self.path}: edit would corrupt the file; nothing written")
        self.path.write_text(text)


def _playbook_store(targets: Dict[str, Path], pb: PlaybookSelection, wanted: Optional[str]) -> Tuple[str, ComponentStore]:
    key = resolve_target(targets, wanted or pb.target())
    return key, ComponentStore(targets[key])


def cli_playbook(
    targets: Dict[str, Path],
    path: Path,
    action: str,
    names: Sequence[str],
    target: Optional[str] = None,
    after: Optional[str] = None,
) -> int:
    """list/add/remove components in a playbook. add checks the names exist for the target."""
    pb = PlaybookSelection(path)
    key, store = _playbook_store(targets, pb, target)
    available = store.names()
    if action == "list":
        print(f"{path} ({key})")
        for name in available:
            comp = store.load(name)
            mark = "x" if name in pb.components else " "
            print(f"  [{mark}] {name:<18} {len(comp.packages):>4}  {comp.label}")
        unknown = [c for c in pb.components if c not in available]
        for name in unknown:
            _say("warn", f"'{name}' is selected but has no component file in {key}")
        return 1 if unknown else 0
    names = parse_packages(names)
    if action == "add":
        bad = [n for n in names if n not in available]
        if bad:
            raise TrackerError(f"No such component for {key}: {', '.join(bad)}. Available: {', '.join(available)}")
        added = pb.add(names, after)
        for n in names:
            _say("ok" if n in added else "warn", f"{'Added' if n in added else 'Already selected:'} '{n}'")
    else:
        removed = pb.remove(names)
        for n in names:
            _say("ok" if n in removed else "warn", f"{'Removed' if n in removed else 'Not selected:'} '{n}'")
    pb.save()
    return 0


# =============================================================================
# TUI
# =============================================================================


# questionary replaces Choice(value=None) with the title, so "Back" and "Exit"
# need their own sentinel values.
_BACK = "\0back"
_EXIT = "\0exit"


def show_details(comp: Component) -> None:
    """Print a component's label, repo_urls, services, kernel_args and fragment."""
    rows = [
        ("label", comp.label),
        ("repo_urls", "\n".join(comp.repo_urls) or "-"),
        ("services", ", ".join(comp.services) or "-"),
        ("kernel_args", " ".join(comp.kernel_args) or "-"),
        ("fragment", comp.fragment or "-"),
    ]
    if console:
        table = Table(show_header=False, box=None)
        for key, value in rows:
            table.add_row(f"[bold]{key}[/bold]", value)
        console.print(Panel(table, title=f"{comp.name} ({len(comp.packages)} packages)", expand=False))
    else:
        print(f"{comp.name} ({len(comp.packages)} packages)")
        for key, value in rows:
            print(f"  {key}: {value}")


def tui_edit_packages(store: ComponentStore, target: str, name: str) -> None:
    """Checkbox over the component's packages; unchecked ones are removed after confirmation."""
    comp = store.load(name)
    kept = questionary.checkbox(
        f"{name}: uncheck the packages to remove",
        choices=[Choice(p, checked=True) for p in comp.packages],
    ).ask()
    if kept is None:
        return
    removals = [p for p in comp.packages if p not in kept]
    if not removals:
        _say("ok", "No changes")
        return
    if not kept:
        _say("err", "A component needs at least one package; nothing removed")
        return
    if not questionary.confirm(
        f"Remove {len(removals)} package(s) from {name}?\n  " + "\n  ".join(removals), default=False
    ).ask():
        return
    cli_remove(store, target, name, removals)


def tui_add_packages(store: ComponentStore, target: str, name: str) -> None:
    """Prompt for names; optional verify; duplicates elsewhere need confirmation."""
    raw = questionary.text("Packages to add (space or comma separated):").ask()
    names = parse_packages([raw or ""])
    if not names:
        return
    try:
        for n in names:
            validate_package_name(n)
    except TrackerError as exc:
        _say("err", str(exc))
        return
    verify = RepoVerifier.dnf_available() and questionary.confirm(
        "Verify against the target's repos?", default=True
    ).ask()
    force = False
    conflicts = store.conflicts(name, names)
    if conflicts:
        listing = "\n  ".join(f"{p}: also in {', '.join(c)}" for p, c in conflicts.items())
        force = bool(questionary.confirm(f"Already in another component:\n  {listing}\nAdd anyway?", default=False).ask())
    cli_add(store, target, name, names, verify=bool(verify), force=force)


def tui_component_menu(store: ComponentStore, target: str, name: str) -> None:
    while True:
        comp = store.load(name)
        action = questionary.select(
            f"{target}/{name} - {comp.label} ({len(comp.packages)} packages)",
            choices=["Edit packages", "Add packages", "Show details", "Back"],
        ).ask()
        if action is None or action == "Back":
            return
        if action == "Edit packages":
            tui_edit_packages(store, target, name)
        elif action == "Add packages":
            tui_add_packages(store, target, name)
        elif action == "Show details":
            show_details(comp)


def tui_components(store: ComponentStore, target: str) -> None:
    while True:
        components = store.components()
        choices = [Choice(f"{n}  {c.label} ({len(c.packages)})", value=n) for n, c in components.items()]
        choices += [Separator(), Choice("Back", value=_BACK)]
        name = questionary.select(f"{target}: choose a component", choices=choices).ask()
        if name is None or name == _BACK:
            return
        tui_component_menu(store, target, name)


def tui_playbook(targets: Dict[str, Path], root: Path) -> None:
    """Pick a playbook, then check/uncheck the components it builds from."""
    playbooks = sorted(
        p for p in (root / "playbooks").glob("*.yml")
        if "osbuild_blueprint_components:" in p.read_text() and not p.name.endswith("osbuild.yml")
    )
    if not playbooks:
        _say("warn", "No playbook with a component list found")
        return
    choices = [Choice(p.name, value=str(p)) for p in playbooks] + [Separator(), Choice("Back", value=_BACK)]
    picked = questionary.select("Choose a playbook:", choices=choices).ask()
    if picked is None or picked == _BACK:
        return
    try:
        pb = PlaybookSelection(Path(picked))
        key, store = _playbook_store(targets, pb, None)
    except TrackerError as exc:
        _say("err", str(exc))
        return
    selected = pb.components
    names = store.names()
    ordered = selected + [n for n in names if n not in selected]
    answer = questionary.checkbox(
        f"{Path(picked).name} ({key}): check the components to build from",
        choices=[
            Choice(f"{n}  {store.load(n).label}" if n in names else f"{n}  (no component file)", value=n, checked=n in selected)
            for n in ordered
        ],
    ).ask()
    if answer is None:
        return
    drop = [n for n in selected if n not in answer]
    add = [n for n in answer if n not in selected]
    if not (drop or add):
        _say("ok", "No changes")
        return
    summary = "\n  ".join([f"+ {n}" for n in add] + [f"- {n}" for n in drop])
    if not questionary.confirm(f"Apply to {Path(picked).name}?\n  {summary}", default=True).ask():
        return
    try:
        pb.add(add)
        pb.remove(drop)
        pb.save()
    except TrackerError as exc:
        _say("err", str(exc))
        return
    _say("ok", f"Updated {Path(picked).name}")


def tui_main_loop(stores: Dict[str, ComponentStore], root: Path = REPO_ROOT) -> None:
    if not questionary:
        print("Error: questionary library not found. Run 'pip install questionary rich'.")
        return
    if console:
        console.print(Panel("[bold cyan]osbuild package tracker[/bold cyan]", style="bold blue", expand=False))
    targets = {t: st.directory for t, st in stores.items()}
    while True:
        what = questionary.select(
            "What would you like to edit?",
            choices=["Packages in a component", "Components in a playbook", "Exit"],
        ).ask()
        if what is None or what == "Exit":
            return
        if what == "Components in a playbook":
            tui_playbook(targets, root)
            continue
        if len(stores) == 1:
            target = next(iter(stores))
        else:
            target = questionary.select(
                "Select target:", choices=[*stores, Separator(), Choice("Exit", value=_EXIT)]
            ).ask()
            if target is None or target == _EXIT:
                continue
        tui_components(stores[target], target)


# =============================================================================
# Entry point
# =============================================================================


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        description="List, search, add and remove packages in the osbuild role's component files",
    )
    parser.add_argument("--repo-root", type=Path, default=REPO_ROOT, help="Path to the repository root")
    sub = parser.add_subparsers(dest="command")

    def target_arg(p, required=True):
        p.add_argument("--target", help="<distro>/<major>/<arch>, e.g. rocky/10/x86_64")

    p = sub.add_parser("list", help="List a target's components with label and package count")
    target_arg(p)
    p = sub.add_parser("search", help="Find the components that contain a package")
    p.add_argument("name", help="Package name or substring")
    target_arg(p)
    p = sub.add_parser("add", help="Append packages to a component")
    target_arg(p)
    p.add_argument("component")
    p.add_argument("packages", nargs="+", metavar="PKG")
    p.add_argument("--verify", action="store_true", help="Check each package against the target's repos first")
    p.add_argument("--force", action="store_true", help="Add packages that another component already has")
    p = sub.add_parser("remove", help="Remove packages from a component")
    target_arg(p)
    p.add_argument("component")
    p.add_argument("packages", nargs="+", metavar="PKG")
    p = sub.add_parser("verify", help="Check a component or the whole target against the repos")
    target_arg(p)
    p.add_argument("component", nargs="?")
    p = sub.add_parser("playbook", help="List, add or remove the components a playbook builds from")
    p.add_argument("path", type=Path, help="Playbook file, e.g. playbooks/osbuild-rocky-iso-components.yml")
    p.add_argument("action", choices=["list", "add", "remove"])
    p.add_argument("components", nargs="*", metavar="COMPONENT")
    p.add_argument("--target", help="Override the target derived from the playbook's osbuild_distro")
    p.add_argument("--after", help="With add: insert after this selected component")
    sub.add_parser("tui", help="Launch the interactive menu")
    return parser


def main(argv: Optional[Sequence[str]] = None) -> int:
    parser = build_parser()
    args = parser.parse_args(argv)
    targets = discover_targets(args.repo_root)
    stores = {t: ComponentStore(d) for t, d in targets.items()}

    try:
        if args.command in (None, "tui"):
            if not sys.stdin.isatty():
                parser.print_help()
                return 2
            tui_main_loop(stores, args.repo_root)
            return 0
        if args.command == "search":
            if args.target:
                key = resolve_target(targets, args.target)
                stores = {key: stores[key]}
            return cli_search(stores, args.name)

        if args.command == "playbook":
            if args.action != "list" and not args.components:
                parser.error(f"playbook {args.action} needs at least one COMPONENT")
            return cli_playbook(targets, args.path, args.action, args.components, args.target, args.after)

        target = resolve_target(targets, args.target)
        store = stores[target]
        if args.command == "list":
            return cli_list(store, target)
        if args.command == "add":
            return cli_add(store, target, args.component, parse_packages(args.packages), args.verify, args.force)
        if args.command == "remove":
            return cli_remove(store, target, args.component, parse_packages(args.packages))
        if args.command == "verify":
            return cli_verify(store, target, args.component)
    except TrackerError as exc:
        _say("err", str(exc))
        return 2
    return 0


if __name__ == "__main__":
    sys.exit(main())
