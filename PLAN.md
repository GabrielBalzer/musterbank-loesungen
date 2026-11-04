# Plan: Musterbank AG

Dieses Dokument enthält alle Spoiler. Es gehört zum Lösungspaket und darf nicht in `musterbank/` landen.

## Die Welt

Die **Musterbank AG** ist eine fiktive Regionalbank aus dem ebenso fiktiven Musterstadt. Ihre Kernbank entstand ab 2011 als Eigenentwicklung eines kleinen Inhouse-Teams und wurde über die Jahre immer weiter ergänzt. Daher kommen die großen Klassen, kopierten Berechnungen und uneinheitlichen Namen.

2019 übernahm die Bank das Zahlungs-Start-up **Pfennigflug GmbH**, ebenfalls fiktiv. Dessen Überweisungsdienst wurde nicht integriert, sondern als eigener Prozess vor die Kernbank gesetzt. Seitdem gibt es zwei Stile: typisierte Dataclasses in `payments/` und gewachsener Code in `core/`. Das Online-Banking in `web/` ist schlicht, funktioniert und wurde lange nicht angefasst.

Die Hausregeln für Code-Reviews entstanden nach der Übernahme und gelten für neuen Code. Der Altbestand hält sie nicht überall ein.

## Modulschnitt

| Modul | Inhalt | Stil | Zeilen (ca.) |
|---|---|---|---|
| `core/` | `BankCore` als große Klasse und öffentliche Fassade, Zinsberechnung, Tagesende, Schema und Migrationen, `money`, `iban`, `dates` | gewachsen | 1.800 |
| `payments/` | HTTP-API, Service, Repository, Modelle; bucht per Import über `core` | Pfennigflug | 500 |
| `statements/` | Kontoauszüge und Umsatzabfragen als Bibliothek und CLI | gemischt | 350 |
| `web/` | Login, Kontenübersicht, Umsätze, Überweisung, Auszug; serverseitig gerendert; ruft die Payments-API über localhost auf | schlicht | 600 |
| `tools/` | `generate_data`, `loadgen` | sachlich | 500 |
| `run.py` | zentraler Einstieg | sachlich | 150 |

Die Zinsberechnung liegt bewusst in `BankCore` und nicht in einem eigenen Modul, damit die Strangler-Aufgabe echte Arbeit ist.

### Stabile Schnittstellen

Diese Schnittstellen dokumentiert `docs/architektur.md`, und die Selbstchecks nutzen nur sie:

- **Fassade:** `core.bank.BankCore(db_path)` mit `open_account`, `get_balance`, `post_booking`, `debit`, `credit`, `calculate_interest(iban, from_date, to_date)`, `run_end_of_day(date)`
- **Helfer:** `core.money.to_cents`, `core.iban.validate_iban`
- **HTTP:** `POST /transfers`, `GET /transfers/{id}`, `GET /accounts/{iban}/balance`, `GET /health`
- **Datenbank:** die Tabellen unten; Erweiterungen laufen über `core/migrations/`

## Datenmodell

SQLite, Beträge als Ganzzahl in Cent.

| Tabelle | Wichtige Spalten |
|---|---|
| `customers` | `id`, `customer_no`, `kind`, `first_name`, `last_name`, `company_name`, `birth_date`, `street`, `zip`, `city`, `email` |
| `products` | `code`, `name`, `day_count`, `credit_rate_bp`, `debit_rate_bp`, `monthly_fee_cents`, `closing_cycle` |
| `accounts` | `id`, `iban`, `customer_id`, `product_code`, `balance_cents`, `overdraft_limit_cents`, `opened_on`, `closed_on`, `status`, `maturity_date` |
| `bookings` | `id`, `account_id`, `booking_date`, `value_date`, `amount_cents`, `kind`, `counterparty_name`, `counterparty_iban`, `purpose`, `transfer_id` |
| `transfers` | `id`, `debtor_iban`, `creditor_iban`, `creditor_name`, `amount_cents`, `purpose`, `status`, `created_at` |
| `eod_runs` | `business_date`, `started_at`, `finished_at`, `checksum` |
| `eod_results` | `business_date`, `iban`, `interest_cents`, `fee_cents`, `closing_balance_cents` |
| `dunning_notices` | `iban`, `level`, `notice_date`, `excess_cents`, `fee_cents`, `resolved_on` |
| `mailbox_messages` | `customer_id`, `created_at`, `subject`, `body`, `read_at` |
| `web_sessions` | `token`, `customer_id`, `expires_at` |
| `schema_version` | `version`, `applied_at` |

