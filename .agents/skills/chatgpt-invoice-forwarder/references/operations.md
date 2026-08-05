# Lokale Operationen

Alle Befehle aus dem Repository ausführen. Unter Windows:

```powershell
& .\.agents\skills\chatgpt-invoice-forwarder\scripts\run_helper.ps1 status
& .\.agents\skills\chatgpt-invoice-forwarder\scripts\run_helper.ps1 guard
```

Unter macOS:

```sh
./.agents/skills/chatgpt-invoice-forwarder/scripts/run_helper.sh status
./.agents/skills/chatgpt-invoice-forwarder/scripts/run_helper.sh guard
```

Einmalige OAuth-Einrichtung:

```powershell
& .\.agents\skills\chatgpt-invoice-forwarder\scripts\run_helper.ps1 auth --client-secret C:\sicher\client_secret.json
```

```sh
./.agents/skills/chatgpt-invoice-forwarder/scripts/run_helper.sh auth \
  --client-secret "$HOME/sicher/client_secret.json"
```

Die Freigabe umfasst `gmail.send` und `gmail.readonly`. Windows speichert sie per DPAPI, macOS im Schlüsselbund. Nach einer älteren `gmail.send`-Einrichtung `auth` erneut ausführen.

Download übernehmen:

```powershell
& .\.agents\skills\chatgpt-invoice-forwarder\scripts\run_helper.ps1 ingest `
  --download-started-at 2026-08-04T06:00:00Z `
  --invoice-date 2026-08-03 `
  --billing-name "<Name aus ChatGPT>" `
  --invoice-number "<Nummer aus Stripe>" `
  --source-url "<exakter Rechnungslink>"
```

```sh
./.agents/skills/chatgpt-invoice-forwarder/scripts/run_helper.sh ingest \
  --download-started-at 2026-08-04T06:00:00Z \
  --invoice-date 2026-08-03 \
  --billing-name "<Name aus ChatGPT>" \
  --invoice-number "<Nummer aus Stripe>" \
  --source-url "<exakter Rechnungslink>"
```

Versenden:

```powershell
& .\.agents\skills\chatgpt-invoice-forwarder\scripts\run_helper.ps1 send --invoice-id "<Rechnungs-ID>"
```

```sh
./.agents/skills/chatgpt-invoice-forwarder/scripts/run_helper.sh send --invoice-id "<Rechnungs-ID>"
```

Exitcodes:

- `0`: erfolgreich oder idempotenter No-op
- `3`: Konfigurations- oder Validierungsfehler
- `4`: dauerhafte Authentifizierungs-/Versandstörung
- `75`: temporäre Gmail-/Netzwerkstörung; später erneut versuchen

`--force` ausschließlich für den einmaligen, ausdrücklich autorisierten Abnahmelauf außerhalb des regulären Versandfensters verwenden.

`guard` liefert ab dem ersten zulässigen Kalendertag `run_required: true`, solange im lokalen Status noch keine versendete Rechnung für den laufenden Monat steht. Nach erfolgreichem Versand liefert jeder weitere stündliche Aufruf `run_required: false` und `reason: already_completed`.

Die Gmail-Prüfung verhindert Duplikate bei nacheinander gestarteten Läufen, ist aber kein atomarer Lock für sekundengleiche Starts.
