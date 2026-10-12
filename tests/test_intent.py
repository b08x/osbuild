"""Intent-driven generation: schema, users and credentials, kickstart, disk
layout, audit policy and tailoring, remote logging, file modes.

Every example intent in profiles/examples/ is generated once through
tests/generate.yml (the role's generate_only path without a build host).
"""
import re
import shutil
import stat
import subprocess

import jsonschema
import pytest
from passlib.hash import sha512_crypt

from intent_helpers import (EXAMPLES, ROOT, SCHEMA, generate, generate_intent, load_intent,
                            run_generate)

EXAMPLE_IDS = [p.stem for p in EXAMPLES]
HARDENED = [p.stem for p in EXAMPLES if load_intent(p)["hardening"] != "none"]


def cis_intent():
    return load_intent(ROOT / "profiles" / "examples" / "rocky-10-2-workstation-openscap-cis-l2-workstation.yml")


# ---- schema ------------------------------------------------------------------------

def test_every_iso_variant_has_an_example_and_no_iso_playbook_is_left():
    assert len(EXAMPLES) >= 9
    assert not list((ROOT / "playbooks").glob("osbuild-*-iso*.yml"))
    # container and bootc playbooks stay
    assert (ROOT / "playbooks" / "osbuild-rocky-cuda-container.yml").is_file()


@pytest.mark.parametrize("example", EXAMPLES, ids=EXAMPLE_IDS)
def test_example_intents_validate(example):
    jsonschema.Draft7Validator(SCHEMA).validate(load_intent(example))


def errors_for(intent):
    return sorted(".".join(map(str, e.absolute_path)) or "(top level)"
                  for e in jsonschema.Draft7Validator(SCHEMA).iter_errors(intent))


@pytest.mark.parametrize("mutate,field", [
    (lambda i: i.pop("disk"), "(top level)"),
    (lambda i: i.update(colour="red"), "(top level)"),
    (lambda i: i.update(hardening="stig"), "hardening"),
    (lambda i: i["disk"].update(size_gib=10), "disk.size_gib"),
    (lambda i: i["disk"].update(tmp="ramdisk"), "disk.tmp"),
    (lambda i: i["disk"].update(serial="bad serial"), "disk.serial"),
    (lambda i: i["disk"].update(passphrase="secret"), "disk"),
    (lambda i: i.update(distro="almalinux-10.2"), "distro"),   # hardening needs rocky-10
    (lambda i: i.update(distro="rocky-10"), "distro"),
    (lambda i: i.update(hostname="Bad_Host"), "hostname"),
    (lambda i: i["components"].append("openscap-hipaa"), "components.14"),
    (lambda i: i.update(users=[]), "users"),
    (lambda i: i["users"][0].update(name="root"), "users.0.name"),
    (lambda i: i["users"][0].update(uid=10), "users.0.uid"),
    (lambda i: i["users"][0].update(gecos='Evil" --groups=root'), "users.0.gecos"),
    (lambda i: i["users"][0].update(ssh_pubkey="not a key"), "users.0.ssh_pubkey"),
    (lambda i: i["users"][0].update(password="hunter2"), "users.0"),
    (lambda i: i.update(remote_logging={"enabled": True}), "remote_logging"),
    (lambda i: i.update(remote_logging={"enabled": True, "url": "http://log:19532", "ca_cert": "a",
                                        "client_cert": "b", "client_key": "c"}), "remote_logging.url"),
])
def test_schema_rejects_bad_intents_naming_the_field(mutate, field):
    intent = cis_intent()
    mutate(intent)
    assert field in errors_for(intent)


