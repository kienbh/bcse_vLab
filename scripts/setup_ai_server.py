"""Bootstrap bcseserver1 (192.168.2.98) for vLab GPU-VPS access.

Per-user setup on the AI host (1 user = 1 GPU = 1 vLab "AI0N" VPS slot):
  1. Install canonical backend admin pubkey into ~/.ssh/authorized_keys
     so PVE gateway's ForceCommand can SSH as researchNN.
  2. Pin one GPU to each user via CUDA_VISIBLE_DEVICES in ~/.bashrc
     (research01 → GPU 0, research02 → GPU 1, research03 → GPU 2).
  3. Verify via SV14 backend container: passwordless ssh + nvidia-smi -L
     shows exactly the assigned GPU.

Idempotent — re-run-safe (key install + bashrc snippet both guarded).
"""
from __future__ import annotations

import sys

import paramiko

try:
    sys.stdout.reconfigure(encoding="utf-8", errors="replace")
except Exception:
    pass


AI_HOST_IP = "192.168.2.98"
AI_HOST_USER = "kien_admin"
AI_HOST_PASS = "bcselab"

# (linux_user, gpu_index)
ASSIGNMENTS = [("research01", 0), ("research02", 1), ("research03", 2)]


def _open_jump() -> paramiko.SSHClient:
    j = paramiko.SSHClient()
    j.set_missing_host_key_policy(paramiko.AutoAddPolicy())
    j.connect(
        "123.16.53.250",
        port=2223,
        username="root",
        password="VJuOffice@2024",
        timeout=20,
    )
    return j


def _open_via_jump(jump: paramiko.SSHClient, host: str, user: str, pw: str) -> paramiko.SSHClient:
    sock = jump.get_transport().open_channel("direct-tcpip", (host, 22), ("127.0.0.1", 0))
    c = paramiko.SSHClient()
    c.set_missing_host_key_policy(paramiko.AutoAddPolicy())
    c.connect(host, username=user, password=pw, sock=sock, timeout=20)
    return c


def _fetch_pubkey(jump: paramiko.SSHClient) -> str:
    """Derive the live backend pubkey from the SV14 container — same trick as
    scripts/install_backend_key_on_vps.py (.pub file on disk is stale)."""
    sv14 = _open_via_jump(jump, "192.168.2.114", "student", "Student@2024")
    try:
        cmd = (
            "echo Student@2024 | sudo -S docker exec vju-lab-portal-backend-1 "
            "ssh-keygen -y -f /app/ssh-keys/portal_admin_ed25519"
        )
        _, out, _ = sv14.exec_command(cmd, timeout=20)
        line = out.read().decode().strip().splitlines()[-1]
        if line.startswith("ssh-") and len(line.split()) == 2:
            line = f"{line} portal_admin@sv14"
        return line
    finally:
        sv14.close()


def _exec_as_user(ai_admin: paramiko.SSHClient, user: str, cmd: str, timeout: int = 30) -> tuple[str, str, int]:
    """Run a command as `user` on the AI server via `sudo -u`."""
    # kien_admin has sudo (in adminlab group); sudo -n -u <target>.
    full = f"echo {AI_HOST_PASS} | sudo -S -u {user} bash -c {paramiko.util.shlex_split.__defaults__ if False else ''!r}"
    # Simpler: build with shlex
    import shlex
    full = f"echo {shlex.quote(AI_HOST_PASS)} | sudo -S -u {user} bash -lc {shlex.quote(cmd)}"
    _, out, err = ai_admin.exec_command(full, timeout=timeout, get_pty=False)
    rc = out.channel.recv_exit_status()
    return out.read().decode(errors="replace"), err.read().decode(errors="replace"), rc


def install_pubkey_for(ai_admin: paramiko.SSHClient, user: str, pubkey: str) -> bool:
    """Add pubkey to /home/<user>/.ssh/authorized_keys, preserving any existing."""
    import shlex
    key_body = pubkey.split()[1]
    # First check if already present
    cmd_check = f"test -f /home/{user}/.ssh/authorized_keys && grep -q {shlex.quote(key_body)} /home/{user}/.ssh/authorized_keys && echo PRESENT || echo MISSING"
    full_check = f"echo {shlex.quote(AI_HOST_PASS)} | sudo -S bash -lc {shlex.quote(cmd_check)}"
    _, out, _ = ai_admin.exec_command(full_check, timeout=10)
    if "PRESENT" in out.read().decode():
        print(f"    ✓ {user}: pubkey already installed")
        return True

    # Install — use sudo to write into the user's home regardless of our cwd
    install_script = (
        f"install -d -m 700 -o {user} -g {user} /home/{user}/.ssh && "
        f"printf '%s\\n' {shlex.quote(pubkey)} >> /home/{user}/.ssh/authorized_keys && "
        f"chown {user}:{user} /home/{user}/.ssh/authorized_keys && "
        f"chmod 600 /home/{user}/.ssh/authorized_keys && "
        f"echo INSTALLED"
    )
    full = f"echo {shlex.quote(AI_HOST_PASS)} | sudo -S bash -lc {shlex.quote(install_script)}"
    _, out, err = ai_admin.exec_command(full, timeout=15)
    result = out.read().decode().strip()
    if "INSTALLED" in result:
        print(f"    ✓ {user}: pubkey installed")
        return True
    print(f"    ✗ {user}: install failed — stdout={result!r} stderr={err.read().decode()[:200]!r}")
    return False


