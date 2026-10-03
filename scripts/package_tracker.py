#!/usr/bin/env python3
"""osbuild Package Tracker & Taxonomy TUI.

Interactive and CLI tool to:
1. Maintain per-distribution package taxonomies (add/remove packages, groups, flatpaks)
   in vars/packages/{Fedora,AlmaLinux,Rocky}.yml using ruamel.yaml to preserve formatting.
2. Interactively select packages, components, and groups for image builds and export
   build selection manifests (YAML, JSON, TOML) for osbuild image generation.
"""

from __future__ import annotations

import argparse
import datetime
import json
import os
import sys
from pathlib import Path
from typing import Any, Dict, List, Optional, Set, Tuple

try:
    import questionary
    from questionary import Choice, Separator
except ImportError:
    questionary = None

try:
    from rich.console import Console
    from rich.panel import Panel
    from rich.table import Table
    from rich import print as rprint
except ImportError:
    Console = None
    rprint = print

from ruamel.yaml import YAML
from ruamel.yaml.comments import CommentedMap, CommentedSeq

DISTROS = ["Fedora", "AlmaLinux", "Rocky"]
DEFAULT_DISTRO = "Fedora"

console = Console() if Console else None


def get_yaml() -> YAML:
    """Return a configured ruamel.yaml round-trip handler."""
    yaml = YAML()
    yaml.preserve_quotes = True
    yaml.indent(mapping=2, sequence=4, offset=2)
    return yaml


