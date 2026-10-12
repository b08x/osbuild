"""remote_logging end to end: a throwaway systemd-journal-remote receives
journal and audit entries over mTLS, configured from the files the role
generates for remote_logging.enabled: true.

What runs here: a local systemd-journal-remote (HTTPS, client certificates
required, CA from the test) and systemd-journal-upload with the URL and the
key/certificate/CA roles taken from the generated drop-in
/etc/systemd/journal-upload.conf.d/50-syncopated.conf. The source is a
journal file holding an ordinary entry and an audit entry (_TRANSPORT=audit),
as journald writes them on the workstation. A second run against a port with
no listener must fail on its own without hanging: the workstation only logs
the failure (the unit drop-in restarts the uploader every 30 s).

Needs systemd-journal-remote (journal-remote and journal-upload binaries) and
openssl; skipped otherwise. The VM variant (a VM built from the ISO) is part
of tests/vm/run-install-test.sh.
"""
import re
import shutil
import socket
import subprocess
import time
from pathlib import Path

import pytest

from intent_helpers import ROOT, generate_intent, load_intent

LIB = Path("/usr/lib/systemd")
REMOTE, UPLOAD = LIB / "systemd-journal-remote", LIB / "systemd-journal-upload"

pytestmark = pytest.mark.skipif(
    not (REMOTE.exists() and UPLOAD.exists() and shutil.which("openssl") and shutil.which("journalctl")),
    reason="systemd-journal-remote/-upload, journalctl or openssl missing")


def remote_verifies_clients():
    """Whether this systemd-journal-remote can require client certificates
    (--trust needs systemd built with gnutls; Ubuntu's is not)."""
    run = subprocess.run([str(REMOTE), "--listen-https=127.0.0.1:1", "--trust=/nonexistent", "--key=/x", "--cert=/x"],
                         capture_output=True, text=True, timeout=10)
    return "is not available" not in run.stdout + run.stderr


def start_remote(port, pki, out):
    trust = [f"--trust={pki / 'ca.pem'}"] if remote_verifies_clients() else []
    remote = subprocess.Popen(
        [str(REMOTE), f"--listen-https=127.0.0.1:{port}", f"--key={pki / 'server.key'}",
         f"--cert={pki / 'server.pem'}", *trust, f"--output={out}/"],
        stdout=subprocess.PIPE, stderr=subprocess.STDOUT, text=True)
    for _ in range(100):
        with socket.socket() as sock:
            if sock.connect_ex(("127.0.0.1", port)) == 0:
                return remote
        if remote.poll() is not None:
            raise RuntimeError(remote.stdout.read())
        time.sleep(0.1)
    remote.terminate()
    raise RuntimeError("systemd-journal-remote did not start listening")


def free_port():
    with socket.socket() as s:
        s.bind(("127.0.0.1", 0))
        return s.getsockname()[1]


def openssl(*args, cwd):
    subprocess.run(["openssl", *args], cwd=cwd, check=True, capture_output=True)


def make_pki(d):
    """CA, server certificate for 127.0.0.1 and a client certificate."""
    openssl("req", "-x509", "-newkey", "rsa:2048", "-nodes", "-keyout", "ca.key", "-out", "ca.pem",
            "-days", "2", "-subj", "/CN=syncopated-test-ca", cwd=d)
    for name, ext in (("server", "subjectAltName=IP:127.0.0.1,DNS:localhost"), ("client", "extendedKeyUsage=clientAuth")):
        openssl("req", "-newkey", "rsa:2048", "-nodes", "-keyout", f"{name}.key", "-out", f"{name}.csr",
                "-subj", f"/CN={name}", cwd=d)
        (d / f"{name}.ext").write_text(ext + "\n")
        openssl("x509", "-req", "-in", f"{name}.csr", "-CA", "ca.pem", "-CAkey", "ca.key", "-CAcreateserial",
                "-out", f"{name}.pem", "-days", "2", "-extfile", f"{name}.ext", cwd=d)


EXPORT = """__REALTIME_TIMESTAMP={t}
_BOOT_ID=0123456789abcdef0123456789abcdef
_HOSTNAME=syncopated-dx
SYSLOG_IDENTIFIER=syncopated-e2e
PRIORITY=6
MESSAGE=syncopated remote logging e2e {tag}

__REALTIME_TIMESTAMP={t2}
_BOOT_ID=0123456789abcdef0123456789abcdef
_HOSTNAME=syncopated-dx
_TRANSPORT=audit
SYSLOG_IDENTIFIER=audit
_AUDIT_TYPE_NAME=USER_LOGIN
MESSAGE=type=USER_LOGIN msg=audit(1.000:42): op=login acct="syncopated" res=success {tag}

"""


@pytest.fixture(scope="module")
def upload_conf(tmp_path_factory):
    """The generated journal-upload drop-in for an enabled intent, as a dict."""
    tmp = tmp_path_factory.mktemp("intent")
    pki = tmp_path_factory.mktemp("pki")
    make_pki(pki)
    intent = load_intent(ROOT / "profiles" / "examples" / "rocky-10-2-workstation-openscap-cis-l2-workstation.yml")
    intent["remote_logging"] = {"enabled": True, "url": "https://127.0.0.1:PORT",
                                "ca_cert": str(pki / "ca.pem"), "client_cert": str(pki / "client.pem"),
                                "client_key": str(pki / "client.key")}
    g = generate_intent(intent, tmp)
    conf = dict(re.findall(r"^(\w+)=(.*)$", g.file("/etc/systemd/journal-upload.conf.d/50-syncopated.conf")["data"], re.M))
    unit = g.file("/etc/systemd/system/systemd-journal-upload.service.d/50-syncopated.conf")["data"]
    creds = dict(re.findall(r"^LoadCredential=([^:]+):(.*)$", unit, re.M))
    # Map each credential the uploader reads to the file the image ships, then
    # to the test's copy of that file (what LoadCredential does at runtime).
    shipped = {f["path"]: f["data"] for f in g.customizations["files"]}
    local = {}
    for key in ("ServerKeyFile", "ServerCertificateFile", "TrustedCertificateFile"):
        cred = Path(conf[key]).name
        path = tmp / cred
        path.write_text(shipped[creds[cred]])
        path.chmod(0o600)
        local[key] = path
    return {"url": conf["URL"], **local, "pki": pki}