def test_play_validates_before_anything_else_and_names_the_fields(tmp_path):
    intent = cis_intent()
    intent["disk"]["size_gib"] = 10
    intent["hardening"] = "stig"
    intent["colour"] = "red"
    profile = tmp_path / "bad.yml"
    import yaml
    profile.write_text(yaml.safe_dump({"intent": intent}))
    result = run_generate(profile, tmp_path / "out")
    assert result.returncode != 0
    out = result.stdout
    assert "intent.disk.size_gib: 10 is less than the minimum of 32" in out
    assert "intent.hardening: 'stig' is not one of" in out
    assert "'colour' was unexpected" in out
    # failed at validation: the first task after the validation never ran
    assert "Map the intent to role variables" not in out
    assert not (tmp_path / "out").exists()


def test_play_without_an_intent_says_how_to_pass_one(tmp_path):
    profile = tmp_path / "flat.yml"
    profile.write_text("name: x\ndistro: rocky-10.2\n")
    result = run_generate(profile, tmp_path / "out")
    assert result.returncode != 0
    assert "top-level key is `intent`" in result.stdout


def test_build_playbook_validates_first():
    import yaml
    play = yaml.safe_load((ROOT / "playbooks" / "build.yml").read_text())[0]
    first = play["pre_tasks"][0]
    assert first["ansible.builtin.include_role"]["tasks_from"] == "intent.yml"
    tasks = yaml.safe_load((ROOT / "roles" / "osbuild" / "tasks" / "intent.yml").read_text())
    assert "ansible.utils.validate" in tasks[1]
    assert tasks[1]["ansible.utils.validate"]["engine"] == "ansible.utils.jsonschema"


def test_profiles_are_gitignored_except_examples():
    check = subprocess.run(["git", "check-ignore", "-q", "profiles/mine.yml"], cwd=ROOT)
    assert check.returncode == 0
    check = subprocess.run(["git", "check-ignore", "-q", "profiles/examples/x.yml"], cwd=ROOT)
    assert check.returncode == 1


# ---- outputs, modes, credentials ---------------------------------------------------

@pytest.mark.parametrize("example", EXAMPLE_IDS)
def test_outputs_are_mode_0600(generated, example):
    g = generated[example]
    for path in (g.toml_path, g.script_path, g.credentials_path):
        assert stat.S_IMODE(path.stat().st_mode) == 0o600, path.name
    assert not list(g.dir.glob("*~")), "backup copies of the blueprint leak secrets"


@pytest.mark.parametrize("example", EXAMPLE_IDS)
def test_iso_is_made_0600_by_the_build_script(generated, example):
    g = generated[example]
    assert f"chmod 0600 {g.name}-test.iso" in g.script_path.read_text()


@pytest.mark.parametrize("example", EXAMPLE_IDS)
def test_only_the_hash_reaches_the_blueprint(generated, example):
    g = generated[example]
    passwords = g.passwords()
    assert list(passwords) == ["syncopated"]
    password = passwords["syncopated"]
    assert re.fullmatch(r"[A-Za-z0-9]{20}", password)
    m = re.search(r"^user --name=syncopated .* --iscrypted --password=(\S+)$", g.kickstart, re.M)
    assert m and m.group(1).startswith("$6$")
    assert sha512_crypt.verify(password, m.group(1))
    for path in (g.toml_path, g.script_path):
        assert password not in path.read_text()


def test_each_generation_makes_a_new_password(tmp_path):
    profile = EXAMPLES[0]
    a = generate(profile, tmp_path / "a").passwords()
    b = generate(profile, tmp_path / "b").passwords()
    assert a != b


def test_password_is_printed_once_at_the_end(generated):
    g = generated["rocky-10-2-workstation-components"]
    password = g.passwords()["syncopated"]
    assert g.log.count(password) == 0  # tests/generate.yml does not run the role's banner
    main = (ROOT / "roles" / "osbuild" / "tasks" / "main.yml").read_text()
    assert "Display the temporary user passwords" in main
    assert main.index("Display the temporary user passwords") > main.index("MODE generate_only")


