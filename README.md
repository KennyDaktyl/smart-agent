# Smart Agent Deployment/Update na Raspberry Pi (systemd + docker compose)

## Cel
Ten dokument opisuje stabilny model aktualizacji obrazu agenta bez uruchamiania `docker compose` z wnętrza kontenera.

Model docelowy:
1. UI zmienia `AGENT_TAG` w `.env`.
2. UI wysyła event restart/trigger update.
3. Host (systemd + skrypt) wykonuje `docker compose pull` i `docker compose up -d`.
4. Nowy tag z `.env` jest użyty przez Docker Compose na hoście.

## Dlaczego ten model
- Kontener agenta nie powinien być głównym orchestratoriem hostowego deploymentu.
- `systemd` na hoście ma natywny dostęp do Dockera i plików deploymentu.
- Łatwiejsza diagnostyka (`journalctl`, `systemctl status`) i prostszy rollback.

## Kontrakty i zachowanie systemu
1. `REBOOT_AGENT` w obecnym agencie restartuje proces/kontener, ale nie gwarantuje `docker compose pull` ani `docker compose up -d`.
2. Kontrakt hostowego update:
   - `docker compose -f <compose-file> pull agent && docker compose -f <compose-file> up -d agent`
3. Kontrakt UI:
   - UI aktualizuje `.env` (minimum `AGENT_TAG`, opcjonalnie `AGENT_IMAGE`).
   - UI wywołuje trigger update (event NATS lub endpoint bridge na hoście).
4. Kontrakt logowania:
   - logować docelową wersję `AGENT_IMAGE:AGENT_TAG`,
   - nie logować sekretów z `.env`.

## Wymagania (Raspberry Pi)
- Zainstalowany Docker + plugin `docker compose`.
- Projekt wdrożony jako katalog hostowy z `docker-compose.yml` i `.env`.
- Użytkownik systemowy mający dostęp do Dockera (np. `pi` w grupie `docker`).

Przykładowe sprawdzenie:

```bash
docker --version
docker compose version
id
```

## Konfiguracja `.env`
Przykład minimalny:

```env
AGENT_IMAGE=docker.io/kennydaktyl/smart-agent
AGENT_TAG=agent_v1.0.0
```

`AGENT_TAG` jest źródłem prawdy dla update.

## Hostowy skrypt update
Utwórz plik `/opt/smart-agent/scripts/update-agent.sh`:

```bash
#!/usr/bin/env bash
set -euo pipefail

APP_DIR="/opt/smart-agent"
COMPOSE_FILE="${APP_DIR}/docker-compose.yml"
SERVICE_NAME="agent"

cd "${APP_DIR}"

# Bez logowania całej zawartości .env (sekrety)
IMAGE="$(grep -E '^AGENT_IMAGE=' .env | head -n1 | cut -d= -f2- || true)"
TAG="$(grep -E '^AGENT_TAG=' .env | head -n1 | cut -d= -f2- || true)"
echo "Starting agent update to image: ${IMAGE:-<unset>}:${TAG:-<unset>}"

docker compose -f "${COMPOSE_FILE}" pull "${SERVICE_NAME}"
docker compose -f "${COMPOSE_FILE}" up -d "${SERVICE_NAME}"

echo "Agent update finished"

# Opcjonalnie (domyślnie wyłączone):
# docker image prune -f
```

Uprawnienia:

```bash
chmod +x /opt/smart-agent/scripts/update-agent.sh
```

## Unit `systemd`: `smart-agent-update.service`
Utwórz plik `/etc/systemd/system/smart-agent-update.service`:

```ini
[Unit]
Description=Smart Agent update (docker compose pull + up)
After=network-online.target docker.service
Wants=network-online.target
Requires=docker.service

[Service]
Type=oneshot
User=pi
Group=docker
WorkingDirectory=/opt/smart-agent
ExecStart=/opt/smart-agent/scripts/update-agent.sh
StandardOutput=journal
StandardError=journal
TimeoutStartSec=600

[Install]
WantedBy=multi-user.target
```

