#!/usr/bin/env bash
# Installs/updates everything needed to run ilmavalvontaseloste on a fresh
# Debian/Ubuntu machine with PipeWire audio: build deps, whisper.cpp + models,
# audio permissions, and a systemd --user service for server.py.
#
# Run this from inside the cloned repo: ./install.sh
# Re-running is safe - each step is skipped if already done.
set -euo pipefail

APP_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
WHISPER_DIR="$HOME/whisper.cpp"
WHISPER_MODEL="small"
VAD_MODEL="silero-v5.1.2"
SERVICE_NAME="ilmavalvontaseloste"

# SUDO_PASS can be set in the environment for unattended runs; otherwise this
# falls back to the normal interactive sudo password prompt.
run_sudo() {
    if [ -n "${SUDO_PASS:-}" ]; then
        echo "$SUDO_PASS" | sudo -S "$@"
    else
        sudo "$@"
    fi
}

echo "==> Asennetaan järjestelmäriippuvuudet (sudo tarvitaan)..."
run_sudo apt-get update -qq || echo "    (apt-get update epäonnistui osittain, jatketaan silti)"
run_sudo apt-get install -y -qq build-essential cmake git wget ffmpeg \
    pipewire-audio-client-libraries wireplumber python3

echo "==> Lisätään $(whoami) audio-ryhmään (mikrofonin käyttöoikeus)..."
run_sudo usermod -aG audio "$(whoami)"

echo "==> Otetaan systemd lingering käyttöön (palvelin pysyy käynnissä uloskirjautumisen jälkeen)..."
run_sudo loginctl enable-linger "$(whoami)"

if [ ! -d "$WHISPER_DIR" ]; then
    echo "==> Kloonataan whisper.cpp..."
    git clone --depth 1 https://github.com/ggerganov/whisper.cpp.git "$WHISPER_DIR"
else
    echo "==> whisper.cpp on jo olemassa, ohitetaan kloonaus."
fi

cd "$WHISPER_DIR"

if [ ! -f "models/ggml-${WHISPER_MODEL}.bin" ]; then
    echo "==> Ladataan Whisper-malli (${WHISPER_MODEL})..."
    bash ./models/download-ggml-model.sh "$WHISPER_MODEL"
else
    echo "==> Whisper-malli on jo ladattu."
fi

if [ ! -f "models/ggml-${VAD_MODEL}.bin" ]; then
    echo "==> Ladataan VAD-malli (${VAD_MODEL})..."
    bash ./models/download-vad-model.sh "$VAD_MODEL"
else
    echo "==> VAD-malli on jo ladattu."
fi

if [ ! -f "build/bin/whisper-cli" ]; then
    echo "==> Käännetään whisper.cpp (kestää muutaman minuutin)..."
    cmake -B build
    cmake --build build -j"$(nproc)" --config Release
else
    echo "==> whisper.cpp on jo käännetty, ohitetaan."
fi

echo "==> Asennetaan systemd-käyttäjäpalvelu ($SERVICE_NAME)..."
mkdir -p "$HOME/.config/systemd/user"
cat > "$HOME/.config/systemd/user/${SERVICE_NAME}.service" <<EOF
[Unit]
Description=Ilmavalvontaseloste - paikallinen palvelin
After=network.target

[Service]
ExecStart=/usr/bin/python3 ${APP_DIR}/server.py
WorkingDirectory=${APP_DIR}
Restart=on-failure
RestartSec=3

[Install]
WantedBy=default.target
EOF

systemctl --user daemon-reload
systemctl --user enable --now "${SERVICE_NAME}.service"

echo ""
echo "==> Valmis. Sovellus on käynnissä: http://127.0.0.1:8642/"
echo "    Tila:  systemctl --user status ${SERVICE_NAME}"
echo "    Lokit: journalctl --user -u ${SERVICE_NAME} -f"
echo ""
echo "    HUOM: jos sinut lisättiin audio-ryhmään juuri nyt, kirjaudu ulos ja"
echo "    sisään (tai käynnistä kone uudelleen) ennen kuin mikrofoni toimii."