class TaxonomyManager:
    """Manages loading, updating, and exporting package taxonomies."""

    def __init__(self, repo_root: Optional[Path] = None):
        if repo_root is None:
            # Default to repo root relative to scripts/
            self.repo_root = Path(__file__).resolve().parent.parent
        else:
            self.repo_root = Path(repo_root)

        self.taxonomy_dir = self.repo_root / "vars" / "packages"
        self.builds_dir = self.repo_root / "build-selections"
        self.yaml = get_yaml()
        self.distro_data: Dict[str, CommentedMap] = {}
        self.distributions_map: Dict[str, Any] = {}
        self.load_all()

    def load_all(self):
        """Load all distribution files and cross-distribution mappings."""
        dist_map_path = self.taxonomy_dir / "00-distributions.yml"
        if dist_map_path.exists():
            with open(dist_map_path, "r", encoding="utf-8") as f:
                self.distributions_map = self.yaml.load(f) or {}

        for distro in DISTROS:
            distro_file = self.taxonomy_dir / f"{distro}.yml"
            if distro_file.exists():
                with open(distro_file, "r", encoding="utf-8") as f:
                    self.distro_data[distro] = self.yaml.load(f) or CommentedMap()
            else:
                self.distro_data[distro] = CommentedMap()

    def save_distro(self, distro: str):
        """Save a specific distribution taxonomy back to disk preserving formatting."""
        distro_file = self.taxonomy_dir / f"{distro}.yml"
        self.taxonomy_dir.mkdir(parents=True, exist_ok=True)
        with open(distro_file, "w", encoding="utf-8") as f:
            self.yaml.dump(self.distro_data[distro], f)

    def save_all_distros(self):
        """Save all loaded distributions back to disk."""
        for distro in DISTROS:
            if distro in self.distro_data:
                self.save_distro(distro)

    def get_categories(self, distro: str, section: str = "system_packages") -> List[str]:
        """Return category names under a given section."""
        data = self.distro_data.get(distro, {})
        section_data = data.get(section, {})
        if isinstance(section_data, dict):
            return list(section_data.keys())
        return []

    def get_subcategories(
        self, distro: str, category: str, section: str = "system_packages"
    ) -> List[str]:
        """Return subcategory names under a given category."""
        data = self.distro_data.get(distro, {})
        cat_data = data.get(section, {}).get(category, {})
        if isinstance(cat_data, dict):
            return list(cat_data.keys())
        return []

    def get_packages(
        self, distro: str, category: str, subcategory: str, section: str = "system_packages"
    ) -> List[str]:
        """Return package list for a given subcategory."""
        data = self.distro_data.get(distro, {})
        packages = data.get(section, {}).get(category, {}).get(subcategory, [])
        if isinstance(packages, list):
            return list(packages)
        return []

    def find_package(self, package_name: str) -> List[Dict[str, str]]:
        """Search for a package across all distributions and sections."""
        results = []
        name_lower = package_name.lower()
        for distro, data in self.distro_data.items():
            for section in ["system_packages", "system_groups", "system_flatpaks"]:
                sec_dict = data.get(section, {})
                if not isinstance(sec_dict, dict):
                    continue
                for cat, subcats in sec_dict.items():
                    if not isinstance(subcats, dict):
                        continue
                    for subcat, pkgs in subcats.items():
                        if isinstance(pkgs, list):
                            for p in pkgs:
                                if name_lower in str(p).lower():
                                    results.append(
                                        {
                                            "distro": distro,
                                            "section": section,
                                            "category": cat,
                                            "subcategory": subcat,
                                            "package": str(p),
                                        }
                                    )
        return results

    def add_package(
        self,
        distro: str,
        category: str,
        subcategory: str,
        package: str,
        section: str = "system_packages",
    ) -> bool:
        """Add a package to a distribution taxonomy."""
        distros_to_update = DISTROS if distro == "All" else [distro]
        added_any = False

        for d in distros_to_update:
            data = self.distro_data.get(d)
            if data is None:
                continue

            if section not in data:
                data[section] = CommentedMap()
            if category not in data[section]:
                data[section][category] = CommentedMap()
            if subcategory not in data[section][category]:
                data[section][category][subcategory] = CommentedSeq()

            pkg_list = data[section][category][subcategory]

            # Check mapping if adding across distros
            target_pkg = package
            if distro == "All":
                map_key = d.lower()
                mappings = self.distributions_map.get("package_mappings", {})
                if package in mappings and map_key in mappings[package]:
                    target_pkg = mappings[package][map_key]

            if target_pkg not in pkg_list:
                pkg_list.append(target_pkg)
                self.save_distro(d)
                added_any = True

        return added_any

    def remove_package(
        self,
        distro: str,
        category: str,
        subcategory: str,
        package: str,
        section: str = "system_packages",
    ) -> bool:
        """Remove a package from a distribution taxonomy."""
        distros_to_update = DISTROS if distro == "All" else [distro]
        removed_any = False

        for d in distros_to_update:
            data = self.distro_data.get(d)
            if not data or section not in data:
                continue
            cat_data = data[section].get(category)
            if not cat_data or subcategory not in cat_data:
                continue

            pkg_list = cat_data[subcategory]
            if isinstance(pkg_list, list):
                # Look for exact match or mapped match
                to_remove = None
                for p in pkg_list:
                    if p == package:
                        to_remove = p
                        break
                if to_remove:
                    pkg_list.remove(to_remove)
                    self.save_distro(d)
                    removed_any = True

        return removed_any

    def generate_build_manifest(
        self,
        distro: str,
        blueprint: str,
        selected_subcategories: List[Tuple[str, str]],
        extra_packages: Optional[List[str]] = None,
        custom_package_pins: Optional[Dict[str, str]] = None,
    ) -> Dict[str, Any]:
        """Aggregate packages for selected subcategories and create a build manifest."""
        data = self.distro_data.get(distro, {})
        sys_pkgs = data.get("system_packages", {})
        sys_groups = data.get("system_groups", {})
        sys_flatpaks = data.get("system_flatpaks", {})

        packages: Set[str] = set()
        groups: Set[str] = set()
        flatpaks: Set[str] = set()

        for cat, subcat in selected_subcategories:
            # Check system_packages
            if cat in sys_pkgs and subcat in sys_pkgs[cat]:
                packages.update(sys_pkgs[cat][subcat])
            # Check system_groups
            if cat in sys_groups and subcat in sys_groups[cat]:
                groups.update(sys_groups[cat][subcat])
            # Check system_flatpaks
            if cat in sys_flatpaks and subcat in sys_flatpaks[cat]:
                flatpaks.update(sys_flatpaks[cat][subcat])

        if extra_packages:
            packages.update(extra_packages)

        sorted_packages = sorted(packages)
        sorted_groups = sorted(groups)
        sorted_flatpaks = sorted(flatpaks)

        manifest = {
            "metadata": {
                "generated_at": datetime.datetime.now(datetime.timezone.utc).isoformat(),
                "distro": distro,
                "blueprint": blueprint,
                "total_packages": len(sorted_packages),
                "total_groups": len(sorted_groups),
                "total_flatpaks": len(sorted_flatpaks),
                "selected_components": [f"{cat}/{subcat}" for cat, subcat in selected_subcategories],
            },
            "build_specification": {
                "distro": distro,
                "blueprint_name": blueprint,
                "packages": sorted_packages,
                "groups": sorted_groups,
                "flatpaks": sorted_flatpaks,
                "package_pins": custom_package_pins or {},
            },
            "ansible_vars": {
                "osbuild_distro": f"{distro.lower()}-43" if distro == "Fedora" else f"{distro.lower()}-10.2",
                "osbuild_blueprint_name": blueprint,
                "osbuild_extra_packages": sorted_packages,
            },
        }

        return manifest

    def export_manifest(
        self,
        manifest: Dict[str, Any],
        output_path: Optional[Path] = None,
        export_format: str = "yaml",
    ) -> Path:
        """Export manifest to disk in YAML, JSON, or TOML format."""
        if output_path is None:
            distro = manifest["metadata"]["distro"]
            blueprint = manifest["metadata"]["blueprint"]
            timestamp = datetime.datetime.now().strftime("%Y%m%d_%H%M%S")
            self.builds_dir.mkdir(parents=True, exist_ok=True)
            output_path = self.builds_dir / f"build-{distro.lower()}-{blueprint}-{timestamp}.{export_format}"
        else:
            output_path = Path(output_path)
            output_path.parent.mkdir(parents=True, exist_ok=True)

        if export_format == "json":
            with open(output_path, "w", encoding="utf-8") as f:
                json.dump(manifest, f, indent=2)
        elif export_format == "toml":
            with open(output_path, "w", encoding="utf-8") as f:
                f.write(f'name = "{manifest["metadata"]["blueprint"]}"\n')
                f.write(f'description = "OSBuild package selection for {manifest["metadata"]["distro"]}"\n')
                f.write('version = "1.0.0"\n\n')
                for pkg in manifest["build_specification"]["packages"]:
                    f.write('[[packages]]\n')
                    f.write(f'name = "{pkg}"\n')
                    pin = manifest["build_specification"]["package_pins"].get(pkg, "*")
                    f.write(f'version = "{pin}"\n\n')
        else:  # default yaml
            with open(output_path, "w", encoding="utf-8") as f:
                f.write("---\n# OSBuild Package Selection Manifest\n")
                self.yaml.dump(manifest, f)

        return output_path


