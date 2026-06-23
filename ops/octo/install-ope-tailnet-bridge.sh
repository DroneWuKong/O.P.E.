#!/usr/bin/env bash
set -euo pipefail

# Repair/replace octo-a user-level kubectl port-forwards with durable system
# bridges. This keeps old clients pinned to octo-a tailnet ports working even
# when O.P.E. pods land on worker nodes.

LISTEN_HOST="${LISTEN_HOST:-100.65.161.67}"
TARGET_HOST="${TARGET_HOST:-100.81.235.34}"
BRIDGE_BIN="${BRIDGE_BIN:-/usr/local/bin/ope-tailnet-bridge.py}"

install_bridge_bin() {
  sudo tee "$BRIDGE_BIN" >/dev/null <<'PY'
#!/usr/bin/env python3
from __future__ import annotations

import os
import socket
import threading

LISTEN_HOST = os.environ.get('LISTEN_HOST', '100.65.161.67')
LISTEN_PORT = int(os.environ.get('LISTEN_PORT', '30080'))
TARGET_HOST = os.environ.get('TARGET_HOST', '100.81.235.34')
TARGET_PORT = int(os.environ.get('TARGET_PORT', '30080'))
BUFFER = 65536


def pipe(src: socket.socket, dst: socket.socket) -> None:
    try:
        while True:
            data = src.recv(BUFFER)
            if not data:
                break
            dst.sendall(data)
    except OSError:
        pass
    finally:
        for sock in (src, dst):
            try:
                sock.shutdown(socket.SHUT_RDWR)
            except OSError:
                pass
            try:
                sock.close()
            except OSError:
                pass


def handle(client: socket.socket) -> None:
    try:
        target = socket.create_connection((TARGET_HOST, TARGET_PORT), timeout=10)
    except OSError:
        client.close()
        return
    threading.Thread(target=pipe, args=(client, target), daemon=True).start()
    threading.Thread(target=pipe, args=(target, client), daemon=True).start()


def main() -> None:
    server = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
    server.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
    server.bind((LISTEN_HOST, LISTEN_PORT))
    server.listen(128)
    print(f'forwarding {LISTEN_HOST}:{LISTEN_PORT} -> {TARGET_HOST}:{TARGET_PORT}', flush=True)
    while True:
        client, _addr = server.accept()
        threading.Thread(target=handle, args=(client,), daemon=True).start()


if __name__ == '__main__':
    main()
PY
  sudo chmod 0755 "$BRIDGE_BIN"
}

install_service() {
  local name="$1"
  local listen_host="$2"
  local listen_port="$3"
  local target_port="$4"
  local description="$5"

  sudo tee "/etc/systemd/system/${name}.service" >/dev/null <<UNIT
[Unit]
Description=${description}
After=network-online.target tailscaled.service k3s.service
Wants=network-online.target

[Service]
Type=simple
Environment=LISTEN_HOST=${listen_host}
Environment=LISTEN_PORT=${listen_port}
Environment=TARGET_HOST=${TARGET_HOST}
Environment=TARGET_PORT=${target_port}
ExecStartPre=/bin/sh -c 'if [ "${listen_host}" != "127.0.0.1" ]; then /usr/sbin/iptables -t nat -C PREROUTING -i tailscale0 -d ${listen_host}/32 -p tcp --dport ${listen_port} -j ACCEPT 2>/dev/null || /usr/sbin/iptables -t nat -I PREROUTING 1 -i tailscale0 -d ${listen_host}/32 -p tcp --dport ${listen_port} -j ACCEPT; fi'
ExecStart=/usr/bin/python3 ${BRIDGE_BIN}
Restart=always
RestartSec=3
NoNewPrivileges=true

[Install]
WantedBy=multi-user.target
UNIT
}

disable_legacy_user_forwarders() {
  if command -v systemctl >/dev/null 2>&1; then
    systemctl --user disable --now ope-core-forward.service 2>/dev/null || true
    systemctl --user disable --now ope-litellm-forward.service 2>/dev/null || true
  fi
  pkill -u "${USER}" -f 'kubectl -n ope port-forward' 2>/dev/null || true
}

disable_stale_services() {
  sudo systemctl disable --now ope-traefik-https-tailnet-bridge.service 2>/dev/null || true
  sudo rm -f /etc/systemd/system/ope-traefik-https-tailnet-bridge.service
  sudo systemctl disable --now ope-https-loopback-bridge.service 2>/dev/null || true
  sudo rm -f /etc/systemd/system/ope-https-loopback-bridge.service
}

install_bridge_bin
disable_legacy_user_forwarders
disable_stale_services
install_service ope-traefik-http-tailnet-bridge "${LISTEN_HOST}" 80 30080 'OPE HTTP bridge from octo-a to octo-b NodePort'
install_service ope-tailnet-bridge "${LISTEN_HOST}" 30080 30080 'OPE tailnet bridge from octo-a to octo-b NodePort'
install_service ope-litellm-tailnet-bridge "${LISTEN_HOST}" 30400 30400 'OPE LiteLLM tailnet bridge from octo-a to octo-b NodePort'

sudo systemctl daemon-reload
sudo systemctl enable --now \
  ope-traefik-http-tailnet-bridge.service \
  ope-tailnet-bridge.service \
  ope-litellm-tailnet-bridge.service
sudo systemctl restart \
  ope-traefik-http-tailnet-bridge.service \
  ope-tailnet-bridge.service \
  ope-litellm-tailnet-bridge.service

systemctl is-active ope-traefik-http-tailnet-bridge.service
systemctl is-active ope-tailnet-bridge.service
systemctl is-active ope-litellm-tailnet-bridge.service
sudo ss -ltnp '( sport = :80 or sport = :30080 or sport = :30400 )' || true
