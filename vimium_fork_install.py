#!/usr/bin/env python3
"""
Install your Vimium fork automatically in EVERY Brave profile, with no manual "Load unpacked".

How it works (Linux): the fork is packed into a signed .crx and registered as a Chromium
"external extension". Brave then installs it in every profile on startup. It does not use
--load-extension, which your Brave ignores.

Usage
  1. Close ALL Brave windows (check there is no background brave process).
  2. sudo python3 vimium_fork_install.py install --repo /path/to/vimium
  3. Start Brave. Open brave://extensions: the fork appears in each profile (shown as
     "Installed by your administrator" or similar, with a different ID from the store one).
  4. After every code change: repeat steps 1 and 2. Each run bumps the version (2.4.2.N) so
     Brave accepts the update.
  sudo python3 vimium_fork_install.py remove      Remove the fork registration again.

Notes
  * Run the existing `vimium_fork_setup.py block` once, so the store Vimium is removed and does
    not run beside the fork.
  * The fork has a new extension ID, so its settings start empty. Re-enter your key mappings
    once on its options page. Settings sync does not carry them over.
  * Unverified: I have not run this against your Brave. External-extension directories can
    differ between Brave builds, so the script writes to both known locations. If the fork does
    not appear, tell me the output of: ls /opt/brave.com/brave /usr/share/brave
  * Linux only. Needs openssl in PATH.
"""
import argparse
import hashlib
import json
import os
import pwd
import re
import shutil
import struct
import subprocess
import sys
import tempfile
import zipfile
from pathlib import Path

EXT_DIRS = [
    Path("/opt/brave.com/brave/extensions"),
    Path("/usr/share/brave/extensions"),
]
EXCLUDE_DIRS = {".git", "node_modules", ".githooks"}


def real_user():
    name = os.environ.get("SUDO_USER") or pwd.getpwuid(os.getuid()).pw_name
    return pwd.getpwnam(name)


def require_root():
    if os.geteuid() != 0:
        sys.exit("Run with sudo (needs to write into Brave's extension directory).")


def brave_running():
    return subprocess.run(["pgrep", "-x", "brave"], capture_output=True).returncode == 0


def varint(n):
    out = bytearray()
    while True:
        b = n & 0x7F
        n >>= 7
        if n:
            out.append(b | 0x80)
        else:
            out.append(b)
            return bytes(out)


def field(number, payload):
    return varint((number << 3) | 2) + varint(len(payload)) + payload


def ensure_key(path):
    if not path.exists():
        path.parent.mkdir(parents=True, exist_ok=True)
        subprocess.run(
            ["openssl", "genrsa", "-out", str(path), "2048"],
            check=True, capture_output=True,
        )
        os.chmod(path, 0o600)
    pub = subprocess.run(
        ["openssl", "rsa", "-in", str(path), "-pubout", "-outform", "DER"],
        check=True, capture_output=True,
    ).stdout
    return pub


def extension_id(pub_der):
    crx_id = hashlib.sha256(pub_der).digest()[:16]
    return crx_id, "".join(chr(ord("a") + int(c, 16)) for c in crx_id.hex())


def stage_zip(repo, version):
    """Zip the repo with the manifest version replaced by `version`."""
    tmp = Path(tempfile.mkdtemp()) / "fork.zip"
    pattern = re.compile(r'("version"\s*:\s*")[0-9.]+(")')
    with zipfile.ZipFile(tmp, "w", zipfile.ZIP_DEFLATED) as z:
        for root, dirs, files in os.walk(repo):
            dirs[:] = [d for d in dirs if d not in EXCLUDE_DIRS]
            for f in files:
                full = Path(root) / f
                rel = full.relative_to(repo).as_posix()
                if rel == "manifest.json":
                    text = full.read_text(encoding="utf-8")
                    text, n = pattern.subn(rf"\g<1>{version}\g<2>", text, count=1)
                    if n != 1:
                        sys.exit("Could not find the version field in manifest.json.")
                    z.writestr(rel, text)
                else:
                    z.write(full, rel)
    return tmp.read_bytes()