# =============================================================================
# CLI Non-Interactive Subcommands
# =============================================================================


def cli_list(manager: TaxonomyManager, distro: str):
    """List taxonomy hierarchy and package counts for a distribution."""
    if console:
        table = Table(title=f"Package Taxonomy for {distro}")
        table.add_column("Category", style="cyan", no_wrap=True)
        table.add_column("Subcategory", style="magenta")
        table.add_column("Package Count", justify="right", style="green")
        table.add_column("Sample Packages", style="dim")

        total_pkgs = 0
        for cat in manager.get_categories(distro):
            for subcat in manager.get_subcategories(distro, cat):
                pkgs = manager.get_packages(distro, cat, subcat)
                count = len(pkgs)
                total_pkgs += count
                sample = ", ".join(pkgs[:4]) + ("..." if len(pkgs) > 4 else "")
                table.add_row(cat, subcat, str(count), sample)

        console.print(table)
        console.print(f"[bold green]Total packages in {distro}: {total_pkgs}[/bold green]\n")
    else:
        for cat in manager.get_categories(distro):
            print(f"[{cat}]")
            for subcat in manager.get_subcategories(distro, cat):
                pkgs = manager.get_packages(distro, cat, subcat)
                print(f"  - {subcat}: {len(pkgs)} pkgs ({', '.join(pkgs[:3])}...)")


