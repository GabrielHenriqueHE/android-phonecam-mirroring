#!/usr/bin/env bash
# Cria a webcam virtual /dev/video10 ("PhoneCam") de forma permanente.
# Testado para distros baseadas em Ubuntu/Debian (Zorin, Mint, Pop!_OS...).
set -euo pipefail

DEV_NR="${DEV_NR:-10}"
LABEL="${LABEL:-PhoneCam}"

echo ">> instalando v4l2loopback"
sudo apt-get update -qq
sudo apt-get install -y v4l2loopback-dkms v4l2loopback-utils

if command -v mokutil >/dev/null && mokutil --sb-state 2>/dev/null | grep -qi enabled; then
  echo "!! Secure Boot está ATIVO: se o modprobe falhar com 'Key was rejected by service',"
  echo "   reinicie e conclua o 'Enroll MOK' com a senha que o DKMS pediu na instalação."
fi

echo ">> configurando carga automática no boot"
# exclusive_caps=1 é o que faz o Chrome/Meet enxergar a câmera virtual
echo "options v4l2loopback devices=1 video_nr=${DEV_NR} card_label=\"${LABEL}\" exclusive_caps=1" \
  | sudo tee /etc/modprobe.d/phonecam-v4l2loopback.conf >/dev/null
echo "v4l2loopback" | sudo tee /etc/modules-load.d/phonecam-v4l2loopback.conf >/dev/null

echo ">> carregando o módulo"
sudo modprobe -r v4l2loopback 2>/dev/null || true
sudo modprobe v4l2loopback

DEV="/dev/video${DEV_NR}"
if [[ ! -e "$DEV" ]]; then
  echo "!! $DEV não apareceu. Veja: sudo dmesg | tail" >&2
  exit 1
fi
ls -l "$DEV"

if [[ ! -w "$DEV" ]]; then
  echo "!! seu usuário não pode escrever em $DEV. Rode:"
  echo "   sudo usermod -aG video \"$USER\"   # e faça logout/login"
fi

echo ">> pronto: $DEV ($LABEL)"