@pytest.mark.parametrize("example", EXAMPLE_IDS)
def test_no_luks_passphrase_anywhere(generated, example):
    g = generated[example]
    for path in g.dir.iterdir():
        assert "passphrase" not in path.read_text().replace(
            "the LUKS passphrase", "").replace("LUKS passphrases", "").lower().replace(
            "asks for the passphrase", ""), path.name
        assert "--passphrase" not in path.read_text()


def test_missing_passlib_fails_early_with_a_clear_message(tmp_path):
    result = run_generate(EXAMPLES[0], tmp_path / "out",
                          extra={"osbuild_controller_python": "/nonexistent/python3"})
    assert result.returncode != 0
    assert "passlib is not importable" in result.stdout
    assert "Map the intent to role variables" not in result.stdout


# ---- kickstart -----------------------------------------------------------------------

@pytest.mark.parametrize("example", EXAMPLE_IDS)
def test_install_asks_nothing(generated, example):
    g = generated[example]
    ks = g.kickstart
    assert re.search(r"^rootpw --lock$", ks, re.M)
    assert re.search(r"^user --name=syncopated --gecos=\"Syncopated Admin\" --groups=wheel", ks, re.M)
    assert "%include /tmp/partitions.ks" in ks
    assert "chage -d 0 syncopated" in ks
    for conflict in ("user", "group"):
        assert conflict not in g.customizations
    assert "unattended" not in g.customizations["installer"]
    # storage comes from the generated layout, never from the storage spoke
    assert g.layout_ks.startswith("ignoredisk --only-use=@DISK@\nzerombr\nclearpart --all")


@pytest.mark.parametrize("example", EXAMPLE_IDS)
def test_kickstart_passes_ksvalidator_rhel10(generated, example, tmp_path):
    ksvalidator = shutil.which("ksvalidator")
    if not ksvalidator:
        pytest.skip("ksvalidator (pykickstart) not installed")
    ks = tmp_path / "ks.cfg"
    ks.write_text(generated[example].standalone_kickstart("nvme0n1"))
    run = subprocess.run([ksvalidator, "-v", "RHEL10", str(ks)], capture_output=True, text=True)
    assert run.returncode == 0, run.stdout + run.stderr


def test_user_groups_come_from_wheel_components_and_intent(tmp_path):
    intent = cis_intent()
    intent["components"].append("intel-oneapi")
    intent["users"] = [
        {"name": "ada", "gecos": "Ada", "groups": ["audio", "wheel"], "uid": 1500,
         "ssh_pubkey": "ssh-ed25519 AAAAC3NzaC1lZDI1NTE5AAAAIEXAMPLEKEYexamplekeyEXAMPLEKEYexample ada@host"},
        {"name": "bob", "gecos": "Bob"},
    ]
    g = generate_intent(intent, tmp_path)
    lines = [l for l in g.kickstart.splitlines() if l.startswith("user ")]
    assert lines[0].startswith('user --name=ada --gecos="Ada" --groups=wheel,libvirt,render,video,audio --uid=1500 --iscrypted')
    assert lines[1].startswith('user --name=bob --gecos="Bob" --groups=wheel,libvirt,render,video --iscrypted')
    assert 'sshkey --username=ada "ssh-ed25519 AAAAC3' in g.kickstart
    assert "sshkey --username=bob" not in g.kickstart
    assert set(g.passwords()) == {"ada", "bob"}
    assert g.passwords()["ada"] != g.passwords()["bob"]


def test_component_without_user_groups_adds_only_wheel(generated):
    # rocky-10-2-workstation-components selects containers-virt (libvirt)
    ks = generated["rocky-10-2-workstation-components"].kickstart
    assert "--groups=wheel,libvirt " in ks


# ---- disk layout -----------------------------------------------------------------------

