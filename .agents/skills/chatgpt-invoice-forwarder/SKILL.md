---
name: chatgpt-invoice-forwarder
description: Download, validate, archive, and send a new ChatGPT subscription invoice exactly once on Windows or macOS. Use for scheduled or manual ChatGPT invoice processing through an authenticated Chrome session and Gmail API, including cross-device sent-mail deduplication, retries, status checks, and OAuth setup.
---

# ChatGPT Invoice Forwarder

Die neueste ChatGPT-Rechnung aus einer bestehenden Chrome-Sitzung abrufen und über den plattformgerechten, idempotenten Helfer an die konfigurierte Adresse senden.

## Voraussetzungen prüfen

1. Im Repository arbeiten und unter Windows `scripts/run_helper.ps1 status`, unter macOS `scripts/run_helper.sh status` ausführen.
2. Bei `oauth_configured: false` den Versand stoppen und eine einmalige Ausführung von `auth --client-secret <desktop-oauth.json>` verlangen. Nach der Scope-Erweiterung bestehende Installationen ebenfalls neu autorisieren.
3. Für Browseraktionen den verfügbaren Chrome-Control-Skill laden und dessen Sicherheits-, Snapshot- und Finalisierungsregeln vollständig befolgen.
4. Keine ChatGPT- oder Google-Passwörter, Cookies, MFA-Codes oder Tokens lesen, speichern oder in Prompts ausgeben.

## Rechnung verarbeiten

1. Den betriebssystemspezifischen Helfer mit `guard` ausführen. Nur bei `run_required: true` fortfahren; andernfalls ohne Browserzugriff sauber beenden. Der lokale Monats-Schalter wird erst durch eine erfolgreich versendete Rechnung geschlossen, damit verpasste oder fehlgeschlagene Läufe stündlich erneut versucht werden können.
2. Eine bestehende ChatGPT-Registerkarte in Chrome verwenden oder `https://chatgpt.com/` öffnen. Die Sitzung mit einem kurzen Rechnungsnamen benennen.
3. Über sichtbare UI und einen frischen DOM-Snapshot zu **Einstellungen → Abrechnung** navigieren. Keine Selektoren raten und vor jeder Interaktion Eindeutigkeit prüfen.
4. Aus dem Abrechnungsbereich den neuesten bezahlten Rechnungseintrag, das Rechnungsdatum, den Link und den aktuellen Abrechnungsnamen lesen. Nur eine Rechnung berücksichtigen, deren Datum mindestens einen Kalendertag zurückliegt.
5. Den Helfer mit `status --invoice-id <nummer>` prüfen, wenn die Rechnungsnummer schon sichtbar ist. Bei Status `sent` ohne Download oder Versand beenden.
6. Den UTC-Startzeitpunkt unmittelbar vor dem Download notieren. Den exakten Rechnungslink öffnen, die Rechnungsnummer aus der Stripe-Ansicht lesen und ausschließlich **Rechnung herunterladen** anklicken. Auf das Download-Ereignis warten.
7. Den Download mit `ingest` übernehmen. Rechnungslink nur als Argument übergeben; der Helfer speichert davon ausschließlich einen SHA-256-Hash. Die archivierte und angehängte Datei als `Rechnung_CHATGPT_<Vorname_Nachname>_<MMYYYY>.pdf` benennen; den Namen aus `filename_name` der Konfiguration verwenden.
8. Die ausgegebene Rechnungs-ID mit `send --invoice-id <id>` senden. Der Helfer prüft vor dem Versand zusätzlich Gmail „Gesendet“. Bei `noop: true` die Quelle `local_state` oder `gmail_sent` melden.
9. Browser-Registerkarten nach den Chrome-Regeln finalisieren; neu erzeugte Stripe-Zwischentabs nicht offen lassen.

Die genauen Befehle und Fehlerklassen in [references/operations.md](references/operations.md) lesen. Vor Browserarbeit die UI-Leitplanken in [references/browser-workflow.md](references/browser-workflow.md) lesen.

## Fehler behandeln

- Abgelaufene Anmeldung, MFA, CAPTCHA oder fehlendes OAuth als permanent und benutzerpflichtig melden. Nicht versuchen, Anmeldedaten zu umgehen.
- Eine noch nicht verfügbare Rechnung als ausstehend melden und beim nächsten stündlichen Lauf erneut prüfen.
- Netzwerk-, Download- und Gmail-Ratenlimitfehler als temporär behandeln und beim nächsten stündlichen Lauf erneut versuchen.
- Validierungsfehler niemals durch Umbenennen oder Senden umgehen. Keine Datei versenden, deren PDF-Signatur, Aussteller, Datum oder Rechnungsnummer nicht bestätigt wurde.
- Dieselbe Rechnungs-ID oder denselben PDF-Hash niemals zweimal senden.
- Einen Fehler bei der Gmail-Gesendet-Prüfung niemals durch direkten Versand umgehen.
