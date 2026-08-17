#!/usr/bin/env bash
# Complete native installer/updater for Ziggo DVB-C Monitor.
set -Eeuo pipefail

APP_NAME="dvb-c-monitor"
APP_USER="dvb-monitor"
APP_GROUP="video"
TARGET_DIR="${TARGET_DIR:-/opt/dvb-c-monitor}"
CONFIG_DIR="${CONFIG_DIR:-/etc/dvb-c-monitor}"
ENV_FILE="$CONFIG_DIR/monitor.env"
SERVICE_FILE="/etc/systemd/system/dvb-c-monitor.service"
PORT="${PORT:-8080}"
SOURCE_DIR="$(cd -- "$(dirname -- "${BASH_SOURCE[0]}")/.." && pwd)"

red='\033[0;31m'; green='\033[0;32m'; yellow='\033[1;33m'; cyan='\033[0;36m'; reset='\033[0m'
info() { printf "${cyan}==>${reset} %s\n" "$*"; }
ok()   { printf "${green}OK:${reset} %s\n" "$*"; }
warn() { printf "${yellow}LET OP:${reset} %s\n" "$*"; }
die()  { printf "${red}FOUT:${reset} %s\n" "$*" >&2; exit 1; }

[[ $EUID -eq 0 ]] || die "Start dit script met sudo: sudo bash tools/install-linux.sh"
[[ -f "$SOURCE_DIR/requirements.txt" && -f "$SOURCE_DIR/app/main.py" ]] || die "Projectbestanden niet gevonden in $SOURCE_DIR"
command -v apt-get >/dev/null 2>&1 || die "Deze installer ondersteunt Debian, Ubuntu en Raspberry Pi OS (apt)."

printf '\nZiggo DVB-C Monitor – volledige Linux-installatie\n'
printf 'Bron:  %s\nDoel:  %s\nPoort: %s\n\n' "$SOURCE_DIR" "$TARGET_DIR" "$PORT"

info "Benodigde Linux-pakketten installeren"
export DEBIAN_FRONTEND=noninteractive
apt-get update
apt-get install -y python3 python3-venv python3-pip dvb-tools rsync curl ca-certificates

info "Serviceaccount en mappen maken"
getent group "$APP_GROUP" >/dev/null || groupadd --system "$APP_GROUP"
if ! id "$APP_USER" >/dev/null 2>&1; then
  useradd --system --home-dir "$TARGET_DIR" --shell /usr/sbin/nologin --gid "$APP_GROUP" "$APP_USER"
else
  usermod -a -G "$APP_GROUP" "$APP_USER"
fi
mkdir -p "$TARGET_DIR" "$TARGET_DIR/data" "$CONFIG_DIR"

info "Applicatie naar $TARGET_DIR kopiëren"
# data, lokale instellingen, Git en virtualenv blijven bij upgrades ongemoeid.
rsync -a --delete \
  --exclude='.git/' --exclude='.venv/' --exclude='.env' --exclude='data/' \
  --exclude='__pycache__/' --exclude='*.pyc' \
  "$SOURCE_DIR/" "$TARGET_DIR/"
mkdir -p "$TARGET_DIR/data"

info "Afzonderlijke Python-omgeving installeren"
python3 -m venv "$TARGET_DIR/.venv"
"$TARGET_DIR/.venv/bin/pip" install --disable-pip-version-check --no-cache-dir -r "$TARGET_DIR/requirements.txt"

# Zoek de eerste adapter die zowel frontend0 als demux0 heeft.
DETECTED_ADAPTER=""
if [[ -d /dev/dvb ]]; then
  for frontend in /dev/dvb/adapter*/frontend0; do
    [[ -e "$frontend" ]] || continue
    adapter_dir="${frontend%/frontend0}"
    if [[ -e "$adapter_dir/demux0" ]]; then
      DETECTED_ADAPTER="${adapter_dir##*adapter}"
      break
    fi
  done
fi

if [[ -n "$DETECTED_ADAPTER" ]]; then
  ok "DVB-adapter $DETECTED_ADAPTER gevonden, inclusief frontend0 en demux0"
else
  DETECTED_ADAPTER="0"
  warn "Geen complete DVB-adapter gevonden. Adapter 0 wordt geconfigureerd."
  warn "Installeer/activeer de Sundtek-driver en controleer later met: /opt/bin/mediaclient -e"
fi

# Bepaal tuningbestand. Bestaande configuratie blijft bij een upgrade behouden.
TUNING_FILE="/usr/share/dvb/dvb-c/nl-Ziggo"
if [[ ! -f "$TUNING_FILE" ]]; then
  for candidate in /usr/share/dvb/dvb-c/nl-*Ziggo* /usr/share/dvb/dvb-c/nl-ziggo*; do
    if [[ -f "$candidate" ]]; then TUNING_FILE="$candidate"; break; fi
  done
