#!/usr/bin/env python3
"""
List USB serial ports (/dev/ttyACM*, /dev/ttyUSB*) and how they map to lsusb entries.

Each tty device sits under a USB interface in sysfs; walking up to the parent
with idVendor/idProduct yields busnum and devnum, which match "Bus NNN Device MMM"
in lsusb output. Stable names also appear under /dev/serial/by-id/.
"""
from __future__ import annotations

import glob
import re
import subprocess
import sys
from pathlib import Path


def usb_device_for_tty(tty_name: str) -> Path | None:
    """Return sysfs path of the USB device node for a tty (e.g. ttyACM0)."""
    sysfs_tty = Path("/sys/class/tty") / tty_name
    if not sysfs_tty.exists():
        return None
    current = sysfs_tty.resolve()
    while current != Path("/"):
        if (current / "idVendor").is_file():
            return current
        current = current.parent
    return None


def read_sysfs_text(path: Path) -> str | None:
    if path.is_file():
        return path.read_text(encoding="utf-8", errors="replace").strip()
    return None


def usb_port_id(usb_sysfs: Path) -> str | None:
    """USB topology port, e.g. '3-2' from .../usb3/3-2."""
    name = usb_sysfs.name
    if re.fullmatch(r"\d+-\d+(\.\d+)*", name):
        return name
    return None


def parse_lsusb() -> dict[tuple[int, int], str]:
    """Map (bus, device) -> full lsusb line."""
    try:
        out = subprocess.check_output(["lsusb"], text=True, stderr=subprocess.DEVNULL)
    except (FileNotFoundError, subprocess.CalledProcessError):
        return {}
    mapping: dict[tuple[int, int], str] = {}
    for line in out.splitlines():
        m = re.match(r"Bus (\d+) Device (\d+): (.+)", line)
        if m:
            mapping[(int(m.group(1)), int(m.group(2)))] = line
    return mapping


def by_id_links() -> dict[str, list[str]]:
    """tty name -> list of /dev/serial/by-id symlink basenames."""
    result: dict[str, list[str]] = {}
    by_id = Path("/dev/serial/by-id")
    if not by_id.is_dir():
        return result
    for link in sorted(by_id.iterdir()):
        if not link.is_symlink():
            continue
        target = Path(os_readlink(link))
        tty = target.name
        result.setdefault(tty, []).append(link.name)
    return result


def os_readlink(path: Path) -> str:
    return path.readlink()


def collect_serial_ttys() -> list[str]:
    names: list[str] = []
    for pattern in ("/dev/ttyACM*", "/dev/ttyUSB*"):
        for path in sorted(glob.glob(pattern)):
            names.append(Path(path).name)
    return names


def main() -> int:
    lsusb_map = parse_lsusb()
    by_id = by_id_links()
    ttys = collect_serial_ttys()

    if not ttys:
        print("No /dev/ttyACM* or /dev/ttyUSB* devices found.", file=sys.stderr)
        return 1

    for tty in ttys:
        dev = f"/dev/{tty}"
        usb = usb_device_for_tty(tty)
        print(f"{dev}")
        if usb is None:
            print("  (not a USB serial device)")
            print()
            continue

        bus = int(read_sysfs_text(usb / "busnum") or "0")
        devnum = int(read_sysfs_text(usb / "devnum") or "0")
        vid = read_sysfs_text(usb / "idVendor")
        pid = read_sysfs_text(usb / "idProduct")
        manufacturer = read_sysfs_text(usb / "manufacturer")
        product = read_sysfs_text(usb / "product")
        serial = read_sysfs_text(usb / "serial")
        port = usb_port_id(usb)

        print(f"  sysfs:     {usb}")
        if port:
            print(f"  usb port:  {port}")
        print(f"  vendor:product: {vid}:{pid}")
        if manufacturer or product:
            desc = " ".join(x for x in (manufacturer, product) if x)
            print(f"  description: {desc}")
        if serial:
            print(f"  serial:    {serial}")

        lsusb_line = lsusb_map.get((bus, devnum))
        if lsusb_line:
            print(f"  lsusb:     {lsusb_line}")
        else:
            print(f"  lsusb:     Bus {bus:03d} Device {devnum:03d} (no matching lsusb line)")

        ids = by_id.get(tty, [])
        if ids:
            print("  by-id:")
            for name in ids:
                print(f"    /dev/serial/by-id/{name}")
        print()

    return 0


if __name__ == "__main__":
    sys.exit(main())
