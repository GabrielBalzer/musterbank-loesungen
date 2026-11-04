# Lösungsheft Musterbank AG

Achtung, Spoiler. Das Heft richtet sich an alle, die ihre Lösung vergleichen möchten oder nicht weiterkommen.

## So prüft ihr euren Stand

```bash
python3 check.py ../musterbank            # alles
python3 check.py ../musterbank bugs       # auch: idempotenz, a11y, reviews
python3 check.py ../musterbank bugs -v    # mit Fehlermeldungen
```

Die Checks nutzen die Schnittstellen aus `docs/architektur.md` und die Testwerkzeuge des geprüften Repos. Das Ergebnis ist eine Liste aus OK und FEHLT, Punkte gibt es keine.

In `patches/` liegt zu jedem Thema ein Referenz-Fix. Alle Patches sind unabhängig voneinander und lassen sich einzeln anwenden, zum Beispiel aus dem Repo heraus mit `git apply ../musterbank-loesungen/patches/M2.diff`.

## Prüfsummen

Für den Standarddatensatz (`python3 run.py data`, `python3 run.py eod`):

| Stand | Prüfsumme |
|---|---|
| Ausgangsstand | `caea4c6171f6268017850549d0e3a982d480f6b45c9f9eb77cb70f7e9aeb666e` |
| Alle Fehler behoben | `b2b5d9fe335541470cd591d91ee1dbfbacf7b754816266ebdf302a9651c3fd4b` |

M2, M5, M7 und M8 können die Prüfsumme ändern, weil sie Zinsen betreffen. Performance-Patch und Strangler-Umbau ändern sie nicht. Auf dem Standarddatensatz gibt es bei M5 keinen Fall mit genau einem halben Cent, dieser Fix ändert die Prüfsumme dort also nicht.

## Die 8 Fehler in der Kernbank (MB-201)

### M1: Beträge verlieren einen Cent

- **Ort:** `core/money.py`, `to_cents`
- **Symptom:** 19,99 € werden zu 1.998 Cent, 0,29 € zu 28 Cent. Überweisungen buchen dadurch einen Cent zu wenig.
- **Ursache:** `int(value * 100)` schneidet das Ergebnis der Float-Rechnung ab.
- **Maßstab:** ADR-001 und Glossar, Abschnitt „Beträge"
- **Warum die Tests es nicht sehen:** Sie nutzen nur Beträge, die als Float exakt darstellbar sind.
- **Fix:** Über `Decimal(str(amount))` umrechnen und auf Cent runden. `patches/M1.diff`
- **Check:** `test_m1`

### M2: Festgeld rechnet mit dem falschen Jahr

- **Ort:** `core/bank.py`, `BankCore._day_basis`
- **Symptom:** 100.000,00 € zu 2,50 % über 90 Tage ergeben 616,44 € statt 625,00 €.
- **Ursache:** `ACT/360` fällt in den Zweig für 365 Tage.
- **Maßstab:** `docs/produkte.md` und Glossar, Abschnitt „Zinstage-Konventionen"
- **Warum die Tests es nicht sehen:** Der Festgeld-Test prüft nur, dass Zinsen größer als null sind.
- **Fix:** 365 nur für `ACT/365`, sonst 360. `patches/M2.diff`
- **Check:** `test_m2`

### M3: Parallele Abbuchungen verlieren Geld

- **Ort:** `core/bank.py`, `BankCore.debit`
- **Symptom:** Zwei gleichzeitige Abbuchungen von je 100 € senken den Saldo nur um 100 €, im Journal stehen aber zwei Buchungen. `tools/reconcile.py` meldet danach eine Differenz.
- **Ursache:** Der Saldo wird gelesen, geprüft und absolut zurückgeschrieben, ohne Transaktion (Lost Update).
- **Maßstab:** `docs/architektur.md`, Abschnitt „Grundregeln der Buchhaltung"
- **Warum die Tests es nicht sehen:** Alle Tests laufen nacheinander. Überweisungen sind nicht betroffen, weil `post_transfer` eine Transaktion öffnet.
- **Fix:** Lesen, Prüfen und Schreiben in `with self.transaction()`. `patches/M3.diff`
- **Check:** `test_m3`. `checks/sqlite_sync.py` hält beide Threads nach jedem Lesen an, das Ergebnis hängt also nicht vom Timing ab.

### M4: Buchungen kurz nach Mitternacht landen auf dem Vortag