Aktywacja:

```bash
sudo systemctl daemon-reload
sudo systemctl enable smart-agent-update.service
```

Ręczne uruchomienie:

```bash
sudo systemctl start smart-agent-update.service
```

## Opcjonalny auto-trigger
Rekomendacja na start: manualny trigger z UI/eventu.

### Opcja A: `systemd path` (trigger po zmianie `.env`)
`/etc/systemd/system/smart-agent-update.path`:

```ini
[Unit]
Description=Watch .env and trigger Smart Agent update

[Path]
PathModified=/opt/smart-agent/.env
Unit=smart-agent-update.service

[Install]
WantedBy=multi-user.target
```

Aktywacja:

```bash
sudo systemctl daemon-reload
sudo systemctl enable --now smart-agent-update.path
```

### Opcja B: `systemd timer` (cykliczny pull/up)
Stosować tylko jeśli potrzebny okresowy self-heal.

## Integracja z UI/NATS (trigger)
1. UI zapisuje nowy `.env` (zmiana `AGENT_TAG`/`AGENT_IMAGE`).
2. UI wysyła event update/restart trigger.
3. Bridge/handler na hoście uruchamia:

```bash
sudo systemctl start smart-agent-update.service
```

Ważne: sam `REBOOT_AGENT` nie zastępuje update service.

## Runbook operatora
1. Zmień `AGENT_TAG` w UI (np. `agent_v1.0.0` -> `agent_v1.0.1`).
2. Zweryfikuj zapis `.env` na hoście.
3. Uruchom trigger update (event/bridge -> `systemctl start`).
4. Zweryfikuj wynik:

```bash
systemctl status smart-agent-update.service
journalctl -u smart-agent-update.service -n 200 --no-pager
docker compose -f /opt/smart-agent/docker-compose.yml ps
docker inspect smart-agent --format '{{.Config.Image}}'
```

## Rollback
1. Ustaw poprzedni `AGENT_TAG` w `.env`.
2. Uruchom ponownie:

```bash
sudo systemctl start smart-agent-update.service
```

3. Sprawdź status kontenera i obraz.

## Troubleshooting
### `permission denied` do `/var/run/docker.sock`
- Użytkownik z service nie ma praw do Dockera.
- Rozwiązanie: `User=pi`, `Group=docker`, ewentualnie `usermod -aG docker pi`.

### `compose file not found`
- Złe `WorkingDirectory` lub ścieżka compose.
- Rozwiązanie: potwierdź `/opt/smart-agent/docker-compose.yml`.

### `manifest unknown` / brak obrazu
- Nieistniejący tag albo obraz bez wsparcia architektury Raspberry (arm).
- Rozwiązanie: popraw `AGENT_TAG`/`AGENT_IMAGE`, sprawdź manifesty obrazu.

### Brak sieci / timeout pull
- `docker compose pull` się wywalił.
- Rozwiązanie: retry po przywróceniu łączności:

```bash
sudo systemctl start smart-agent-update.service
```

## Scenariusze testowe
1. Happy path: `v1.0.0 -> v1.0.1`, service kończy się kodem `0`.
2. Invalid tag: błędny tag, service `failed`, kontener zostaje na starej wersji.
3. Brak sieci: `pull` fail, po przywróceniu sieci retry działa.
4. Rollback: powrót do poprzedniego tagu przez ten sam flow.
5. Reboot hosta: system działa na ostatnio wdrożonym tagu.

## Założenia i decyzje domyślne
1. Model update: `systemd host updater` (rekomendowany).
2. Brak automatycznego rollbacku w skrypcie.
3. Nazwa usługi compose: `agent`.
4. Stały katalog deploymentu: `/opt/smart-agent`.
5. UI może wysyłać cały `.env`, ale operacyjnie kluczowe są `AGENT_IMAGE` i `AGENT_TAG`.
