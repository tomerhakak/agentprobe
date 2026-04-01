#!/usr/bin/env bash
# AgentProbe Installer — https://github.com/tomerhakak/agentprobe
# Usage: curl -fsSL https://raw.githubusercontent.com/tomerhakak/agentprobe/main/install.sh | bash
set -euo pipefail

VERSION="0.2.0"
REPO="tomerhakak/agentprobe"
INSTALL_DIR="${AGENTPROBE_HOME:-$HOME/.agentprobe}"
BIN_DIR="$INSTALL_DIR/bin"
VENV_DIR="$INSTALL_DIR/venv"

# Colors
RED='\033[0;31m'
GREEN='\033[0;32m'
CYAN='\033[0;36m'
BOLD='\033[1m'
RESET='\033[0m'

info()  { printf "${CYAN}▸${RESET} %s\n" "$1"; }
ok()    { printf "${GREEN}✓${RESET} %s\n" "$1"; }
fail()  { printf "${RED}✗${RESET} %s\n" "$1" >&2; exit 1; }

echo ""
printf "${BOLD}  AgentProbe Installer v${VERSION}${RESET}\n"
printf "  pytest for AI Agents\n\n"

# Check Python
if command -v python3 &>/dev/null; then
    PYTHON=python3
elif command -v python &>/dev/null; then
    PYTHON=python
else
    fail "Python 3.10+ is required. Install it from https://python.org"
fi

PY_VERSION=$($PYTHON -c 'import sys; print(f"{sys.version_info.major}.{sys.version_info.minor}")')
PY_MAJOR=$($PYTHON -c 'import sys; print(sys.version_info.major)')
PY_MINOR=$($PYTHON -c 'import sys; print(sys.version_info.minor)')

if [ "$PY_MAJOR" -lt 3 ] || { [ "$PY_MAJOR" -eq 3 ] && [ "$PY_MINOR" -lt 10 ]; }; then
    fail "Python 3.10+ required (found $PY_VERSION)"
fi
ok "Python $PY_VERSION"

# Create install directory
info "Installing to $INSTALL_DIR"
mkdir -p "$INSTALL_DIR" "$BIN_DIR"

# Create virtual environment
if [ ! -d "$VENV_DIR" ]; then
    info "Creating virtual environment..."
    $PYTHON -m venv "$VENV_DIR"
fi
ok "Virtual environment ready"

# Activate and install
info "Installing AgentProbe..."
"$VENV_DIR/bin/pip" install --quiet --upgrade pip
"$VENV_DIR/bin/pip" install --quiet "agentprobe @ git+https://github.com/${REPO}.git@v${VERSION}"
ok "AgentProbe $VERSION installed"

# Create wrapper script
cat > "$BIN_DIR/agentprobe" << 'WRAPPER'
#!/usr/bin/env bash
INSTALL_DIR="${AGENTPROBE_HOME:-$HOME/.agentprobe}"
exec "$INSTALL_DIR/venv/bin/agentprobe" "$@"
WRAPPER
chmod +x "$BIN_DIR/agentprobe"

# Add to PATH
SHELL_NAME=$(basename "$SHELL")
PROFILE=""
case "$SHELL_NAME" in
    zsh)  PROFILE="$HOME/.zshrc" ;;
    bash) PROFILE="$HOME/.bashrc" ;;
    fish) PROFILE="$HOME/.config/fish/config.fish" ;;
esac

PATH_LINE="export PATH=\"$BIN_DIR:\$PATH\""
if [ -n "$PROFILE" ] && ! grep -q "agentprobe/bin" "$PROFILE" 2>/dev/null; then
    echo "" >> "$PROFILE"
    echo "# AgentProbe" >> "$PROFILE"
    echo "$PATH_LINE" >> "$PROFILE"
    ok "Added to PATH in $PROFILE"
else
    ok "PATH already configured"
fi

echo ""
printf "${BOLD}${GREEN}  AgentProbe v${VERSION} installed successfully!${RESET}\n"
echo ""
echo "  Get started:"
echo ""
printf "    ${CYAN}source ${PROFILE}${RESET}          # reload shell\n"
printf "    ${CYAN}agentprobe init${RESET}             # setup a project\n"
printf "    ${CYAN}agentprobe record${RESET}           # record an agent run\n"
printf "    ${CYAN}agentprobe test${RESET}             # run tests\n"
printf "    ${CYAN}agentprobe platform start${RESET}   # launch web dashboard\n"
echo ""
printf "  Docs: ${CYAN}https://github.com/${REPO}${RESET}\n"
echo ""
