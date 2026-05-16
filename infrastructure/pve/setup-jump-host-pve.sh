#!/usr/bin/env bash
# ADR-0013 (M5.8) — Proxmox host as password-auth SSH ProxyJump gateway.
#
# What this script does (idempotent — safe to re-run):
#   1. Creates a single static user `vlab` (no home shell, no key auth).
#      That's the only thing the user types at `ssh vlab@gateway`.
#   2. Installs /usr/local/bin/vlab-pam-auth.sh — PAM exec script that POSTs
#      the typed password to backend /api/gateway/auth.
#   3. Installs /usr/local/bin/vlab-jump.sh — ForceCommand wrapper. After PAM
#      passes, this resolves the right kit from backend, exec's `ssh -i
#      backend_key pi@kit`. User never sees a SV14 shell.
#   4. Patches /etc/pam.d/sshd to call the PAM script ONLY when user = vlab.
#      Other accounts (root, admin) still use the standard sshd PAM stack.
#   5. Installs sshd_config.d/99-vju-jump.conf with a Match block locking
#      vlab to password-only + ForceCommand + no TTY/agent/X11.
#   6. Reloads sshd.
#
# Run as root on the Proxmox host:
#     sudo bash setup-jump-host-pve.sh
#
# Required env (or args):
#     BACKEND_URL            e.g. https://backend.bcse-vju.com (internal)
#     GATEWAY_SHARED_SECRET  must match backend's value
#     KIT_KEY_PATH           path to backend ed25519 priv key for kit access
#                            (defaults to /etc/vlab/backend_ed25519)

set -euo pipefail

if [[ $EUID -ne 0 ]]; then
    echo "Must run as root" >&2
    exit 1
fi
log() { echo "[setup-jump-pve] $*"; }
die() { echo "[setup-jump-pve] FATAL: $*" >&2; exit 1; }

: "${BACKEND_URL:?must set BACKEND_URL (e.g. https://backend.bcse-vju.com)}"
: "${GATEWAY_SHARED_SECRET:?must set GATEWAY_SHARED_SECRET (matches backend .env)}"
KIT_KEY_PATH="${KIT_KEY_PATH:-/etc/vlab/backend_ed25519}"
# Space-separated `ip:port` list of kits the vlab user is allowed to forward
# TCP to (used by `ssh -J vlab@gw kit-user@kit-ip`). Default = pilot kit
# pool on the same LAN as the PVE host. Override with KIT_POOL=... env.
KIT_POOL="${KIT_POOL:-192.168.2.93:22 192.168.2.100:22 192.168.2.121:22}"

# ------------------------------------------------------------------------- #
# 1. Tools
# ------------------------------------------------------------------------- #
log "1/7 — ensure curl + jq are installed"
if ! command -v jq >/dev/null 2>&1 || ! command -v curl >/dev/null 2>&1; then
    # Try install with existing apt cache first — PVE hosts often have the
    # enterprise repo (which fails apt-get update without a subscription),
    # so we only fall back to a network refresh if the install itself fails.
    if ! apt-get install -y -qq curl jq 2>/dev/null; then
        # Refresh only the Debian + pve-no-subscription lists, ignoring any
        # enterprise repo errors.
        apt-get update -o Acquire::AllowInsecureRepositories=true \
            -o APT::Update::Error-Mode=any 2>/dev/null || true
        apt-get install -y -qq curl jq
    fi
fi

# ------------------------------------------------------------------------- #
# 2. Static vlab user
# ------------------------------------------------------------------------- #
log "2/7 — ensure vlab user + /etc/vlab dir"
if ! id vlab >/dev/null 2>&1; then
    useradd \
        --system \
        --shell /bin/bash \
        --home-dir /var/lib/vlab \
        --create-home \
        --comment "VJU Lab Portal gateway (ADR-0013)" \
        vlab
    # Random password unset PAM_authtok — but sshd's pam_unix would normally
    # check /etc/shadow. Set it to '!' (locked) so only our pam_exec can pass.
    passwd -l vlab >/dev/null
fi
install -d -m 750 -o root -g vlab /etc/vlab
install -d -m 700 -o vlab -g vlab /var/lib/vlab

# Drop env file with the shared secret + backend URL (mode 640, root:vlab).
cat > /etc/vlab/gateway.env <<EOF
BACKEND_URL=${BACKEND_URL}
GATEWAY_SHARED_SECRET=${GATEWAY_SHARED_SECRET}
KIT_KEY_PATH=${KIT_KEY_PATH}
EOF
chown root:vlab /etc/vlab/gateway.env
chmod 640 /etc/vlab/gateway.env