def cli_search(manager: TaxonomyManager, query: str):
    """Search for packages across distributions."""
    results = manager.find_package(query)
    if not results:
        print(f"No packages found matching '{query}'.")
        return

    if console:
        table = Table(title=f"Search Results for '{query}'")
        table.add_column("Distro", style="cyan")
        table.add_column("Section", style="yellow")
        table.add_column("Category", style="blue")
        table.add_column("Subcategory", style="magenta")
        table.add_column("Package", style="green bold")

        for r in results:
            table.add_row(r["distro"], r["section"], r["category"], r["subcategory"], r["package"])
        console.print(table)
    else:
        for r in results:
            print(f"[{r['distro']}] {r['category']}/{r['subcategory']} -> {r['package']}")


def cli_add_package(
    manager: TaxonomyManager,
    distro: str,
    category: str,
    subcategory: str,
    package: str,
    section: str = "system_packages",
):
    """Add a package via CLI."""
    packages = [p.strip() for p in package.split(",") if p.strip()]
    for p in packages:
        success = manager.add_package(distro, category, subcategory, p, section)
        if success:
            msg = f"Added '{p}' to {distro} -> {category}/{subcategory} ({section})"
            if console:
                console.print(f"[bold green]✓[/bold green] {msg}")
            else:
                print(f"✓ {msg}")
        else:
            msg = f"Package '{p}' already exists in {distro} -> {category}/{subcategory}"
            if console:
                console.print(f"[yellow]![/yellow] {msg}")
            else:
                print(f"! {msg}")


def cli_remove_package(
    manager: TaxonomyManager,
    distro: str,
    category: str,
    subcategory: str,
    package: str,
    section: str = "system_packages",
):
    """Remove a package via CLI."""
    packages = [p.strip() for p in package.split(",") if p.strip()]
    for p in packages:
        success = manager.remove_package(distro, category, subcategory, p, section)
        if success:
            msg = f"Removed '{p}' from {distro} -> {category}/{subcategory} ({section})"
            if console:
                console.print(f"[bold green]✓[/bold green] {msg}")
            else:
                print(f"✓ {msg}")
        else:
            msg = f"Package '{p}' not found in {distro} -> {category}/{subcategory}"
            if console:
                console.print(f"[yellow]![/yellow] {msg}")
            else:
                print(f"! {msg}")


def cli_build_manifest(
    manager: TaxonomyManager,
    distro: str,
    blueprint: str,
    subcategories: List[str],
    output: Optional[str] = None,
    export_format: str = "yaml",
):
    """Generate and export a build manifest via CLI."""
    # Resolve (cat, subcat) pairs
    selected_pairs: List[Tuple[str, str]] = []
    for req in subcategories:
        if "/" in req:
            cat, subcat = req.split("/", 1)
            selected_pairs.append((cat, subcat))
        else:
            # Search which category contains this subcategory
            matched = False
            for cat in manager.get_categories(distro):
                if req in manager.get_subcategories(distro, cat):
                    selected_pairs.append((cat, req))
                    matched = True
                    break
            if not matched:
                print(f"Warning: subcategory '{req}' not found in {distro} taxonomy.")

    manifest = manager.generate_build_manifest(distro, blueprint, selected_pairs)
    out_path = manager.export_manifest(
        manifest, Path(output) if output else None, export_format=export_format
    )
    if console:
        console.print(
            Panel(
                f"[bold green]Build Selection Manifest Saved![/bold green]\n\n"
                f"• Target Distro: [cyan]{distro}[/cyan]\n"
                f"• Blueprint: [magenta]{blueprint}[/magenta]\n"
                f"• Total Packages: [bold]{manifest['metadata']['total_packages']}[/bold]\n"
                f"• Output File: [blue]{out_path}[/blue]",
                title="Manifest Summary",
            )
        )
    else:
        print(f"Manifest written to: {out_path} ({manifest['metadata']['total_packages']} packages)")