def build_crx(zip_bytes, key_path, pub_der, crx_id):
    signed_data = field(1, crx_id)
    payload = (
        b"CRX3 SignedData\x00" + struct.pack("<I", len(signed_data)) + signed_data + zip_bytes
    )
    signature = subprocess.run(
        ["openssl", "dgst", "-sha256", "-sign", str(key_path)],
        input=payload, check=True, capture_output=True,
    ).stdout
    proof = field(1, pub_der) + field(2, signature)
    header = field(2, proof) + field(10000, signed_data)
    return b"Cr24" + struct.pack("<II", 3, len(header)) + header + zip_bytes


def cmd_install(args):
    require_root()
    if brave_running():
        sys.exit("Brave is running. Close ALL Brave windows and background processes first.")
    repo = Path(args.repo).expanduser().resolve()
    manifest = repo / "manifest.json"
    if not manifest.exists():
        sys.exit(f"No manifest.json in {repo}.")
    m = re.search(r'"version"\s*:\s*"(\d+(?:\.\d+){0,2})"', manifest.read_text(encoding="utf-8"))
    if not m:
        sys.exit("Could not read the version from manifest.json.")
    base = m.group(1)

    user = real_user()
    data_dir = Path(user.pw_dir) / ".local/share/vimium-fork"
    data_dir.mkdir(parents=True, exist_ok=True)
    state_path = data_dir / "state.json"
    state = json.loads(state_path.read_text()) if state_path.exists() else {"build": 0}
    state["build"] += 1
    version = f"{base}.{state['build']}"

    key_path = data_dir / "key.pem"
    pub_der = ensure_key(key_path)
    crx_id, ext_id = extension_id(pub_der)

    crx_bytes = build_crx(stage_zip(repo, version), key_path, pub_der, crx_id)
    crx_path = data_dir / "vimium-fork.crx"
    crx_path.write_bytes(crx_bytes)
    state_path.write_text(json.dumps(state))
    for p in (data_dir, key_path, crx_path, state_path):
        os.chown(p, user.pw_uid, user.pw_gid)
    os.chmod(crx_path, 0o644)

    for d in EXT_DIRS:
        d.mkdir(parents=True, exist_ok=True)
        (d / f"{ext_id}.json").write_text(json.dumps({
            "external_crx": str(crx_path),
            "external_version": version,
        }, indent=2))
        os.chmod(d / f"{ext_id}.json", 0o644)

    print(f"Fork packed as version {version}, extension ID {ext_id}")
    print(f"CRX: {crx_path}")
    print("Start Brave and check brave://extensions in each profile.")


def cmd_remove(_args):
    require_root()
    user = real_user()
    key_path = Path(user.pw_dir) / ".local/share/vimium-fork/key.pem"
    if not key_path.exists():
        sys.exit("No key found, nothing to remove.")
    _, ext_id = extension_id(ensure_key(key_path))
    for d in EXT_DIRS:
        f = d / f"{ext_id}.json"
        if f.exists():
            f.unlink()
            print(f"Removed {f}")
    print("Restart Brave. Remove the extension from brave://extensions if it remains.")


def main():
    if sys.platform != "linux":
        sys.exit("Linux only.")
    if shutil.which("openssl") is None:
        sys.exit("openssl is required.")
    parser = argparse.ArgumentParser(description=__doc__.split("\n\n")[0])
    sub = parser.add_subparsers(dest="cmd", required=True)
    p = sub.add_parser("install")
    p.add_argument("--repo", required=True, help="path to your vimium fork")
    sub.add_parser("remove")
    args = parser.parse_args()
    cmd_install(args) if args.cmd == "install" else cmd_remove(args)


if __name__ == "__main__":
    main()