# ------------------------------------------------------------------------- #
# 3. PAM exec script — POST password to backend
# ------------------------------------------------------------------------- #
log "3/7 — install /usr/local/bin/vlab-pam-auth.sh"
cat > /usr/local/bin/vlab-pam-auth.sh <<'PAMSH'
#!/bin/bash
# Called by pam_exec.so with expose_authtok — password is on stdin, $PAM_USER
# is the requested account, $PAM_RHOST is the client IP. Exits 0 on success,
# non-zero to deny.
set -u
. /etc/vlab/gateway.env

PASSWORD="$(cat || true)"
[[ -z "${PASSWORD}" ]] && exit 1
[[ "${PAM_USER:-}" != "vlab" ]] && exit 1  # belt + suspenders — only vlab

CLIENT_IP="${PAM_RHOST:-unknown}"
RESP=$(curl -sS --max-time 3 \
    -H 'Content-Type: application/json' \
    -H "X-Gateway-Secret: ${GATEWAY_SHARED_SECRET}" \
    -d "$(jq -nc --arg u "${PAM_USER}" --arg p "${PASSWORD}" --arg ip "${CLIENT_IP}" \
        '{username:$u, password:$p, client_ip:$ip}')" \
    "${BACKEND_URL%/}/api/gateway/auth" 2>/dev/null) || exit 1

echo "$RESP" | jq -e '.ok == true' >/dev/null || exit 1
exit 0
PAMSH
chmod 755 /usr/local/bin/vlab-pam-auth.sh

# ------------------------------------------------------------------------- #
# 4. ForceCommand wrapper — resolve target + ssh into kit
# ------------------------------------------------------------------------- #
log "4/7 — install /usr/local/bin/vlab-jump.sh"
cat > /usr/local/bin/vlab-jump.sh <<'JUMPSH'
#!/bin/bash
# ForceCommand wrapper. PAM has already verified the password right before
# this runs, so the backend has the user's session marked last_auth_at=now.
# We ask backend which kit this session targets, then exec ssh into it.
set -u
. /etc/vlab/gateway.env

CLIENT_IP="${SSH_CLIENT%% *}"

RESP=$(curl -sS --max-time 5 \
    -H 'Content-Type: application/json' \
    -H "X-Gateway-Secret: ${GATEWAY_SHARED_SECRET}" \
    -d "$(jq -nc --arg u "${USER:-vlab}" --arg ip "${CLIENT_IP}" \
        '{username:$u, client_ip:$ip}')" \
    "${BACKEND_URL%/}/api/gateway/resolve-target" 2>/dev/null) || {
        echo "Gateway error: không lấy được thông tin kit (backend không trả lời)." >&2
        exit 1
    }

OK=$(echo "$RESP" | jq -r 'if has("target_host") then "yes" else "no" end' 2>/dev/null)
if [[ "$OK" != "yes" ]]; then
    REASON=$(echo "$RESP" | jq -r '.detail.code // "unknown"' 2>/dev/null)
    echo "Gateway error: phiên không hợp lệ (${REASON}). Liên hệ admin nếu cần." >&2
    exit 1
fi

TARGET_HOST=$(echo "$RESP" | jq -r '.target_host')
TARGET_PORT=$(echo "$RESP" | jq -r '.target_port')
TARGET_USER=$(echo "$RESP" | jq -r '.target_user')
SESSION_ID=$(echo "$RESP" | jq -r '.session_id')

# Notify backend that the actual shell session is starting — backend uses
# this to record PID + pty so the janitor can kill on expiry.
PTY="$(tty 2>/dev/null || echo '')"
curl -sS --max-time 3 \
    -H 'Content-Type: application/json' \
    -H "X-Gateway-Secret: ${GATEWAY_SHARED_SECRET}" \
    -d "$(jq -nc --arg s "$SESSION_ID" --argjson p "$$" --arg pty "$PTY" --arg ip "$CLIENT_IP" \
        '{session_id:$s, pid:$p, pty_path:$pty, client_ip:$ip}')" \
    "${BACKEND_URL%/}/api/gateway/session-start" >/dev/null 2>&1 || true

# Trap exit to flush session-end
cleanup() {
    curl -sS --max-time 3 \
        -H 'Content-Type: application/json' \
        -H "X-Gateway-Secret: ${GATEWAY_SHARED_SECRET}" \
        -d "$(jq -nc --arg s "$SESSION_ID" '{session_id:$s, bytes_in:0, bytes_out:0}')" \
        "${BACKEND_URL%/}/api/gateway/session-end" >/dev/null 2>&1 || true
}
trap cleanup EXIT

# Hand off — `exec` makes the ssh process replace this script, so the
# kill -HUP <pid> from the janitor reaches the actual SSH connection.
exec ssh \
    -i "${KIT_KEY_PATH}" \
    -p "${TARGET_PORT}" \
    -o StrictHostKeyChecking=accept-new \
    -o UserKnownHostsFile=/var/lib/vlab/.ssh/known_hosts \
    -o ServerAliveInterval=30 \
    "${TARGET_USER}@${TARGET_HOST}"
