#!/bin/bash
set -e

SCRIPT_DIR="$(cd "$(dirname "$0")" && pwd)"
BIN_DIR="${HOME}/.local/bin"

echo "=== murmur-type installer ==="
echo ""

# 1. Symlink to PATH
mkdir -p "$BIN_DIR"
ln -sf "$SCRIPT_DIR/murmur-type.py" "$BIN_DIR/murmur-type"
echo "[+] Symlinked murmur-type → $BIN_DIR/murmur-type"

# 2. Create config from template if not exists
if [ ! -f "$SCRIPT_DIR/config.json" ]; then
    cp "$SCRIPT_DIR/config.example.json" "$SCRIPT_DIR/config.json"
    echo "[+] Created config.json from template — edit it with your API keys"
else
    echo "[=] config.json already exists, skipping"
fi

# 3. Check dependencies
echo ""
echo "Checking dependencies..."
MISSING=()
for cmd in python3 pw-record wtype notify-send rofi; do
    if command -v "$cmd" &>/dev/null; then
        echo "  [OK] $cmd"
    else
        echo "  [!!] $cmd — NOT FOUND"
        MISSING+=("$cmd")
    fi
done

if [ ${#MISSING[@]} -gt 0 ]; then
    echo ""
    echo "Install missing dependencies (Arch Linux):"
    echo "  sudo pacman -S ${MISSING[*]}"
fi

# 4. VPN split-tunnel (optional)
echo ""
echo "=== VPN Split-Tunnel (optional) ==="
echo "If you use a VPN that blocks Groq (datacenter IPs), install the route service:"
echo ""
echo "  sudo cp $SCRIPT_DIR/groq-route.service /etc/systemd/system/"
echo "  sudo systemctl daemon-reload"
echo "  sudo systemctl enable --now groq-route.service"

# 5. Keybindings hint
echo ""
echo "=== Keybindings ==="
echo "Add these to your Wayland compositor config (niri/sway/hyprland):"
echo ""
echo "  Mod+Shift+E → murmur-type en        (voice → type English)"
echo "  Mod+Shift+R → murmur-type ru        (voice → type Russian)"
echo "  Mod+Shift+A → murmur-type translate  (voice → translate RU→EN popup)"
echo ""
echo "=== Done! ==="
echo "Edit $SCRIPT_DIR/config.json with your Groq API key, then try: murmur-type en"
