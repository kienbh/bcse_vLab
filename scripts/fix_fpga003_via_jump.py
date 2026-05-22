"""Recover FPGA 003 through the FPGA 001 jump host.

FPGA 003 (MAC 00:0a:35:17:98:70) is stuck on static 192.168.2.143, which is
also claimed by another machine (MAC c8-cd-55-5e-f0-8b) — an IP conflict.
From this PC, .143 ARP-resolves to the wrong machine; from FPGA 001 it
resolves to the real FPGA 003. So we SSH FPGA 003 *through* FPGA 001.

This uploads the network recovery script to FPGA 003 and runs it detached
(switch eth0 to NetworkManager DHCP, then reboot). After it reboots, FPGA 003
leaves .143 and picks up a clean DHCP lease.

Run:  python scripts/fix_fpga003_via_jump.py
"""
from __future__ import annotations

import io
import sys
import time
from pathlib import Path

import paramiko

REPO = Path(__file__).resolve().parents[1]
PRIV = REPO / "infrastructure" / "sv14" / "secrets" / "portal_admin_ed25519"
RECOVER = REPO / "scripts" / "recover_kv260_network.sh"

JUMP_IP = "192.168.2.93"      # FPGA 001
JUMP_USER = "ubuntu001"
TARGET_IP = "192.168.2.143"   # FPGA 003 (conflicted)
TARGET_USER = "ubuntu003"
SUDO_PASS = "abc135"

RUNNER = (
    "#!/bin/bash\n"
    "exec >/var/log/recover.log 2>&1\n"
    "sleep 5\n"
    "bash /tmp/recover.sh\n"
    "sleep 3\n"
    "systemctl enable NetworkManager\n"
    "sleep 2\n"
    "reboot\n"
)


def main() -> int:
    key = paramiko.Ed25519Key.from_private_key(io.StringIO(PRIV.read_text()))

    for attempt in range(1, 11):
        jump = None
        try:
            jump = paramiko.SSHClient()
            jump.set_missing_host_key_policy(paramiko.AutoAddPolicy())
            jump.connect(JUMP_IP, username=JUMP_USER, pkey=key, timeout=12,
                         allow_agent=False, look_for_keys=False)

            # Pin .143 -> FPGA 003's MAC in FPGA 001's ARP table so the
            # direct-tcpip channel reliably reaches FPGA 003 and not the
            # other machine squatting the same address.
            ji, jo, _ = jump.exec_command(
                'sudo -S -p "" ip neigh replace 192.168.2.143 '
                "lladdr 00:0a:35:17:98:70 dev eth0")
            ji.write(SUDO_PASS + "\n")
            ji.flush()
            jo.channel.recv_exit_status()

            chan = jump.get_transport().open_channel(
                "direct-tcpip", (TARGET_IP, 22), ("127.0.0.1", 0), timeout=10)
            tgt = paramiko.SSHClient()
            tgt.set_missing_host_key_policy(paramiko.AutoAddPolicy())
            tgt.connect(TARGET_IP, username=TARGET_USER, pkey=key, sock=chan,
                        timeout=12, allow_agent=False, look_for_keys=False)
            print(f"attempt {attempt}: SSH FPGA 003 via jump — OK")

            sftp = tgt.open_sftp()
            sftp.put(str(RECOVER), "/tmp/recover.sh")
            with sftp.open("/tmp/run_recover.sh", "w") as f:
                f.write(RUNNER)
            sftp.chmod("/tmp/run_recover.sh", 0o755)
            sftp.close()

            i, o, _ = tgt.exec_command(
                'sudo -S -p "" systemd-run --unit=kv260-recover '
                "/bin/bash /tmp/run_recover.sh")
            i.write(SUDO_PASS + "\n")
            i.flush()
            rc = o.channel.recv_exit_status()
            tgt.close()
            print(f"FPGA 003 recovery+reboot scheduled (rc={rc}).")
            print("It will switch to DHCP and reboot in ~10s.")
            print("Then run a full subnet scan to find its new IP.")
            return 0
        except Exception as ex:
            print(f"attempt {attempt}: {type(ex).__name__} — {ex}")
            time.sleep(4)
        finally:
            if jump is not None:
                try:
                    jump.close()
                except Exception:
                    pass

    print("FAILED after 10 attempts — the .143 IP conflict is blocking even "
          "the jump route. Recover FPGA 003 from its physical console instead.")
    return 1


if __name__ == "__main__":
    sys.exit(main())
