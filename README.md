# ChatGPT-Rechnungsagent

Der lokale Agent liest die neueste ChatGPT-Rechnung über eine bestehende Chrome-Sitzung, validiert und archiviert die PDF und sendet sie unter Windows oder macOS idempotent über die Gmail API.

Archiv und E-Mail-Anhang verwenden das Schema `Rechnung_CHATGPT_<Vorname_Nachname>_<MMYYYY>.pdf`. Der Personenname wird über `filename_name` in `config/agent.json` festgelegt.

## Einmalige Einrichtung

1. In der Google Cloud Console die Gmail API aktivieren und unter **APIs & Services → Credentials → Create credentials → OAuth client ID** ausdrücklich den Anwendungstyp **Desktop app** wählen. Ein Web-Client mit fester HTTPS-Callback-URL ist nicht kompatibel.
2. Die heruntergeladene Desktop-Client-JSON sicher ablegen. Sie wird nur für die Autorisierung eingelesen. Windows speichert die OAuth-Daten anschließend DPAPI-verschlüsselt, macOS im Schlüsselbund.
3. Die lokale Umgebung installieren.

   Windows:

   ```powershell
   .\scripts\setup.ps1
   ```

   macOS 11 oder neuer:

   ```sh
   ./scripts/setup.sh
   ```

4. OAuth mit `gmail.send` und `gmail.readonly` freigeben. Der Lesebereich wird ausschließlich zur Deduplizierung im Ordner „Gesendet“ verwendet.

   Windows:

   ```powershell
   .\.agents\skills\chatgpt-invoice-forwarder\scripts\run_helper.ps1 auth --client-secret C:\Pfad\client_secret.json
   ```

   macOS:

   ```sh
   ./.agents/skills/chatgpt-invoice-forwarder/scripts/run_helper.sh auth \
     --client-secret "$HOME/Pfad/client_secret.json"
   ```

Bestehende `gmail.send`-Anmeldungen müssen einmal erneut autorisiert werden. Laufzeitstatus und Rechnungsarchiv liegen im gitignorierten Ordner `runtime`.

## Status

```powershell
.\.agents\skills\chatgpt-invoice-forwarder\scripts\run_helper.ps1 status
```

```sh
./.agents/skills/chatgpt-invoice-forwarder/scripts/run_helper.sh status
```

Der geplante Codex-Lauf wird stündlich ausgeführt, solange der Rechner an ist. Vor jeder Browseraktion prüft `guard` den lokalen Status:

- Vor dem ersten zulässigen Tag des Monats wird nichts ausgeführt.
- Sobald eine Rechnung des laufenden Monats erfolgreich versendet wurde, bleibt der Monats-Schalter bis zum nächsten Monat geschlossen.
- Fehlgeschlagene oder verpasste Läufe schließen den Schalter nicht und werden beim nächsten stündlichen Start erneut versucht.

Der erste zulässige Tag ergibt sich aus `billing_day` plus dem kleinsten Wert in `retry_offsets_days` (aktuell der 4. Kalendertag). Danach bleibt das Fenster offen, damit ein ausgeschalteter Rechner keinen Monatslauf verpassen kann.
