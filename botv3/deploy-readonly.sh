#!/usr/bin/env bash
set -euo pipefail

src=${1:-/tmp/botv3-readonly}
target=/opt/botv3
state=/opt/nodo/datos/botv3
service=/etc/systemd/system/botv3.service
stamp=$(date +%Y%m%d_%H%M%S)
backup="$state/deploy-backups/$stamp"

test -d "$src"
mountpoint -q /opt/nodo/datos
install -d -m 0700 "$backup/botv3"
cp -a "$target/." "$backup/botv3/"
cp -a "$service" "$backup/botv3.service"

# Copias de los binarios: /usr/local/bin enlaza a /home, bloqueado por systemd.
install -d -o root -g root -m 0755 "$target/bin"
install -o root -g root -m 0755 "$(readlink -f /usr/local/bin/claude)" "$target/bin/claude"
install -o root -g root -m 0755 "$(readlink -f /usr/local/bin/codex)" "$target/bin/codex"
codex_bin_dir=$(dirname "$(readlink -f /usr/local/bin/codex)")
install -o root -g root -m 0755 "$codex_bin_dir/codex-code-mode-host" "$target/bin/codex-code-mode-host"

install -o root -g root -m 0755 "$src/botv3.py" "$target/botv3.py"
install -o root -g root -m 0755 "$src/configure.py" "$target/configure.py"
install -o root -g root -m 0755 "$src/test_botv3.py" "$target/test_botv3.py"
install -o root -g root -m 0644 "$src/proposal.schema.json" "$target/proposal.schema.json"
install -o root -g root -m 0644 "$src/botv3.env.example" "$target/botv3.env.example"
install -o root -g root -m 0644 "$src/README.md" "$target/README.md"
install -o root -g root -m 0644 "$src/botv3.service" "$service"

install -d -o dcifu004 -g captura -m 0700 "$state/runtime-home"
python3 "$target/test_botv3.py"
systemd-analyze verify "$service"
systemctl daemon-reload
systemctl restart botv3.service
sleep 3
systemctl is-active --quiet botv3.service

echo "BACKUP=$backup"
systemctl show botv3.service -p ActiveState -p SubState -p MainPID -p ReadOnlyPaths -p ReadWritePaths -p InaccessiblePaths
journalctl -u botv3.service -n 12 --no-pager
