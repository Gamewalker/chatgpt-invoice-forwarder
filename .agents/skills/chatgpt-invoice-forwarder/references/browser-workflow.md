# Browser-Workflow

## Grundregeln

- Unter Windows und macOS eine bestehende Chrome-Anmeldung verwenden; Safari nicht verwenden und keine Cookies oder Browserprofile exportieren.
- Vor jedem Klick einen aktuellen DOM-Snapshot als Locator-Grundlage verwenden und die Trefferzahl auf genau eins prüfen.
- Deutsche und englische Beschriftungen als mögliche UI-Varianten behandeln, aber ausschließlich tatsächlich sichtbare Beschriftungen verwenden.
- Keine Zahlungs-, Plan-, Adress- oder Kontodaten verändern.

## Erwarteter Pfad

1. Profilmenü öffnen.
2. **Einstellungen / Settings** öffnen.
3. Tab **Abrechnung / Billing** auswählen.
4. Im **Abrechnungsverlauf / Billing history** den neuesten bezahlten Eintrag bestimmen.
5. Den sichtbaren Rechnungslink öffnen.
6. In der Stripe-Ansicht Rechnungsnummer und Bezahldatum lesen.
7. Direkt vor dem Klick einen UTC-Zeitstempel erfassen.
8. Das Download-Ereignis für **Rechnung herunterladen / Download invoice** erwarten und genau diesen Button anklicken.

## Stoppsignale

- Login-Seite, MFA oder CAPTCHA: sofort stoppen und Benutzeraktion verlangen.
- Mehrere gleich neue Rechnungen oder mehrere neue PDFs im Download-Ordner: als mehrdeutig stoppen.
- Datum, Rechnungsnummer oder Aussteller stimmen nicht mit dem PDF überein: nicht senden.
- Nach einem erfolgreichen Download keine Quittung statt der Rechnung verwenden.
