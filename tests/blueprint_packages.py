"""Print or return the sorted package-name set of a blueprint TOML."""
import sys
import tomllib
from pathlib import Path


def package_names(toml_text):
    """Names from `packages = [...]`/`[[packages]]` plus `[[groups]]` (as @name)."""
    data = tomllib.loads(toml_text)
    names = set()
    for pkg in data.get("packages", []):
        names.add(pkg if isinstance(pkg, str) else pkg["name"])
    for grp in data.get("groups", []):
        gname = grp if isinstance(grp, str) else grp["name"]
        names.add("@" + gname.lstrip("@"))
    return sorted(names)


if __name__ == "__main__":
    print("\n".join(package_names(Path(sys.argv[1]).read_text())))
