# Ziggo DVB-C Monitor (MVP)

Een lokale webtool die via een Sundtek DVB-C-stick het Ziggo-aanbod scant en wijzigingen bewaart. De tool vergelijkt DVB service-informatie per scan en toont:

- nieuwe en verdwenen zenders;
- gewijzigde zendernaam, provider en logisch kanaalnummer (LCN/VCHANNEL);
- teletekst-, ondertitel-, audio- en video-PID's;
- frequentie, modulatie, symboolsnelheid en versleuteling;
- scanstatus en volledige wijzigingshistorie.

De Sundtek Linux-driver exposeert de stick normaal als `/dev/dvb/adapterN`. De applicatie gebruikt standaard `dvbv5-scan` uit `dvb-tools`. Er worden geen uitzendingen gestreamd of ontsleuteld.

## 1. Eerst hardware controleren

Installeer de officiële Sundtek-driver op de **host** en controleer:

```bash
/opt/bin/mediaclient -e
dvb-fe-tool -a 0
ls -l /dev/dvb/adapter0
```

Zet de stick zo nodig in DVB-C-modus (exacte opdracht hangt af van het Sundtek-model/driver):

```bash
/opt/bin/mediaclient -D DVBC
```

Het account dat de native service draait is lid van groep `video`.

## 2. Ziggo starttransponder/tuningbestand

`dvbv5-scan` heeft minstens één geldige starttransponder nodig. Distributies leveren vaak `/usr/share/dvb/dvb-c/nl-Ziggo`. Bestaat die niet of past deze niet bij de regio, maak bijvoorbeeld `/etc/ziggo-fijnaart.conf`:

```ini
[CHANNEL]
DELIVERY_SYSTEM = DVBC/ANNEX_A
FREQUENCY = <frequentie-in-Hz>
SYMBOL_RATE = 6900000
INNER_FEC = NONE
MODULATION = QAM/256
```

Vul de actuele Ziggo-frequentie, symboolsnelheid en zo nodig netwerk-ID van de aansluiting in. Het netwerk-ID wordt niet als tunerparameter gebruikt, maar kan nodig zijn om het juiste regionale profiel te kiezen. Test eerst handmatig:

```bash
dvbv5-scan -a 0 -f 0 -o /tmp/channels.conf /etc/ziggo-fijnaart.conf
```

## 3A. Volledige Linux-installatie in één keer (aanbevolen)

Voor Debian, Ubuntu en Raspberry Pi OS:

```bash
cd /dvb-c-monitor
sudo bash tools/install-linux.sh
```

Het script installeert de Linux-pakketten en Python-omgeving, kopieert de applicatie naar `/opt/dvb-c-monitor`, detecteert de DVB-adapter, maakt de configuratie in `/etc/dvb-c-monitor/monitor.env` en activeert de systemd-service. Bestaande database en configuratie blijven bij een latere update behouden.

Open daarna `http://SERVER-IP:8080`.

Beheeropdrachten:

```bash
sudo systemctl status dvb-c-monitor
sudo journalctl -u dvb-c-monitor -f
sudo systemctl restart dvb-c-monitor
```

De Sundtek-driver zelf moet al op de host geïnstalleerd zijn. Het script meldt duidelijk wanneer `/dev/dvb/adapterN/demux0` nog ontbreekt.

### Oud native installatiescript

Het eerdere script blijft beschikbaar als `tools/install-native.sh`, maar de complete installer hierboven wordt aanbevolen.

Voor andere distributies: installeer Python 3.10+, `dvb-tools`, maak een virtualenv, installeer `requirements.txt` en start:

```bash
uvicorn app.main:app --host 0.0.0.0 --port 8080
```

## 3B. Docker Compose

Installeer de Sundtek-driver op de host; de container krijgt `/dev/dvb` doorgegeven.

```bash
cp .env.example .env
nano .env
docker compose up -d --build
```

De Compose-MVP gebruikt `privileged: true` voor voorspelbare hotplug-toegang. Dit kan later worden aangescherpt tot expliciete devices/cgroup-regels. Als het tuningbestand buiten `/usr/share/dvb` staat, mount dat bestand extra in `docker-compose.yml`.

## Configuratie

| Variabele | Standaard | Betekenis |
|---|---:|---|
| `DVB_ADAPTER` | `0` | `/dev/dvb/adapterN` |
| `DVB_FRONTEND` | `0` | frontendnummer |
| `DVB_TUNING_FILE` | `/usr/share/dvb/dvb-c/nl-Ziggo` | starttransponderbestand |
| `SCAN_INTERVAL_MINUTES` | `360` | automatische scanfrequentie |
| `SCAN_ON_START` | `false` | direct scannen bij starten |
| `REMOVAL_GRACE_SCANS` | `2` | pas na N gemiste scans als verdwenen markeren |
| `DVB_SCAN_COMMAND` | leeg | alternatief probecommando |

Scannen onderbreekt eventueel live tv-gebruik op dezelfde tuner. Een interval van 6–24 uur is daarom gebruikelijk.

## Demo zonder DVB-hardware

```bash
python3 -m venv .venv && . .venv/bin/activate
pip install -r requirements.txt
export DVB_SCAN_COMMAND='python3 tools/demo_scan.py'
uvicorn app.main:app --host 0.0.0.0 --port 8080
```

Klik daarna op **Nu scannen**.

## Eigen/enriched probe

Niet elke versie van `dvbv5-scan` schrijft alle descriptors (vooral LCN, talen, DVB-subtitles en teletekst) naar `channels.conf`. Daarom accepteert `DVB_SCAN_COMMAND` ook een eigen scanner die een JSON-array naar stdout schrijft. Elk object kan deze velden bevatten:

```json
{"original_network_id":5555,"transport_stream_id":31,"service_id":10001,
 "name":"Voorbeeld TV","provider":"Ziggo","channel_number":12,
 "frequency":474000000,"symbol_rate":6900000,"modulation":"QAM/256",
 "encrypted":false,"teletext":[{"pid":36,"language":"nld"}],
 "subtitles":[{"pid":51,"language":"nld"}],"audio":[],"video":[]}
```

Dit maakt koppeling met TSDuck, `dvbsnoop`, een Sundtek-specifiek script of een externe SI-parser mogelijk. Dezelfde payload kan worden aangeleverd via `POST /api/scans/import` als `{ "services": [...] }`.

## Belangrijke MVP-beperkingen

- Voor betrouwbare teletekst/ondertitel-detectie moet de gebruikte scanbackend de PMT-descriptors exporteren. De standaardparser bewaart ze zodra `TELETEXT_PID`/`SUBTITLE_PID` in channels.conf staan; anders is een enriched probe nodig.
- Het dashboard heeft in deze versie geen login. Publiceer poort 8080 daarom niet rechtstreeks op internet.
- Versleutelde kanalen worden alleen geïnventariseerd, niet gedecodeerd.
- Een verdwenen zender wordt standaard pas na twee opeenvolgende succesvolle scans gemeld, om valse meldingen door tijdelijk signaalverlies te beperken.

## Tests

```bash
python -m unittest discover -s tests -v
```
