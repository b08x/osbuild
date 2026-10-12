"""Generate an intent's outputs through tests/generate.yml (no build host)."""
import json
import os
import re
import subprocess
import tempfile
import tomllib
from pathlib import Path

import yaml

ROOT = Path(__file__).resolve().parent.parent
EXAMPLES = sorted((ROOT / "profiles" / "examples").glob("*.yml"))
SCHEMA = json.loads((ROOT / "schema" / "intent.schema.json").read_text())


def load_intent(path):
    return yaml.safe_load(Path(path).read_text())["intent"]


def run_generate(profile, out_dir, extra=None):
    """Run tests/generate.yml; return the CompletedProcess."""
    cmd = ["ansible-playbook", str(ROOT / "tests" / "generate.yml"),
           "-e", f"@{profile}", "-e", json.dumps({"generate_out": str(out_dir), **(extra or {})})]
    env = {**os.environ, "ANSIBLE_NOCOLOR": "1", "ANSIBLE_LOCAL_TEMP": str(out_dir) + ".tmp",
           "ANSIBLE_REMOTE_TEMP": str(out_dir) + ".tmp"}
    return subprocess.run(cmd, cwd=ROOT, capture_output=True, text=True, env=env, stdin=subprocess.DEVNULL)


def generate(profile, out_dir):
    """Generate and return a Generated for ``profile``; raise with the play output on failure."""
    result = run_generate(profile, out_dir)
    if result.returncode != 0:
        raise RuntimeError(result.stdout[-6000:] + result.stderr[-3000:])
    return Generated(out_dir, result.stdout)


def generate_intent(intent, tmp_path):
    """Write ``intent`` to a profile file under tmp_path and generate it."""
    profile = tmp_path / "profile.yml"
    profile.write_text(yaml.safe_dump({"intent": intent}))
    return generate(profile, tmp_path / "out")


class Generated:
    def __init__(self, out_dir, log):
        self.dir = Path(out_dir)
        self.log = log
        self.report = json.loads((self.dir / "generated.json").read_text())
        self.name = self.report["blueprint_name"]
        self.toml_path = self.dir / f"{self.name}.toml"
        self.raw = self.toml_path.read_text()
        self.blueprint = tomllib.loads(self.raw)
        self.script_path = self.dir / f"build-{self.name}.sh"
        self.credentials_path = self.dir / f"{self.name}.credentials.txt"

    @property
    def customizations(self):
        return self.blueprint.get("customizations", {})

    @property
    def kickstart(self):
        return self.customizations["installer"]["kickstart"]["contents"]

    def file(self, path):
        hits = [f for f in self.customizations.get("files", []) if f["path"] == path]
        assert len(hits) <= 1, f"{path} injected {len(hits)} times"
        return hits[0] if hits else None

    @property
    def layout_ks(self):
        m = re.search(r"cat >/tmp/syncopated-layout\.ks <<'EOF'\n(.*?)\nEOF\n", self.kickstart, re.S)
        return m.group(1)

    @property
    def layout_env(self):
        m = re.search(r"cat >/tmp/syncopated-layout\.env <<'EOF'\n(.*?)\nEOF\n", self.kickstart, re.S)
        return dict(line.split("=", 1) for line in m.group(1).splitlines())

    def logvols(self):
        """{mount: size_mib} from the rendered layout."""
        return {m.group(1): int(m.group(2))
                for m in re.finditer(r"^logvol (\S+) .*--size=(\d+)", self.layout_ks, re.M)}

    def passwords(self):
        return dict(line.split(": ", 1) for line in self.credentials_path.read_text().splitlines()
                    if line and not line.startswith("#"))

    def tailoring(self):
        """The injected JSON tailoring profile (templates/openscap-tailoring.json.j2), or {}."""
        ref = self.customizations.get("openscap", {}).get("json_tailoring")
        if not ref:
            return {}
        (profile,) = json.loads(self.file(ref["filepath"])["data"])["profiles"]
        return profile

    def unselected(self):
        rules = self.tailoring().get("rules", {})
        return [r for r, v in rules.items() if v == {"evaluate": False}]

    def variables(self):
        return {k: v["value"] for k, v in self.tailoring().get("variables", {}).items()}

    def standalone_kickstart(self, disk="vda"):
        """The kickstart with %include /tmp/partitions.ks replaced by the layout for ``disk``."""
        return self.kickstart.replace("%include /tmp/partitions.ks\n",
                                      self.layout_ks.replace("@DISK@", disk) + "\n")


def tmpdir():
    return Path(tempfile.mkdtemp(prefix="syncopated-intent-"))