- **Ort:** `core/bank.py`, `BankCore._booking_days`
- **Symptom:** Eine Buchung um 00:30 Uhr Berliner Zeit erhält Buchungstag und Valuta des Vortags.
- **Ursache:** `moment.date()` nimmt das UTC-Datum.
- **Maßstab:** Glossar, Abschnitte „Buchungstag" und „Valuta"
- **Warum die Tests es nicht sehen:** Alle Tests buchen mittags.
- **Fix:** `berlin_date(moment)`. `patches/M4.diff`
- **Check:** `test_m4`

### M5: Banker's Rounding statt kaufmännischer Rundung

- **Ort:** `core/bank.py`, `BankCore._round_interest`
- **Symptom:** 4,5 Cent werden zu 4 Cent, 10,5 Cent zu 10 Cent.
- **Ursache:** `quantize` ohne Rundungsart nutzt die Voreinstellung `ROUND_HALF_EVEN`.
- **Maßstab:** Glossar, Abschnitt „Rundung"
- **Warum die Tests es nicht sehen:** Kein Test trifft einen halben Cent.
- **Fix:** `rounding=ROUND_HALF_UP`. `patches/M5.diff`
- **Check:** `test_m5`

### M6: Zu lange und zu kurze IBANs gelten als gültig

- **Ort:** `core/iban.py`, `validate_iban`
- **Symptom:** Eine gültige IBAN mit angehängten Zeichen besteht die Prüfung, eine gekürzte mit passender Prüfziffer ebenfalls. Gültige IBANs mit mehr als 22 Zeichen, etwa aus Frankreich, fallen durch.
- **Ursache:** Die Eingabe wird auf 22 Zeichen abgeschnitten, und die Länge je Land wird nicht geprüft.
- **Maßstab:** Glossar, Abschnitt „IBAN"
- **Warum die Tests es nicht sehen:** Sie prüfen nur einen gültigen Fall und eine falsche Prüfziffer.
- **Fix:** Längentabelle je Land, kein Abschneiden. `patches/M6.diff`
- **Check:** `test_m6`

### M7: Dem Monatsabschluss fehlt der letzte Tag

- **Ort:** `core/eod.py`, `EndOfDayProcessor._closing_period`
- **Symptom:** Der Abschluss für März rechnet nur bis zum 30. März. Bei 73.000 € Tagesgeld fehlen 3,00 €.
- **Ursache:** Die Periode endet einen Tag vor dem Abschlusstag.
- **Maßstab:** Glossar, Abschnitt „Zinsperiode"
- **Warum die Tests es nicht sehen:** Sie prüfen nur, dass überhaupt Zinsen gebucht werden.
- **Fix:** Die Periode endet am Abschlusstag. `patches/M7.diff`
- **Check:** `test_m7`

### M8: Zinsen ignorieren die Valuta

- **Ort:** `core/bank.py`, `BankCore._interest_rows`
- **Symptom:** Eine rückvalutierte Gutschrift bringt für die Tage vor dem Buchungstag keine Zinsen.
- **Ursache:** Die Tagessalden entstehen aus `booking_date` statt aus `value_date`.
- **Maßstab:** Glossar, Abschnitt „Valuta"
- **Warum die Tests es nicht sehen:** In den exakten Testfällen sind Buchungstag und Valuta gleich.
- **Fix:** `value_date` in der Abfrage. `patches/M8.diff`
- **Check:** `test_m8`

## Idempotenz (MB-202)

Der Referenz-Fix `patches/idempotenz.diff` legt in einer Transaktion mit `BEGIN IMMEDIATE`:

1. Key nachschlagen. Gleicher Fingerabdruck: gespeicherte Antwort wiederholen. Anderer: `422`.
2. Überweisung in einem Savepoint ausführen. Ablehnungen rollen nur den Savepoint zurück.
3. Antwort unter dem Key speichern.

Der Primärschlüssel und die Schreibtransaktion machen das auch über mehrere Prozesse sicher. `400` für ungültige Anfragen wird nicht gespeichert, weil noch nichts ausgeführt wurde.

## Strangler (MB-203)

Dafür gibt es keinen Referenz-Fix, die Prüfsumme genügt als Rückmeldung. Fallen, auf die ihr achten solltet:

- `_interest_from_rows`, `_day_basis`, `_day_weight`, `_round_interest` und `_interest_rows` gehören zusammen.
- `core/eod.py` ruft die Berechnung ebenfalls auf.
- `core/reports.py` enthält mit `interest_forecast` eine eigene grobe Schätzung. Sie ist bewusst keine echte Zinsberechnung, sollte aber nicht versehentlich wegfallen.

## Performance (MB-204)

Die Ursachen, alle in `core/eod.py` und `BankCore._interest_from_rows`:

