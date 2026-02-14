"""Kill the process listening on a given port.

Safe, scoped utility for the coding agent to free occupied ports mid-session.
Only kills the specific process bound to the requested port.

Usage:
    python kill_port.py <port>

Port must be between 1024 and 65535 (no system ports).
"""

import platform
import subprocess
import sys


def kill_port(port: int) -> None:
    """Find and kill the process listening on the given port."""
    if platform.system() == "Windows":
        result = subprocess.run(
            ["netstat", "-ano"],
            capture_output=True,
            text=True,
        )
        for line in result.stdout.splitlines():
            if f":{port}" in line and "LISTENING" in line:
                pid = line.strip().split()[-1]
                subprocess.run(
                    ["taskkill", "/F", "/PID", pid],
                    capture_output=True,
                )
                print(f"Killed PID {pid} on port {port}")
                return
    else:
        result = subprocess.run(
            ["lsof", "-ti", f":{port}"],
            capture_output=True,
            text=True,
        )
        if result.stdout.strip():
            pid = result.stdout.strip().split("\n")[0]
            subprocess.run(["kill", "-9", pid], capture_output=True)
            print(f"Killed PID {pid} on port {port}")
            return

    print(f"No process found on port {port}")


if __name__ == "__main__":
    if len(sys.argv) != 2 or not sys.argv[1].isdigit():
        print("Usage: python kill_port.py <port>")
        sys.exit(1)
    port_num = int(sys.argv[1])
    if not (1024 <= port_num <= 65535):
        print("Port must be between 1024 and 65535")
        sys.exit(1)
    kill_port(port_num)