Überweisungen an fremde Banken laufen über ein internes Verrechnungskonto. Dadurch bleibt die Summe aller Salden konstant, was der Idempotenz-Check nutzt.

### Produkte und Zinsregeln

`docs/produkte.md` und `docs/glossar.md` sind der Maßstab für richtig und falsch. Jeder eingebaute Fehler weicht von einer dort dokumentierten Regel ab.

| Produkt | Zinstage | Haben | Soll | Gebühr | Abschluss |
|---|---|---|---|---|---|
| `GIRO` | 30E/360 | 0,00 % | 11,50 % | 4,90 € monatlich | quartalsweise |
| `TAGESGELD` | ACT/365 | 1,50 % | – | – | monatlich |
| `FESTGELD` | ACT/360 | 2,50 % | – | – | bei Fälligkeit |

Regeln:
- Maßgeblich für die Zinsen ist der Tagesendsaldo nach **Valuta**, für jeden Kalendertag der Periode einschließlich ihres letzten Tags.
- Gerechnet wird tagesgenau mit `Decimal`. Das Ergebnis wird am Ende **kaufmännisch** auf Cent gerundet.
- Die Valuta richtet sich nach dem Bankarbeitstag in **Europe/Berlin**.

### Daten

Zeitraum ist das Kalenderjahr 2025. Der Generator schreibt direkt per SQL und nicht über `core`, damit Bugfixes die Daten und damit die Prüfsumme nicht verändern.

| Datensatz | Kunden | Buchungen | Erzeugung | Tagesende |
|---|---|---|---|---|
| Standard | 2.000 | etwa 310.000 | unter 5 s | wenige Sekunden |
| Groß (`--customers 40000`) | 40.000 | etwa 6,2 Mio. | unter 1 Minute | einige Minuten |

`BERICHT.md` enthält die gemessenen Zeiten.

Fiktive Daten:
- BLZ der Musterbank: `01234500`; fremde Banken ebenfalls mit führender 0, denn echte deutsche BLZ beginnen nie mit 0
- BIC: `MUBKDE00XXX`, die `0` an der achten Stelle kennzeichnet einen Test-BIC
- Postleitzahlen `00xxx`, Orte erfunden, E-Mails auf `example.org`
- Personen aus getrennten Listen für Vor- und Nachnamen, keine bekannten Namen, Firmen mit erfundenen Namen

Eine Websuche nach „Pfennigflug" lieferte keinen Treffer auf eine Firma. Das ersetzt keine Registerprüfung.

## Abhängigkeiten und Einbettung

Die Bank selbst läuft mit der Standardbibliothek, ein `run.py setup` ist dafür nicht nötig. pytest und coverage liegen als reine Wheels in `vendor/`, geladen werden die für Python 3.10 und neuer aufgelösten Pakete:

`pytest 9.2.0`, `pluggy 1.7.0`, `iniconfig 2.3.1`, `packaging 26.3`, `pygments 2.21.0`, `coverage 7.16.2`, dazu `exceptiongroup`, `tomli` und `typing_extensions` für Python 3.10. Beim Bau prüft `package.py`, dass alle Wheels die Endung `py3-none-any` tragen. Die Lizenzen stehen in `THIRD_PARTY.md`.

`run.py setup` geht so vor:
1. `python3 -m venv .venv`, dann `pip install --no-index --find-links vendor/ -r requirements-dev.txt`.
2. Fehlt `venv` oder `pip`, entpackt es die Wheels per `zipfile` nach `.deps/` und setzt `PYTHONPATH`.

Das Lösungspaket bringt keine eigenen Abhängigkeiten mit und nutzt die Testwerkzeuge aus dem Repo, das es prüft.

## Aufgabenmenü

`CHALLENGES.md` listet alles als Angebot, ohne Punkte, Abgabe oder Reihenfolge.

### Feature-Tickets

Jedes Ticket enthält ID, Titel, Beschreibung, fachliche Akzeptanzkriterien und die öffentliche Schnittstelle.