| Ursache | Wirkung |
|---|---|
| Für jeden Tag der Periode werden alle Buchungen des Kontos durchlaufen und die Datumswerte neu geparst | quadratisch, größter Anteil |
| Je Konto eigene Abfragen für Konto, Produkt, Buchungen und Saldenabgleich | N+1 |
| Kunden werden je Konto linear in einer Liste gesucht | quadratisch über die Kundenzahl |
| Bearbeitete Konten stehen für den Wiederanlauf in einer Liste statt in einer Menge | quadratisch über die Kontenzahl |
| Jedes Konto hat eine eigene Transaktion | je Konto ein Schreibvorgang auf die Platte |

Der Fix `patches/performance.diff` lädt alle Buchungen einmal, gruppiert sie und läuft mit einem Zeiger durch die Tage. Die Prüfsumme bleibt gleich. `BERICHT.md` enthält die gemessenen Zeiten.

## Barrierefreiheit (MB-205)

`check.py a11y` prüft statisch die gerenderten Seiten und das Stylesheet.

| ID | Mangel | Ort | Fix |
|---|---|---|---|
| A1 | `<html>` ohne `lang` | `layout.html` | `lang="de"` |
| A2 | Felder nur mit Platzhalter | alle Formulare | `<label for>` mit passender `id` |
| A3 | Tabellen ohne Kopfzellen | Übersicht, Umsätze, Auszug, Postfach | `<th scope="col">`, `<caption>` |
| A4 | Zu wenig Kontrast | `style.css` | Farben mit mindestens 4,5:1 |
| A5 | `<div onclick>` und `<tr onclick>`, Formulare ohne Absende-Button | Menü, Zeilen, Knöpfe | echte `<a>` und `<button>` |
| A6 | `outline: none` | `style.css` | sichtbarer `:focus-visible` |
| A7 | Logo ohne `alt` | `layout.html` | `alt="Musterbank AG"` |
| A8 | Überall derselbe Titel, keine `<h1>` | `layout.html`, `page()`, alle Seiten | Titel je Seite, `<h1>` statt `.title` |

Zum Ausgangsstand gehören außerdem Dinge, die der Check nicht sieht: fehlender Sprunglink, Fehlermeldungen ohne `role="alert"` und nur per Farbe erkennbare Meldungen. `patches/barrierefreiheit.diff` behebt auch sie.

## Reviews (MB-206)

| PR | Thema | Entscheidung | Regel | Begründung |
|---|---|---|---|---|
| PR-1001 | Glossar um SEPA ergänzen | annehmen | – | Nur Doku |
| PR-1002 | Kundensuche nach Ort | ablehnen | R4 | Ort per f-String im SQL |
| PR-1003 | Durchschnittliche Monatsausgaben | ablehnen | R1 | Durchschnitt als Float in Euro |
| PR-1004 | Fortschrittsanzeige im Generator | annehmen | – | Float ist ein Prozentwert, kein Geld |
| PR-1005 | Sofortüberweisung als Endpunkt | ablehnen | R2 | Bewegt Geld ohne Idempotency-Key |
| PR-1006 | Überziehungsrahmen lesen | annehmen | – | Rein lesend, Beträge in Cent |
| PR-1007 | Log ausgeführter Überweisungen | ablehnen | R3 | Vollständige IBANs und Name im Log |
| PR-1008 | Abgelehnte Überweisungen im Log | annehmen | – | IBAN ist maskiert |
| PR-1009 | Suche im Verwendungszweck | ablehnen | R4 | Suchtext per Verkettung im SQL |
| PR-1010 | Anzahl offener Mahnungen | annehmen | – | f-String nur mit Konstante, IBAN als Parameter |
| PR-1011 | Rabatt für Vereine | ablehnen | R1 | Gebühr als Float in Euro |
| PR-1012 | Fehlgeschlagene Anmeldungen | ablehnen | R3 | E-Mail und Name im Log |
| PR-1013 | Status mit Prozess-ID | annehmen | – | Nur Werkzeugausgabe |
| PR-1014 | Festgeld-Auszahlung per API | ablehnen | R2 | Bewegt Geld ohne Idempotency-Key |
| PR-1015 | Anzahl Buchungen im Auszug | annehmen | – | Reine Anzeige |
| PR-1016 | Adressänderung per API | annehmen | – | Schreibt, bewegt aber kein Geld |

PR-1004, 1006, 1008, 1010 und 1016 sind die schwierigen Fälle: Sie sehen aus wie ein Verstoß, sind aber keiner.

## Testqualität (MB-207)

Dafür gibt es keinen automatischen Check. Eine einfache Kontrolle: Schreibt eure Tests, nehmt dann einzelne Patches zurück oder baut Fehler wieder ein. Eure Suite sollte jedes Mal rot werden.