def make_source_journal(tmp, tag):
    now = int(time.time() * 1_000_000)
    src = tmp / "source" / "src.journal"
    src.parent.mkdir()
    subprocess.run([str(REMOTE), f"--output={src}", "-"], input=EXPORT.format(t=now, t2=now + 1, tag=tag),
                   text=True, check=True, capture_output=True)
    return src


def test_journal_and_audit_entries_reach_the_log_host(upload_conf, tmp_path):
    port = free_port()
    pki = upload_conf["pki"]
    out = tmp_path / "remote"
    out.mkdir()
    remote = start_remote(port, pki, out)
    try:
        tag = f"tag-{time.time_ns()}"
        src = make_source_journal(tmp_path, tag)
        upload = subprocess.run(
            [str(UPLOAD), f"--url={upload_conf['url'].replace('PORT', str(port))}",
             f"--key={upload_conf['ServerKeyFile']}", f"--cert={upload_conf['ServerCertificateFile']}",
             f"--trust={upload_conf['TrustedCertificateFile']}", f"--file={src}",
             f"--save-state={tmp_path / 'state'}", "--follow=no"],
            capture_output=True, text=True, timeout=60)
        assert upload.returncode == 0, upload.stdout + upload.stderr
        time.sleep(1)
    finally:
        remote.terminate()
        remote.wait(timeout=10)
    entries = subprocess.run(["journalctl", f"--directory={out}", "-o", "export", "--no-pager"],
                             capture_output=True, text=True).stdout
    assert f"MESSAGE=syncopated remote logging e2e {tag}" in entries
    assert "_TRANSPORT=audit" in entries and f'acct="syncopated" res=success {tag}' in entries


def test_a_client_without_a_trusted_certificate_is_refused(upload_conf, tmp_path):
    if not remote_verifies_clients():
        pytest.skip("this systemd-journal-remote cannot require client certificates (no --trust)")
    port = free_port()
    pki = upload_conf["pki"]
    out = tmp_path / "remote"
    out.mkdir()
    other = tmp_path / "other"
    other.mkdir()
    make_pki(other)   # a client certificate from another CA
    remote = start_remote(port, pki, out)
    try:
        src = make_source_journal(tmp_path, "refused")
        upload = subprocess.run(
            [str(UPLOAD), f"--url=https://127.0.0.1:{port}", f"--key={other / 'client.key'}",
             f"--cert={other / 'client.pem'}", f"--trust={pki / 'ca.pem'}", f"--file={src}",
             f"--save-state={tmp_path / 'state'}", "--follow=no"],
            capture_output=True, text=True, timeout=60)
    finally:
        remote.terminate()
        remote.wait(timeout=10)
    assert upload.returncode != 0
    entries = subprocess.run(["journalctl", f"--directory={out}", "-o", "export", "--no-pager"],
                             capture_output=True, text=True).stdout
    assert "refused" not in entries


def test_the_uploader_verifies_the_log_host(upload_conf, tmp_path):
    """A log host whose certificate the configured CA did not sign is refused."""
    port = free_port()
    other = tmp_path / "other"
    other.mkdir()
    make_pki(other)
    out = tmp_path / "remote"
    out.mkdir()
    remote = start_remote(port, other, out)
    try:
        src = make_source_journal(tmp_path, "impostor")
        upload = subprocess.run(
            [str(UPLOAD), f"--url=https://127.0.0.1:{port}", f"--key={upload_conf['ServerKeyFile']}",
             f"--cert={upload_conf['ServerCertificateFile']}", f"--trust={upload_conf['TrustedCertificateFile']}",
             f"--file={src}", f"--save-state={tmp_path / 'state'}", "--follow=no"],
            capture_output=True, text=True, timeout=60)
    finally:
        remote.terminate()
        remote.wait(timeout=10)
    assert upload.returncode != 0
    assert "impostor" not in subprocess.run(["journalctl", f"--directory={out}", "-o", "export", "--no-pager"],
                                            capture_output=True, text=True).stdout


def test_an_unreachable_log_host_fails_fast_and_only_logs(upload_conf, tmp_path):
    src = make_source_journal(tmp_path, "unreachable")
    started = time.monotonic()
    upload = subprocess.run(
        [str(UPLOAD), f"--url=https://127.0.0.1:{free_port()}", f"--key={upload_conf['ServerKeyFile']}",
         f"--cert={upload_conf['ServerCertificateFile']}", f"--trust={upload_conf['TrustedCertificateFile']}",
         f"--file={src}", f"--save-state={tmp_path / 'state'}", "--follow=no"],
        capture_output=True, text=True, timeout=120)
    assert upload.returncode != 0
    assert time.monotonic() - started < 60
    assert re.search(r"(?i)upload|connect|refused", upload.stderr)