# =============================================================================
# Interactive TUI Workflows (Questionary + Rich)
# =============================================================================


def tui_search(manager: TaxonomyManager):
    """Interactive package search."""
    if not questionary:
        print("Error: questionary library required for interactive mode.")
        return

    term = questionary.text("Enter search term:").ask()
    if term and term.strip():
        cli_search(manager, term.strip())


def tui_add_package(manager: TaxonomyManager):
    """Interactive wizard to add package(s) to taxonomy."""
    if not questionary:
        return

    distro_choice = questionary.select(
        "Select target distribution:",
        choices=["All", *DISTROS],
        default="All",
    ).ask()
    if not distro_choice:
        return

    ref_distro = "Fedora" if distro_choice == "All" else distro_choice
    categories = manager.get_categories(ref_distro)
    categories.append("➕ Create New Category...")

    cat_choice = questionary.select("Select category:", choices=categories).ask()
    if not cat_choice:
        return

    if cat_choice == "➕ Create New Category...":
        cat_choice = questionary.text("Enter new category name:").ask()
        if not cat_choice:
            return
        subcats = ["➕ Create New Subcategory..."]
    else:
        subcats = manager.get_subcategories(ref_distro, cat_choice)
        subcats.append("➕ Create New Subcategory...")

    subcat_choice = questionary.select(
        f"Select subcategory under [{cat_choice}]:", choices=subcats
    ).ask()
    if not subcat_choice:
        return

    if subcat_choice == "➕ Create New Subcategory...":
        subcat_choice = questionary.text("Enter new subcategory name:").ask()
        if not subcat_choice:
            return

    pkg_input = questionary.text(
        "Enter package name(s) (comma-separated):"
    ).ask()
    if not pkg_input or not pkg_input.strip():
        return

    cli_add_package(
        manager,
        distro=distro_choice,
        category=cat_choice,
        subcategory=subcat_choice,
        package=pkg_input.strip(),
    )


def tui_remove_package(manager: TaxonomyManager):
    """Interactive wizard to remove package(s) from taxonomy."""
    if not questionary:
        return

    distro_choice = questionary.select(
        "Select distribution:",
        choices=DISTROS,
        default="Fedora",
    ).ask()
    if not distro_choice:
        return

    categories = manager.get_categories(distro_choice)
    if not categories:
        print(f"No categories found for {distro_choice}.")
        return

    cat_choice = questionary.select("Select category:", choices=categories).ask()
    if not cat_choice:
        return

    subcats = manager.get_subcategories(distro_choice, cat_choice)
    if not subcats:
        print(f"No subcategories in {cat_choice}.")
        return

    subcat_choice = questionary.select("Select subcategory:", choices=subcats).ask()
    if not subcat_choice:
        return

    pkgs = manager.get_packages(distro_choice, cat_choice, subcat_choice)
    if not pkgs:
        print(f"No packages in {cat_choice}/{subcat_choice}.")
        return

    to_remove = questionary.checkbox(
        f"Select package(s) to remove from {cat_choice}/{subcat_choice}:",
        choices=[Choice(p) for p in pkgs],
    ).ask()

    if not to_remove:
        return

    confirm = questionary.confirm(
        f"Confirm removal of {len(to_remove)} package(s) from {distro_choice}?"
    ).ask()
    if confirm:
        for p in to_remove:
            manager.remove_package(
                distro=distro_choice,
                category=cat_choice,
                subcategory=subcat_choice,
                package=p,
            )
        if console:
            console.print(f"[bold green]Successfully removed {len(to_remove)} package(s).[/bold green]")
        else:
            print(f"Successfully removed {len(to_remove)} package(s).")