@pytest.mark.parametrize("example", EXAMPLE_IDS)
def test_layout_has_fixed_sizes_from_the_declared_disk(generated, example):
    g = generated[example]
    intent = load_intent(ROOT / "profiles" / "examples" / f"{example}.yml")
    assert g.layout_env["DECLARED_MIB"] == str(intent["disk"]["size_gib"] * 1024)
    assert g.layout_env["COUNTDOWN"] == "30"
    assert g.logvols() == {v["mount"]: v["size_mib"] for v in g.report["disk_layout"]["volumes"]}
    assert "--grow" not in "".join(l for l in g.layout_ks.splitlines() if l.startswith("logvol"))
    if intent["hardening"] == "none":
        assert list(g.logvols()) == ["/", "/usr", "/var", "/home"]
    else:
        assert set(g.logvols()) == {"/", "/usr", "/var", "/var/tmp", "/var/log", "/var/log/audit", "/home"}
        audit = 10 if intent["hardening"] == "hipaa" else 4
        assert g.logvols()["/var/log/audit"] == audit * 1024
        assert re.search(r'^logvol /var/log/audit .*--fsoptions="nodev,nosuid,noexec,noatime"$', g.layout_ks, re.M)
    cuda = {"nvidia", "cuda-container"} & set(intent["components"])
    usr = g.logvols()["/usr"]
    if cuda:
        assert usr >= 80 * 1024
    elif intent["hardening"] != "none":
        assert usr == 45 * 1024
    encrypted = "--encrypted" in g.layout_ks
    assert encrypted == intent["disk"].get("encrypt", False)


def test_serial_pin_and_small_disk(tmp_path):
    intent = cis_intent()
    intent["disk"].update(serial="S5GXNF0R123", tmp="lv")
    g = generate_intent(intent, tmp_path)
    assert g.layout_env["DISK_SERIAL"] == "S5GXNF0R123"
    assert g.logvols()["/tmp"] == 8 * 1024
    assert "tmpfs /tmp" not in g.kickstart


def test_tmpfs_tmp_is_an_fstab_line(generated):
    ks = generated["rocky-10-2-workstation-openscap-cis-l2-workstation"].kickstart
    assert "tmpfs /tmp tmpfs defaults,nodev,nosuid,noexec,mode=1777,size=8192M 0 0" in ks


def test_too_small_declared_disk_fails_at_generation(tmp_path):
    intent = cis_intent()
    intent["disk"]["size_gib"] = 120
    with pytest.raises(RuntimeError, match=r"disk.size_gib=120 is too small for the compliant layout; it needs at least \d+ GiB"):
        generate_intent(intent, tmp_path)


# ---- audit policy and tailoring --------------------------------------------------------

AUDIT_ACTION_RULES = {"auditd_data_retention_max_log_file_action", "auditd_data_retention_max_log_file",
                      "auditd_data_retention_admin_space_left_action", "auditd_data_retention_space_left_action",
                      "auditd_data_disk_full_action", "auditd_data_disk_error_action"}


def auditd_conf(g):
    data = g.file("/etc/audit/auditd.conf")["data"]
    return dict(map(str.strip, l.split("=", 1)) for l in data.splitlines() if l and not l.startswith("#"))


@pytest.mark.parametrize("example", HARDENED)
def test_auditd_conf_rotates_and_never_halts(generated, example):
    g = generated[example]
    conf = auditd_conf(g)
    hipaa = "hipaa" in example
    assert conf["max_log_file_action"] == "rotate"
    assert conf["max_log_file"] == ("64" if hipaa else "32")
    assert conf["num_logs"] == ("32" if hipaa else "16")
    assert conf["admin_space_left_action"] == "rotate"
    assert conf["disk_full_action"] == "rotate"
    assert conf["disk_error_action"] == "syslog"
    assert conf["space_left_action"] == "exec /usr/local/sbin/syncopated-audit-warn"
    assert conf["space_left"] == "25%"
    for key in ("space_left_action", "admin_space_left_action", "disk_full_action", "disk_error_action",
                "max_log_file_action"):
        assert not re.search(r"\b(single|halt|suspend|keep_logs)\b", conf[key]), key
    assert g.file("/etc/audit/auditd.conf")["mode"] == "0640"


