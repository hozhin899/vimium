#!/usr/bin/env python3
"""
Remove the Chrome Web Store build of Vimium and keep only your own
(unpacked) Vimium active.

Usage:
  ./block_store_vimium.py --browser chrome --repo ~/src/vimium
  ./block_store_vimium.py --browser all --purge-data     # also wipe store copy's on-disk data
  ./block_store_vimium.py --browser chrome --undo        # remove the block again
"""
import argparse
import json
import subprocess
import sys
import tempfile
from pathlib import Path

VIMIUM_STORE_ID = "dbepggeogbaibhgnhhndojpepiihcmeb"
POLICY_FILE = "block-store-vimium.json"
HOME = Path.home()

# name: (managed policy dir, profile root, process name)
BROWSERS = {
    "chrome":   (Path("/etc/opt/chrome/policies/managed"),
                 HOME / ".config/google-chrome", "chrome"),
    "chromium": (Path("/etc/chromium/policies/managed"),
                 HOME / ".config/chromium", "chromium"),
    "brave":    (Path("/etc/brave/policies/managed"),
                 HOME / ".config/BraveSoftware/Brave-Browser", "brave"),
    "edge":     (Path("/etc/opt/edge/policies/managed"),
                 HOME / ".config/microsoft-edge", "msedge"),
}

PURGE_SUBDIRS = ["Extensions", "Local Extension Settings",
                 "Sync Extension Settings", "Managed Extension Settings",
                 "Extension State"]


def sudo(*cmd):
    subprocess.run(["sudo", *cmd], check=True)


def is_running(proc):
    return subprocess.run(["pgrep", "-x", proc],
                          capture_output=True).returncode == 0


def check_repo(repo):
    manifest = Path(repo).expanduser() / "manifest.json"
    if not manifest.is_file():
        sys.exit(f"error: {manifest} not found. Point --repo at the folder "
                 "containing your Vimium manifest.json")
    name = json.loads(manifest.read_text()).get("name", "?")
    print(f"[ok] repo found: {manifest.parent} (extension name: {name})")


def warn_conflicts(policy_dir):
    if not policy_dir.is_dir():
        return
    for f in policy_dir.glob("*.json"):
        if f.name == POLICY_FILE:
            continue
        try:
            if "ExtensionSettings" in f.read_text():
                print(f"[warn] {f} also sets ExtensionSettings; policy files "
                      "are merged alphabetically and the later one wins, so "
                      "merge the block into that file if Vimium reappears.")
        except OSError:
            pass


def install_policy(policy_dir):
    policy = {"ExtensionSettings": {
        VIMIUM_STORE_ID: {"installation_mode": "blocked"}}}
    with tempfile.NamedTemporaryFile("w", suffix=".json", delete=False) as t:
        json.dump(policy, t, indent=2)
        tmp = t.name
    dest = policy_dir / POLICY_FILE
    sudo("install", "-D", "-m", "644", tmp, str(dest))
    Path(tmp).unlink()
    print(f"[ok] wrote policy {dest}")


def remove_policy(policy_dir):
    dest = policy_dir / POLICY_FILE
    if dest.exists():
        sudo("rm", "-f", str(dest))
        print(f"[ok] removed {dest}")
    else:
        print(f"[skip] {dest} does not exist")


def purge_data(profile_root):
    if not profile_root.is_dir():
        return
    import shutil
    count = 0
    for profile in profile_root.iterdir():
        if not profile.is_dir():
            continue
        for sub in PURGE_SUBDIRS:
            target = profile / sub / VIMIUM_STORE_ID
            if target.exists():
                shutil.rmtree(target, ignore_errors=True)
                count += 1
                print(f"[ok] deleted {target}")
    if not count:
        print("[skip] no store Vimium data found on disk")


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--browser", default="chrome",
                    choices=[*BROWSERS, "all"])
    ap.add_argument("--repo", help="path to your Vimium repo (sanity check)")
    ap.add_argument("--purge-data", action="store_true",
                    help="also delete the store copy's files/settings on disk")
    ap.add_argument("--undo", action="store_true",
                    help="remove the block policy")
    args = ap.parse_args()

    if args.repo:
        check_repo(args.repo)

    names = list(BROWSERS) if args.browser == "all" else [args.browser]
    for name in names:
        policy_dir, profile_root, proc = BROWSERS[name]
        if args.browser == "all" and not profile_root.is_dir():
            continue  # browser not in use
        print(f"\n== {name} ==")
        if args.undo:
            remove_policy(policy_dir)
            continue
        warn_conflicts(policy_dir)
        install_policy(policy_dir)
        if args.purge_data:
            if is_running(proc):
                print(f"[warn] {name} is running; close it fully, then rerun "
                      "with --purge-data (skipping purge)")
            else:
                purge_data(profile_root)

    if not args.undo:
        print("\nDone. Restart the browser, then:\n"
              "  1. chrome://policy -> click 'Reload policies' (check ExtensionSettings is listed)\n"
              "  2. chrome://extensions -> enable Developer mode -> 'Load unpacked' -> your repo folder\n"
              "  3. Confirm only one Vimium is listed, and it shows 'Errors'/'Details' with a local path.")


if __name__ == "__main__":
    main()