| ID | Titel | Schwierigkeit |
|---|---|---|
| MB-101 | Dispo-Limit pro Konto | leicht |
| MB-102 | Benachrichtigung bei großen Abbuchungen | leicht |
| MB-103 | Umsatzsuche mit Filtern | leicht |
| MB-104 | Daueraufträge | mittel |
| MB-105 | Empfängerüberprüfung (Match / Close Match / No Match) | mittel |
| MB-106 | Jahreszinsbescheinigung | mittel |
| MB-107 | Kontoauszug im camt.053-Format | schwer |
| MB-108 | Sammelüberweisung per pain.001-Import | schwer |

### Challenge-Tickets

| ID | Titel | Rückmeldung |
|---|---|---|
| MB-201 | Fehler in der Kernbank finden und mit Tests belegen | `check.py bugs` |
| MB-202 | Überweisungs-API idempotent machen | `check.py idempotenz` |
| MB-203 | Zinsberechnung aus `core` herauslösen | Prüfsumme von `run.py eod` |
| MB-204 | Tagesende beschleunigen | Prüfsumme und Laufzeit von `run.py eod` |
| MB-205 | Online-Banking barrierefrei machen | `check.py a11y` |
| MB-206 | Review-Agent für `reviews/` bauen | `check.py reviews` |
| MB-207 | Testsuite schärfen | `run.py test --cov`, die Fehler aus MB-201; wer mag, baut sich einen eigenen Mutator |

Hinweis für MB-203 und MB-204: Die Prüfsumme ändert sich, sobald jemand fachliche Fehler in den Zinsen behebt. `CHALLENGES.md` empfiehlt deshalb allgemein, Umbauten und fachliche Änderungen getrennt zu halten und die Prüfsumme vorab zu notieren.

## Eingebaute Fehler

Jeder Fehler ist in der Entwicklung ein eigener Commit auf `clean-baseline`. Die Spalte „Prüfsumme" gibt an, ob er die Ausgabe von `run.py eod` verändert.

| ID | Ort | Abweichung | Maßstab | Warum Bestandstests ihn nicht finden | Prüfsumme |
|---|---|---|---|---|---|
| M1 | `core/money.py`, `to_cents` | `int(amount * 100)` schneidet ab: 19,99 € werden 1998 Cent | ADR-001, centgenaue Beträge | nur runde Testbeträge | nein |
| M2 | Zinsberechnung in `BankCore` | `FESTGELD` teilt durch 365 statt 360 | Produktblatt | prüft nur Zinsen > 0 | ja |
| M3 | `BankCore.debit` | Liest den Saldo, prüft und schreibt ihn absolut zurück, ohne Transaktion: Lost Update | Architektur, konsistente Salden | Tests laufen sequenziell | nein |
| M4 | `BankCore.post_booking` | Valuta nimmt das UTC-Datum statt des Berliner Datums | Glossar, Valuta | Testzeiten liegen mittags | nein |
| M5 | Zinsberechnung in `BankCore` | `quantize` ohne Rundungsart: Banker's Rounding statt kaufmännisch | Glossar, Rundung | keine Halb-Cent-Fälle | ja |
| M6 | `core/iban.py` | Schneidet auf 22 Zeichen ab und prüft die Länge nicht: zu lange IBANs gelten als gültig | Glossar, IBAN | nur ein gültiger Fall und eine falsche Prüfziffer | nein |
| M7 | Periodenermittlung im Tagesende | Der Monatsletzte fehlt in der Abschlussperiode | Glossar, Zinstage | prüft nur, dass gebucht wird | ja |
| M8 | Zinsberechnung in `BankCore` | Tagessalden nach Buchungsdatum statt nach Valuta | Glossar, Valuta | in den Fixtures sind beide Daten gleich | ja |

Damit jeder Check für sich grün werden kann:
- M7 sitzt in der Periodenermittlung und nicht in `calculate_interest`. M2, M5 und M8 rufen `calculate_interest` direkt auf.
- Der Check für M2 nutzt `FESTGELD` ohne Halb-Cent-Ergebnis, der für M8 `TAGESGELD`.
- Kein Bestandstest schreibt fehlerhafte Werte fest. Ein Fix macht also keinen Test rot.

### Weitere eingebaute Mängel

**Nicht idempotent (MB-202):** `POST /transfers` bucht bei jedem Aufruf. Ein Referenz-Patch ergänzt den Header `Idempotency-Key` mit Unique-Constraint und Transaktion. `web/` und `loadgen` senden ihn mit.

