#!/bin/bash
set -e

echo "============================================"
echo "  ShuyuanCore - One-Click Installation"
echo "============================================"

# Configuration
INSTALL_DIR=${INSTALL_DIR:-/opt/shuyuancore}
GIT_REPO=${GIT_REPO:-https://github.com/Shuyuanverse/Shuyuancore.git}
BRANCH=${BRANCH:-main}
SYSTEM_USER=${SYSTEM_USER:-shuyuancore}

# Check OS
if [ -f /etc/os-release ]; then
    . /etc/os-release
    OS=$ID
    VERSION=$VERSION_ID
else
    echo "Unsupported OS. Please use Ubuntu 22.04+."
    exit 1
fi

echo "Installing ShuyuanCore on $OS $VERSION..."

# Create system user
if ! id -u $SYSTEM_USER >/dev/null 2>&1; then
    useradd -m -s /bin/bash $SYSTEM_USER
    echo "Created user: $SYSTEM_USER"
fi

# Create directory
mkdir -p $INSTALL_DIR
chown $SYSTEM_USER:$SYSTEM_USER $INSTALL_DIR

# Install system dependencies
echo "Installing system dependencies..."
apt-get update -qq
apt-get install -y -qq git python3 python3-pip python3-venv curl >/dev/null 2>&1

# Clone repository
echo "Cloning repository..."
cd $INSTALL_DIR
if [ -d "$INSTALL_DIR/.git" ]; then
    sudo -u $SYSTEM_USER git pull origin $BRANCH
else
    sudo -u $SYSTEM_USER git clone --branch $BRANCH $GIT_REPO .
fi

# Create virtual environment
echo "Setting up Python virtual environment..."
sudo -u $SYSTEM_USER python3 -m venv venv
sudo -u $SYSTEM_USER ./venv/bin/pip install --upgrade pip -q
sudo -u $SYSTEM_USER ./venv/bin/pip install -e . -q

# Create .env from template
if [ ! -f .env ]; then
    if [ -f .env.example ]; then
        sudo -u $SYSTEM_USER cp .env.example .env
        echo "Created .env from .env.example"
        echo "  >> Please edit $INSTALL_DIR/.env to set your API keys"
    else
        sudo -u $SYSTEM_USER touch .env
        echo "Created empty .env"
    fi
fi

# Create data directories
sudo -u $SYSTEM_USER mkdir -p data/logs data/chroma

# Install systemd service
echo "Installing systemd service..."
cp deploy/systemd/shuyuancore.service /etc/systemd/system/
systemctl daemon-reload
systemctl enable shuyuancore

echo ""
echo "============================================"
echo "  Installation Complete!"
echo "============================================"
echo ""
echo "  1. Edit configuration:  nano $INSTALL_DIR/.env"
echo "  2. Start service:       systemctl start shuyuancore"
echo "  3. Check status:        systemctl status shuyuancore"
echo "  4. View logs:           journalctl -u shuyuancore -f"
echo ""
echo "  API endpoint: http://localhost:8005"
echo "  Health check: http://localhost:8005/health"
echo ""