JUMPSH
chmod 755 /usr/local/bin/vlab-jump.sh
install -d -m 700 -o vlab -g vlab /var/lib/vlab/.ssh

# ------------------------------------------------------------------------- #
# 5. Patch /etc/pam.d/sshd — conditional pam_exec only for user vlab
# ------------------------------------------------------------------------- #
log "5/7 — patch /etc/pam.d/sshd with conditional pam_exec (vlab only)"
PAM_FILE=/etc/pam.d/sshd
MARKER_BEGIN="# VJU-LAB-PORTAL-VLAB-BEGIN"
MARKER_END="# VJU-LAB-PORTAL-VLAB-END"
if ! grep -q "$MARKER_BEGIN" "$PAM_FILE"; then
    cp -a "$PAM_FILE" "${PAM_FILE}.bak.$(date +%Y%m%d%H%M%S)"
    # Prepend the conditional block. pam_succeed_if returns success if the
    # condition holds; success=N means skip the next N rules.
    {
        echo "$MARKER_BEGIN"
        echo "# Inserted by setup-jump-host-pve.sh (ADR-0013)."
        echo "# If user != vlab → skip the next rule (fall through to default stack)."
        echo "# If user = vlab  → run pam_exec; on success skip past default stack."
        echo "auth [success=1 default=ignore] pam_succeed_if.so user != vlab quiet_success"
        echo "auth required                   pam_exec.so expose_authtok /usr/local/bin/vlab-pam-auth.sh"
        echo "auth [success=done default=ignore] pam_succeed_if.so user = vlab quiet_success"
        echo "$MARKER_END"
        cat "$PAM_FILE"
    } > "${PAM_FILE}.new"
    mv "${PAM_FILE}.new" "$PAM_FILE"
    chmod 644 "$PAM_FILE"
fi

# ------------------------------------------------------------------------- #
# 6. sshd Match block for vlab user
# ------------------------------------------------------------------------- #
log "6/7 — install /etc/ssh/sshd_config.d/99-vju-jump.conf"

# Verify global UsePAM is on (Debian/PVE default), otherwise our pam_exec
# block in /etc/pam.d/sshd is never consulted.
if ! sshd -T 2>/dev/null | grep -qx "usepam yes"; then
    log "  WARNING — global UsePAM is OFF. Adding 'UsePAM yes' to /etc/ssh/sshd_config"
    if ! grep -qE "^\s*UsePAM\s+yes" /etc/ssh/sshd_config; then
        echo "UsePAM yes" >> /etc/ssh/sshd_config
    fi
fi
cat > /etc/ssh/sshd_config.d/99-vju-jump.conf <<EOF
# VJU Lab Portal — gateway user (ADR-0013).
# Static account 'vlab': password-auth via PAM → backend, no key, no shell,
# no TTY, no agent fwd, no X11. ForceCommand routes to the assigned kit
# using a backend-held key.
Match User vlab
    PasswordAuthentication yes
    PubkeyAuthentication no
    AuthenticationMethods password
    AuthorizedKeysFile /dev/null
    PermitTTY yes
    # Two supported UX paths:
    #   A. `ssh -J vlab@gw kit-user@kit-ip` — direct-tcpip via PermitOpen
    #   B. `ssh vlab@gw`                    — ForceCommand wrapper auto-jumps
    AllowTcpForwarding yes
    GatewayPorts no
    X11Forwarding no
    AllowAgentForwarding no
    PermitOpen ${KIT_POOL}
    ForceCommand /usr/local/bin/vlab-jump.sh
EOF

# ------------------------------------------------------------------------- #
# 7. sshd -t + reload
# ------------------------------------------------------------------------- #
log "7/7 — sshd -t && reload"
sshd -t || die "sshd config failed validation — refusing to reload"
if systemctl reload ssh 2>/dev/null; then
    log "  reloaded ssh.service"
elif systemctl reload sshd 2>/dev/null; then
    log "  reloaded sshd.service"
else
    log "  WARNING — couldn't reload via systemctl; check unit name manually"
fi

log "DONE."
log ""
log "Verify:"
log "  ssh -p \$JUMP_HOST_PUBLIC_PORT vlab@<this-host>     # asks for portal password"
log "  cat /etc/pam.d/sshd | head -10                       # confirms inserted block"
log "  sudo sshd -T -C user=vlab | grep -E '(forcecommand|usepam)'"
log ""
log "Rollback PAM:"
log "  ls /etc/pam.d/sshd.bak.*"
log "  cp /etc/pam.d/sshd.bak.<timestamp> /etc/pam.d/sshd && systemctl reload ssh"