@pytest.mark.parametrize("example", HARDENED)
def test_tailoring_unselects_the_audit_deviations(generated, example):
    g = generated[example]
    unselected = set(g.unselected())
    assert AUDIT_ACTION_RULES <= unselected
    noise = {r for r in unselected if r.startswith(("audit_rules_dac_modification_", "audit_rules_file_deletion_events_"))}
    if "hipaa" in example:
        assert not [r for r in unselected if r.startswith("audit_rules_")], "HIPAA keeps every audit rule"
    else:
        assert {"audit_rules_dac_modification_chmod", "audit_rules_dac_modification_setxattr",
                "audit_rules_file_deletion_events_unlink", "audit_rules_file_deletion_events_rename"} <= noise
    # the stock profile stays the base of the tailoring
    assert g.customizations["openscap"]["profile_id"].startswith("xccdf_org.ssgproject.content_profile_")
    assert g.customizations["openscap"]["datastream"].endswith("ssg-rhel10-ds.xml")


@pytest.mark.parametrize("example", HARDENED)
def test_no_post_override_of_audit_settings(generated, example):
    ks = generated[example].kickstart
    assert "auditd.conf" not in ks and "audit.rules" not in ks


@pytest.mark.parametrize("example", HARDENED)
def test_warning_and_scan_tools_are_installed(generated, example):
    g = generated[example]
    assert g.file("/usr/local/sbin/syncopated-audit-warn")["mode"] == "0755"
    assert g.file("/usr/local/bin/syncopated-audit-notify")["mode"] == "0755"
    assert g.file("/etc/xdg/autostart/syncopated-audit-notify.desktop")
    assert g.file("/etc/systemd/system/syncopated-audit-check.timer")
    assert "syncopated-audit-check.timer" in g.customizations["services"]["enabled"]
    assert g.file("/usr/local/bin/syncopated-scan")["mode"] == "0755"
    scan = g.file("/etc/syncopated/scan.conf")["data"]
    assert f"PROFILE={g.customizations['openscap']['profile_id']}" in scan
    assert "DATASTREAM=/usr/share/xml/scap/ssg/content/ssg-rhel10-ds.xml" in scan
    assert g.file("/etc/cockpit/cockpit.conf")["data"].endswith("Banner=/etc/cockpit/issue.cockpit\n")
    for f in g.customizations["files"]:
        assert f["path"].startswith(("/etc/", "/usr/local/bin/", "/usr/local/sbin/")), \
            f"{f['path']} is outside image-builder's allowed custom file paths"


def test_unhardened_builds_have_no_audit_policy(generated):
    g = generated["rocky-10-2-workstation-components"]
    assert "openscap" not in g.customizations
    assert g.file("/etc/audit/auditd.conf") is None
    assert "# BEGIN syncopated-hardening" not in g.raw


# ---- remote logging ----------------------------------------------------------------------

def test_remote_logging_off_disables_upload_and_unselects_its_cis_rule(generated):
    g = generated["rocky-10-2-workstation-openscap-cis-l2-workstation"]
    assert "service_systemd-journal-upload_enabled" in g.unselected()
    assert g.customizations["services"]["disabled"] == ["systemd-journal-upload"]
    assert "systemd-journal-upload" not in g.customizations["services"]["enabled"]
    assert g.file("/etc/systemd/journal-upload.conf.d/50-syncopated.conf") is None


def test_remote_logging_off_without_the_package_disables_nothing(generated):
    services = generated["rocky-10-2-workstation-openscap-hipaa"].customizations["services"]
    assert "disabled" not in services


PEM = "-----BEGIN CERTIFICATE-----\nMIIBfake\n-----END CERTIFICATE-----\n"
KEY = "-----BEGIN PRIVATE KEY-----\nMIIBfakekey\n-----END PRIVATE KEY-----\n"