**Langsames Tagesende (MB-204):**
- P1: Je Konto eigene Abfragen für Konto, Produkt, Buchungen und Saldenabgleich (N+1).
- P2: Für jeden Tag der Periode werden alle Buchungen des Kontos durchlaufen (quadratisch).
- P3: Kunden werden je Konto linear in einer Liste gesucht, bearbeitete Konten stehen in einer Liste statt in einer Menge, und jedes Konto hat eine eigene Transaktion.

**Barrierefreiheit (MB-205):**

| ID | Mangel |
|---|---|
| A1 | `<html>` ohne `lang` |
| A2 | Eingabefelder ohne `<label>` |
| A3 | Tabellen ohne `<th>` und ohne Beschriftung |
| A4 | Text mit zu wenig Kontrast, unter 4,5:1 |
| A5 | `<div onclick>` statt Link oder Button, per Tastatur nicht erreichbar |
| A6 | `outline: none` ohne sichtbaren Fokus-Ersatz |
| A7 | Bilder ohne `alt` |
| A8 | Gleicher Seitentitel überall und keine `<h1>` |

## Review-Diffs

16 Dateien `reviews/PR-1001.diff` bis `PR-1016.diff`, jede mit kurzer Beschreibung vor dem Diff. Jeder Diff lässt sich auf den Stand im Zip anwenden; das prüfe ich in der Entwicklung.

| Hausregel | Verstöße | Saubere Diffs, die dieser Regel ähneln |
|---|---|---|
| R1: kein Float für Geld | 2 | Float für einen Fortschrittswert |
| R2: zahlungsauslösende Endpunkte mit Idempotency-Key | 2 | neuer Endpunkt, der nur liest |
| R3: keine personenbezogenen Daten im Log | 2 | Log mit maskierter IBAN |
| R4: SQL nur parametrisiert | 2 | f-String, der nur einen festen Tabellennamen einsetzt |

Dazu kommen 4 unauffällige saubere Diffs, also 8 Verstöße und 8 saubere Diffs. MB-206 legt das Ausgabeformat fest: `reviews/verdicts.json` mit PR-ID, `approve` oder `reject` und verletzten Regeln.

## Selbstcheck

Das ist kein Punktesystem. `check.py` listet nur, welche Prüfungen bestehen.

```text
python3 check.py ../musterbank bugs

M1  Betragsumrechnung     FEHLT
M2  Festgeld-Zinsen       OK
...
```

| Bereich | Inhalt | Vorgehen |
|---|---|---|
| `bugs` | Je ein Test für M1 bis M8 | M3 hält über `sqlite_sync.py` einen Thread nach dem Lesen an, statt auf Timing zu hoffen |
| `idempotenz` | Duplikate nacheinander, parallel mit gleichem Key, Abbruch nach dem Senden samt Retry, Abbruch mitten im Body, gleicher Key mit anderem Inhalt, Summe aller Salden | Server läuft im selben Prozess, die Parallelität steuert `sqlite_sync.py` |
| `a11y` | A1 bis A8 | `html.parser` auf den gerenderten Seiten, Kontrast aus dem CSS berechnet |
| `reviews` | `verdicts.json` gegen den Schlüssel | Zeigt je Regel Treffer, Fehlalarme und übersehene Verstöße |

MB-203 und MB-204 prüfen die Teams über die Prüfsumme. `LOESUNG.md` nennt für den Standarddatensatz die Prüfsumme des Ausgangsstands und des Stands mit allen Patches.

Zu den Patches: M1 bis M8, Performance und Barrierefreiheit sind die umgekehrten Commits. Der Idempotenz-Patch ist neu geschrieben, weil es dafür keinen sauberen Vorgängerstand gibt.

## Bewusst weggelassen

- Selbstchecks und Referenzlösungen für Feature-Tickets: Sie würden einen Nachbau aller 8 Features verlangen. Die Akzeptanzkriterien stehen im Ticket, und die Teams schreiben ihre Tests selbst.
- Referenz für den Strangler (MB-203): Die Prüfsumme genügt als Rückmeldung.
- Mutator: Nur nötig, wenn Teams verglichen werden. Wer möchte, baut sich mit KI einen eigenen.
- Echte Sicherheit im Online-Banking: Demo-PIN für alle Kunden, nur fiktive Daten, nur localhost. `docs/README.md` sagt das offen.
