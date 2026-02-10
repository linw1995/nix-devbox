#!/usr/bin/env bash
# Demo: Stack base + opencode + local config

set -e

echo "=== nix-devbox Stacked Config Demo ==="
echo ""
echo "Layers:"
echo "  1. base/       - Foundation (memory 1g, security)"
echo "  2. opencode/   - App config (volumes, env)"
echo "  3. ./          - Local overrides (memory 2g, ports)"
echo ""

cd "$(dirname "$0")"

echo "Command: nix-devbox run ../base ../opencode . --dry-run"
echo ""
nix-devbox run ../base ../opencode . --dry-run

echo ""
echo "=== Key merge results ==="
echo "✓ memory: 1g → 2g (overridden by local config)"
echo "✓ cap_drop: ALL (inherited from base)"
echo "✓ volumes: 3 mounts (inherited from opencode)"
echo "✓ ports: 9000:9000 (added by local config)"
