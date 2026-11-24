#!/usr/bin/env bash
# Instala a bolinha pro usuário atual: venv, voz, ícone e atalhos no menu (rofi, wofi, etc.).
# Pode rodar de novo quando quiser; ele só completa o que falta.
set -euo pipefail

REPO="$(cd "$(dirname "$0")" && pwd)"
DADOS="${XDG_DATA_HOME:-$HOME/.local/share}/bolinha"
VENV="$DADOS/venv"
APPS="${XDG_DATA_HOME:-$HOME/.local/share}/applications"
ICONES="${XDG_DATA_HOME:-$HOME/.local/share}/icons/hicolor/scalable/apps"

for cmd in pw-record pw-play claude python3; do
  command -v "$cmd" >/dev/null || { echo "Falta '$cmd'. Instale antes (pipewire / Claude Code / python)."; exit 1; }
done

mkdir -p "$DADOS/voz" "$APPS" "$ICONES"

if [ ! -x "$VENV/bin/python" ]; then
  echo "Criando o ambiente Python em $VENV…"
  python3 -m venv --system-site-packages "$VENV"
fi
echo "Instalando dependências…"
"$VENV/bin/pip" install -q -r "$REPO/requirements.txt"

if command -v nvidia-smi >/dev/null && nvidia-smi -L >/dev/null 2>&1; then
  echo "GPU NVIDIA encontrada: instalando cuBLAS/cuDNN pra transcrever na placa (~2 GB)…"
  "$VENV/bin/pip" install -q nvidia-cublas-cu12 "nvidia-cudnn-cu12==9.*"
fi

VOZ_URL="https://huggingface.co/Phoonnx/pipertts_pt-BR_dii/resolve/main"
if [ ! -f "$DADOS/voz/pt_BR-dii.onnx" ]; then
  echo "Baixando a voz (Dii, pt-BR, 60 MB)…"
  curl -sSfL -o "$DADOS/voz/pt_BR-dii.onnx" "$VOZ_URL/dii_pt-BR.onnx"
  curl -sSfL -o "$DADOS/voz/pt_BR-dii.onnx.json" "$VOZ_URL/dii_pt-BR.onnx.json"
fi

install -m644 "$REPO/bolinha.svg" "$ICONES/bolinha.svg"

cat > "$APPS/bolinha.desktop" <<EOF
[Desktop Entry]
Type=Application
Name=Bolinha
Comment=Pergunte ao Claude por voz
Exec=$VENV/bin/python $REPO/bolinha.py
Icon=bolinha
Terminal=false
Categories=Utility;
Keywords=voz;assistente;claude;perguntar;
StartupWMClass=bolinha
EOF

cat > "$APPS/bolinha-ajustes.desktop" <<EOF
[Desktop Entry]
Type=Application
Name=Bolinha — Ajustes
Comment=Estilo, voz, microfone e modelo da bolinha
Exec=$VENV/bin/python $REPO/ajustes.py
Icon=bolinha
Terminal=false
Categories=Utility;
Keywords=voz;assistente;claude;configurar;
StartupWMClass=bolinha-ajustes
EOF

command -v update-desktop-database >/dev/null && update-desktop-database -q "$APPS" || true

cat <<EOF

Pronto! "Bolinha" e "Bolinha — Ajustes" já aparecem no menu de apps.

Falta o atalho de teclado. No Hyprland, adicione uma destas linhas e recarregue:

  hyprland.conf:  bind = SUPER, C, exec, $VENV/bin/python $REPO/bolinha.py
  hyprland.lua:   hl.bind("SUPER + C", hl.dsp.exec_cmd("$VENV/bin/python $REPO/bolinha.py"))

E uma regra pra ela flutuar por cima, sem borda/sombra/blur (exemplo testado no hyprland.lua, Hyprland 0.57):

  hl.window_rule({ match = { class = "^(bolinha)$" }, float = true, pin = true, center = true, border_size = 0,
                   no_shadow = true, no_blur = true, rounding = 0, no_anim = true, opacity = "1.0 override 1.0 override" })

EOF