def tui_select_build_packages(manager: TaxonomyManager):
    """Interactive package selection for image build tracking."""
    if not questionary:
        return

    distro = questionary.select(
        "Select target OS distribution:",
        choices=DISTROS,
        default="Fedora",
    ).ask()
    if not distro:
        return

    blueprint = questionary.text(
        "Enter blueprint name:",
        default="workstation",
    ).ask()
    if not blueprint:
        return

    # Build checklist of categories/subcategories
    choices = []
    for cat in manager.get_categories(distro):
        choices.append(Separator(f"── {cat} ──"))
        for subcat in manager.get_subcategories(distro, cat):
            pkgs = manager.get_packages(distro, cat, subcat)
            label = f"{cat}/{subcat} ({len(pkgs)} pkgs)"
            # Default check common core components
            checked = subcat in ["base", "kernel", "installer", "ansible"]
            choices.append(Choice(title=label, value=(cat, subcat), checked=checked))

    selected_subcats = questionary.checkbox(
        "Select components / subcategories for this build:",
        choices=choices,
    ).ask()

    if not selected_subcats:
        print("No components selected. Build canceled.")
        return

    # Extra packages prompt
    extra_str = questionary.text(
        "Optional: Enter any extra packages to include (comma-separated):"
    ).ask()
    extra_pkgs = [p.strip() for p in extra_str.split(",") if p.strip()] if extra_str else []

    # Export format prompt
    fmt = questionary.select(
        "Select export format for the build manifest:",
        choices=["yaml", "json", "toml"],
        default="yaml",
    ).ask()

    manifest = manager.generate_build_manifest(
        distro=distro,
        blueprint=blueprint,
        selected_subcategories=selected_subcats,
        extra_packages=extra_pkgs,
    )

    out_path = manager.export_manifest(manifest, export_format=fmt)

    if console:
        console.print(
            Panel(
                f"[bold green]✓ Build Manifest Successfully Created![/bold green]\n\n"
                f"• Target Distro: [cyan]{distro}[/cyan]\n"
                f"• Blueprint: [magenta]{blueprint}[/magenta]\n"
                f"• Components Selected: [yellow]{len(selected_subcats)}[/yellow]\n"
                f"• Total Packages Resolved: [bold white]{manifest['metadata']['total_packages']}[/bold white]\n"
                f"• Saved To: [bold blue]{out_path}[/bold blue]\n\n"
                f"[dim]Tip: You can use these packages in your osbuild playbook or blueprint.[/dim]",
                title="OSBuild Tracking Record",
            )
        )
    else:
        print(f"Manifest written to: {out_path} ({manifest['metadata']['total_packages']} packages)")


def tui_main_loop(manager: TaxonomyManager):
    """Main interactive TUI loop."""
    if not questionary:
        print("Error: questionary library not found. Run 'pip install questionary rich'.")
        return

    if console:
        console.print(
            Panel(
                "[bold cyan]OSBuild Package Taxonomy & Build Tracker[/bold cyan]\n"
                "[dim]Maintain distribution taxonomies and build package sets[/dim]",
                style="bold blue",
            )
        )

    while True:
        action = questionary.select(
            "What would you like to do?",
            choices=[
                "📦 Select Packages & Create Build Manifest",
                "🔍 Search Packages in Taxonomy",
                "📋 List Taxonomy Categories & Counts",
                "➕ Add Package to Taxonomy",
                "➖ Remove Package from Taxonomy",
                "🚪 Exit",
            ],
        ).ask()

        if action is None or "Exit" in action:
            break
        elif "Select Packages" in action:
            tui_select_build_packages(manager)
        elif "Search Packages" in action:
            tui_search(manager)
        elif "List Taxonomy" in action:
            distro = questionary.select("Select distribution:", choices=DISTROS).ask()
            if distro:
                cli_list(manager, distro)
        elif "Add Package" in action:
            tui_add_package(manager)
        elif "Remove Package" in action:
            tui_remove_package(manager)


