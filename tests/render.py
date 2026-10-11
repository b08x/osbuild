"""Render a component-composed blueprint through tests/render_blueprint.yml."""
import json
import subprocess
import tempfile
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent


def render(distro, components, *, name="custom", description="Custom Workstation",
           hostname="syncopated", template="blueprint-components.toml.j2", extra=None):
    """Return the rendered text of `template` for the given target and components."""
    with tempfile.TemporaryDirectory() as tmp:
        out = Path(tmp) / "out"
        evars = {
            "osbuild_distro": distro,
            "osbuild_blueprint_components": list(components),
            "osbuild_blueprint_name": name,
            "osbuild_blueprint_description": description,
            "osbuild_hostname": hostname,
            "render_out": str(out),
            "render_template": template,
        }
        evars.update(extra or {})
        result = subprocess.run(
            ["ansible-playbook", str(ROOT / "tests" / "render_blueprint.yml"),
             "-e", json.dumps(evars)],
            cwd=ROOT, capture_output=True, text=True,
            env={**__import__("os").environ, "ANSIBLE_NOCOLOR": "1", "ANSIBLE_LOCAL_TEMP": tmp,
                 "ANSIBLE_REMOTE_TEMP": tmp},
        )
        if result.returncode != 0:
            raise RuntimeError(result.stdout + result.stderr)
        return out.read_text()