def test_remote_logging_on_is_one_switch(tmp_path):
    intent = cis_intent()
    ca = tmp_path / "ca.pem"
    ca.write_text(PEM)
    intent["remote_logging"] = {"enabled": True, "url": "https://logs.example.net:19532",
                                "ca_cert": str(ca), "client_cert": PEM, "client_key": KEY}
    g = generate_intent(intent, tmp_path)
    assert "service_systemd-journal-upload_enabled" not in g.unselected()
    services = g.customizations["services"]
    assert "systemd-journal-upload" in services["enabled"]
    assert "systemd-journald-audit.socket" in services["enabled"]
    assert "disabled" not in services
    assert {"name": "systemd-journal-remote", "version": "*"} in g.blueprint["packages"]
    conf = g.file("/etc/systemd/journal-upload.conf.d/50-syncopated.conf")["data"]
    assert "URL=https://logs.example.net:19532" in conf
    assert "ServerKeyFile=/run/credentials/systemd-journal-upload.service/client.key" in conf
    unit = g.file("/etc/systemd/system/systemd-journal-upload.service.d/50-syncopated.conf")["data"]
    assert "StartLimitIntervalSec=0" in unit and "Restart=always" in unit
    assert "LoadCredential=client.key:/etc/pki/syncopated/journal-upload/client.key" in unit
    assert g.file("/etc/pki/syncopated/journal-upload/ca.pem")["data"] == PEM
    key = g.file("/etc/pki/syncopated/journal-upload/client.key")
    assert key["data"] == KEY and key["mode"] == "0600"
    # the key is only in the 0600 blueprint, never in the play output
    assert "MIIBfakekey" not in g.log


def test_remote_logging_works_without_hardening(tmp_path):
    intent = load_intent(ROOT / "profiles" / "examples" / "rocky-10-2-workstation-components.yml")
    intent["remote_logging"] = {"enabled": True, "url": "https://logs.example.net",
                                "ca_cert": PEM, "client_cert": PEM, "client_key": KEY}
    g = generate_intent(intent, tmp_path)
    assert "systemd-journal-upload" in g.customizations["services"]["enabled"]
    assert g.file("/etc/systemd/journal-upload.conf.d/50-syncopated.conf")


def test_remote_logging_rejects_non_pem(tmp_path):
    intent = cis_intent()
    bad = tmp_path / "bad.pem"
    bad.write_text("not a certificate\n")
    intent["remote_logging"] = {"enabled": True, "url": "https://logs.example.net",
                                "ca_cert": str(bad), "client_cert": PEM, "client_key": KEY}
    with pytest.raises(RuntimeError, match="remote_logging.ca_cert is not PEM"):
        generate_intent(intent, tmp_path)


# ---- build script --------------------------------------------------------------------------

@pytest.mark.parametrize("example", EXAMPLE_IDS)
def test_build_script_passes_shellcheck(generated, example):
    if not shutil.which("shellcheck"):
        pytest.skip("shellcheck not installed")
    run = subprocess.run(["shellcheck", str(generated[example].script_path)], capture_output=True, text=True)
    assert run.returncode == 0, run.stdout


@pytest.mark.parametrize("example", EXAMPLE_IDS)
def test_extra_repos_come_from_components(generated, example):
    g = generated[example]
    urls = g.report["extra_repo_urls"]
    if load_intent(ROOT / "profiles" / "examples" / f"{example}.yml")["distro"].startswith("rocky-10"):
        # Rocky CRB, Plus and RT for depsolve (former skill hard rule, now component data)
        for repo in ("CRB", "plus", "RT"):
            assert f"https://dl.rockylinux.org/pub/rocky/10/{repo}/x86_64/os/" in urls
    for url in urls:
        assert f"--extra-repo {url}" in g.script_path.read_text() or f"--extra-repo '{url}'" in g.script_path.read_text()