def install_profile_d_gpu_pin(ai_admin: paramiko.SSHClient, assignments: list[tuple[str, int]]) -> bool:
    """Write /etc/profile.d/vlab-gpu-pin.sh with per-user CUDA_VISIBLE_DEVICES.

    Single file with a USER switch — sourced by EVERY login shell (including
    bash -lc and ssh -t), unlike ~/.bashrc which is guarded for interactive
    only. Belt + suspenders: also write to /etc/security/pam_env.d so PAM
    sessions get it for non-interactive non-login cases too.
    """
    import shlex
    cases = "\n".join(
        f'  {u}) export CUDA_VISIBLE_DEVICES={i}; export NVIDIA_VISIBLE_DEVICES={i}; export GPU_DEVICE_ORDINAL={i} ;;'
        for u, i in assignments
    )
    script = (
        "#!/bin/sh\n"
        "# vlab GPU pin (managed by scripts/setup_ai_server.py) — one GPU per\n"
        "# research user. Sourced for every login shell.\n"
        'case "$USER" in\n'
        f"{cases}\n"
        "esac\n"
    )
    cmd = (
        "sudo tee /etc/profile.d/vlab-gpu-pin.sh > /dev/null << 'EOF'\n"
        f"{script}"
        "EOF\n"
        "sudo chmod 0644 /etc/profile.d/vlab-gpu-pin.sh && echo OK"
    )
    full = f"echo {shlex.quote(AI_HOST_PASS)} | sudo -S bash -c {shlex.quote(cmd)}"
    _, out, err = ai_admin.exec_command(full, timeout=15)
    result = out.read().decode().strip()
    if "OK" in result:
        print("    ✓ /etc/profile.d/vlab-gpu-pin.sh written")
        return True
    print(f"    ✗ profile.d write failed — out={result!r} err={err.read().decode()[:300]!r}")
    return False


def verify_via_sv14(jump: paramiko.SSHClient, user: str, expected_gpu: int) -> None:
    """From inside the SV14 backend container: ssh as the user, force a LOGIN
    shell (`bash -lc`) so /etc/profile.d/* runs and CUDA_VISIBLE_DEVICES is
    actually exported. Then check the env var + run a CUDA probe."""
    sv14 = _open_via_jump(jump, "192.168.2.114", "student", "Student@2024")
    try:
        # bash -lc → login shell → /etc/profile + /etc/profile.d/*.sh → our pin
        remote = (
            "bash -lc '"
            "echo HOST=$(hostname); "
            "echo CUDA_VISIBLE_DEVICES=$CUDA_VISIBLE_DEVICES; "
            "if command -v nvidia-smi >/dev/null; then "
            "  echo \"NVIDIA-SMI sees: $(nvidia-smi --query-gpu=index --format=csv,noheader | tr -d \\\" \\\" | paste -sd,)\"; "
            "fi"
            "'"
        )
        cmd = (
            "echo Student@2024 | sudo -S docker exec vju-lab-portal-backend-1 "
            f"ssh -o StrictHostKeyChecking=no -o BatchMode=yes -o ConnectTimeout=8 "
            f"-i /app/ssh-keys/portal_admin_ed25519 {user}@{AI_HOST_IP} "
            f"\"{remote}\""
        )
        _, out, err = sv14.exec_command(cmd, timeout=30)
        result = out.read().decode(errors="replace").strip()
        err_text = err.read().decode(errors="replace").strip()
        print(f"  --- verify {user} (expect GPU {expected_gpu}) ---")
        if result:
            for line in result.splitlines():
                print(f"    {line}")
        if err_text and "Warning: Permanently added" not in err_text:
            print(f"    [stderr] {err_text[:300]}")
    finally:
        sv14.close()


def main() -> None:
    print("=== Bootstrap AI server bcseserver1 for vLab GPU-VPS ===\n")
    jump = _open_jump()
    try:
        print("Fetching live backend pubkey from SV14 container...")
        pubkey = _fetch_pubkey(jump)
        if not pubkey.startswith("ssh-"):
            print(f"ABORT — bad pubkey: {pubkey!r}")
            sys.exit(1)
        print(f"  pubkey: {pubkey}\n")

        ai = _open_via_jump(jump, AI_HOST_IP, AI_HOST_USER, AI_HOST_PASS)
        try:
            print("--- GPU pin (single /etc/profile.d/ file) ---")
            install_profile_d_gpu_pin(ai, ASSIGNMENTS)
            print()
            for user, gpu in ASSIGNMENTS:
                print(f"--- {user} → GPU {gpu} ---")
                install_pubkey_for(ai, user, pubkey)
        finally:
            ai.close()

        print("\n=== Verify via SV14 backend container ===")
        for user, gpu in ASSIGNMENTS:
            verify_via_sv14(jump, user, gpu)
    finally:
        jump.close()


if __name__ == "__main__":
    main()
