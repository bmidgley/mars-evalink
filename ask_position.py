#!/usr/bin/env python3
"""
Standalone script: fetch stalenode list from evalink and run
meshtastic --request-position --dest <node> for each node.
No shell is used; node numbers are passed as separate arguments (no escape issues).
"""
import subprocess
import urllib.request

STALENODE_URL = "https://evalink.archresearch.net/stalenode?delay=1"


def main():
    try:
        with urllib.request.urlopen(STALENODE_URL) as resp:
            body = resp.read().decode("utf-8").strip()
    except Exception as e:
        print(f"Failed to fetch stalenode: {e}")
        return 1
    if not body:
        print("No stale nodes found")
        return 0
    nodes = [s.strip() for s in body.split(",") if s.strip()]
    if not nodes:
        return 0
    for node in nodes:
        # Pass node as separate argument so leading ! or other chars need no escaping
        cmd = ["meshtastic", "--request-position", "--dest", node]
        try:
            subprocess.run(cmd, check=False)
        except FileNotFoundError:
            print(f"meshtastic not found; skipped --dest {node}")
        except Exception as e:
            print(f"Error running meshtastic --dest {node}: {e}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