# =============================================================================
# Entry Point
# =============================================================================


def main():
    parser = argparse.ArgumentParser(
        description="osbuild Package Tracker & Taxonomy TUI",
        formatter_class=argparse.RawDescriptionHelpFormatter,
    )

    parser.add_argument("--repo-root", type=str, help="Path to repository root")
    parser.add_argument(
        "--distro",
        choices=["All", *DISTROS],
        default="Fedora",
        help="Target distribution (default: Fedora)",
    )

    subparsers = parser.add_subparsers(dest="command")

    # list
    list_p = subparsers.add_parser("list", help="List categories and package counts")
    list_p.add_argument("--distro", choices=DISTROS, default="Fedora")

    # search
    search_p = subparsers.add_parser("search", help="Search for package across taxonomies")
    search_p.add_argument("query", help="Package name substring to search for")

    # add
    add_p = subparsers.add_parser("add", help="Add package(s) to taxonomy")
    add_p.add_argument("--distro", choices=["All", *DISTROS], default="All")
    add_p.add_argument("--category", required=True, help="Category name (e.g. System)")
    add_p.add_argument("--subcategory", required=True, help="Subcategory name (e.g. base)")
    add_p.add_argument("--package", required=True, help="Package name or comma-separated list")
    add_p.add_argument("--section", default="system_packages", help="YAML section (default: system_packages)")

    # remove
    rm_p = subparsers.add_parser("remove", help="Remove package(s) from taxonomy")
    rm_p.add_argument("--distro", choices=["All", *DISTROS], default="Fedora")
    rm_p.add_argument("--category", required=True, help="Category name (e.g. System)")
    rm_p.add_argument("--subcategory", required=True, help="Subcategory name (e.g. base)")
    rm_p.add_argument("--package", required=True, help="Package name or comma-separated list")
    rm_p.add_argument("--section", default="system_packages", help="YAML section (default: system_packages)")

    # build
    build_p = subparsers.add_parser("build", help="Generate build package manifest")
    build_p.add_argument("--distro", choices=DISTROS, default="Fedora")
    build_p.add_argument("--blueprint", default="workstation", help="Blueprint name")
    build_p.add_argument(
        "--subcategories",
        required=True,
        help="Comma-separated list of subcategories or Category/Subcategory pairs",
    )
    build_p.add_argument("--output", help="Path to write the manifest")
    build_p.add_argument("--format", choices=["yaml", "json", "toml"], default="yaml")

    # interactive
    subparsers.add_parser("tui", help="Launch interactive TUI mode")

    args = parser.parse_args()

    repo_root = Path(args.repo_root) if args.repo_root else None
    manager = TaxonomyManager(repo_root=repo_root)

    if args.command == "list":
        cli_list(manager, args.distro)
    elif args.command == "search":
        cli_search(manager, args.query)
    elif args.command == "add":
        cli_add_package(manager, args.distro, args.category, args.subcategory, args.package, args.section)
    elif args.command == "remove":
        cli_remove_package(manager, args.distro, args.category, args.subcategory, args.package, args.section)
    elif args.command == "build":
        subcats = [s.strip() for s in args.subcategories.split(",") if s.strip()]
        cli_build_manifest(manager, args.distro, args.blueprint, subcats, args.output, args.format)
    elif args.command == "tui" or args.command is None:
        if sys.stdin.isatty():
            tui_main_loop(manager)
        else:
            # If piped or non-interactive with no command, display brief summary or help
            cli_list(manager, args.distro)


if __name__ == "__main__":
    main()