fi

if [[ ! -f "$ENV_FILE" ]]; then
  info "Configuratie maken"
  if [[ ! -f "$TUNING_FILE" ]]; then
    TUNING_FILE="$CONFIG_DIR/ziggo.conf"
    if [[ -t 0 ]]; then
      printf '\nGeen Ziggo-tuningbestand gevonden.\n'
      read -r -p 'Ziggo-startfrequentie in MHz (leeg = later invullen): ' frequency_mhz
      read -r -p 'Symboolsnelheid [6900000]: ' symbol_rate
      symbol_rate="${symbol_rate:-6900000}"
    else
      frequency_mhz=""
      symbol_rate="6900000"
    fi
    if [[ -n "$frequency_mhz" ]]; then
      frequency_hz="$(awk -v f="$frequency_mhz" 'BEGIN { printf "%.0f", f*1000000 }')"
    else
      frequency_hz="474000000"
      warn "Tijdelijke startfrequentie 474 MHz gebruikt; pas $TUNING_FILE aan voor jouw Ziggo-regio."
    fi
    cat > "$TUNING_FILE" <<EOF
[CHANNEL]
DELIVERY_SYSTEM = DVBC/ANNEX_A
FREQUENCY = $frequency_hz
SYMBOL_RATE = $symbol_rate
INNER_FEC = NONE
MODULATION = QAM/256
EOF
  fi

  cat > "$ENV_FILE" <<EOF
DATABASE_PATH=$TARGET_DIR/data/ziggo-monitor.db
DVB_ADAPTER=$DETECTED_ADAPTER
DVB_FRONTEND=0
DVB_TUNING_FILE=$TUNING_FILE
DVB_CHANNELS_FILE=$TARGET_DIR/data/channels.conf
SCAN_INTERVAL_MINUTES=360
SCAN_ON_START=false
ENABLE_SCHEDULER=true
REMOVAL_GRACE_SCANS=2
EOF
else
  ok "Bestaande configuratie behouden: $ENV_FILE"
fi

info "Bestandsrechten instellen"
chown -R root:root "$TARGET_DIR"
chown -R "$APP_USER:$APP_GROUP" "$TARGET_DIR/data"
chmod 750 "$TARGET_DIR/data"
chown -R root:"$APP_GROUP" "$CONFIG_DIR"
chmod 750 "$CONFIG_DIR"
chmod 640 "$ENV_FILE"

info "systemd-service installeren"
cat > "$SERVICE_FILE" <<EOF
[Unit]
Description=Ziggo DVB-C zender- en wijzigingsmonitor
After=network-online.target
Wants=network-online.target

[Service]
Type=simple
User=$APP_USER
Group=$APP_GROUP
SupplementaryGroups=$APP_GROUP
WorkingDirectory=$TARGET_DIR
EnvironmentFile=$ENV_FILE
ExecStart=$TARGET_DIR/.venv/bin/uvicorn app.main:app --host 0.0.0.0 --port $PORT
Restart=on-failure
RestartSec=5
NoNewPrivileges=true
PrivateTmp=true
ProtectHome=true
ProtectSystem=strict
ReadWritePaths=$TARGET_DIR/data

[Install]
WantedBy=multi-user.target
EOF

systemctl daemon-reload
systemctl enable dvb-c-monitor.service >/dev/null
systemctl restart dvb-c-monitor.service
sleep 2

if systemctl is-active --quiet dvb-c-monitor.service; then
  ok "De webservice draait"
else
  systemctl status dvb-c-monitor.service --no-pager || true
  die "De service kon niet worden gestart. Bekijk: journalctl -u dvb-c-monitor -n 100"
fi

IP="$(hostname -I 2>/dev/null | awk '{print $1}')"
printf '\n${green}Installatie voltooid.${reset}\n'
printf 'Website:       http://%s:%s\n' "${IP:-SERVER-IP}" "$PORT"
printf 'Configuratie:  %s\n' "$ENV_FILE"
printf 'Applicatie:    %s\n' "$TARGET_DIR"
printf 'Status:        sudo systemctl status dvb-c-monitor\n'
printf 'Logboek:       sudo journalctl -u dvb-c-monitor -f\n'
printf 'Herstarten:    sudo systemctl restart dvb-c-monitor\n\n'

if [[ ! -e "/dev/dvb/adapter${DETECTED_ADAPTER}/demux0" ]]; then
  warn "De website draait, maar scannen werkt pas als /dev/dvb/adapter${DETECTED_ADAPTER}/demux0 bestaat."
  printf 'Controleer met:\n  /opt/bin/mediaclient -e\n  find /dev/dvb -maxdepth 2 -ls\n\n'
else
  printf 'Test de eerste scan via de knop “Nu scannen” op de website.\n\n'
fi
