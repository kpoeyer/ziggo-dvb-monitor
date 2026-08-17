#!/bin/sh
set -eu
[ "$(id -u)" = 0 ] || { echo "Voer uit als root" >&2; exit 1; }
apt-get update
apt-get install -y python3 python3-venv dvb-tools
id ziggo-monitor >/dev/null 2>&1 || useradd --system --home /opt/ziggo-dvb-monitor --shell /usr/sbin/nologin --groups video ziggo-monitor
mkdir -p /opt/ziggo-dvb-monitor
cp -a app requirements.txt tools /opt/ziggo-dvb-monitor/
python3 -m venv /opt/ziggo-dvb-monitor/.venv
/opt/ziggo-dvb-monitor/.venv/bin/pip install -r /opt/ziggo-dvb-monitor/requirements.txt
mkdir -p /opt/ziggo-dvb-monitor/data
chown -R ziggo-monitor:ziggo-monitor /opt/ziggo-dvb-monitor
[ -f /etc/ziggo-dvb-monitor.env ] || cp .env.example /etc/ziggo-dvb-monitor.env
cp deploy/systemd/ziggo-dvb-monitor.service /etc/systemd/system/
systemctl daemon-reload
systemctl enable --now ziggo-dvb-monitor
printf '\nGereed: http://%s:8080\n' "$(hostname -I | awk '{print $1}')"
