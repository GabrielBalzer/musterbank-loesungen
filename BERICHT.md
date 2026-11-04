# Abschlussbericht Musterbank AG

## Ergebnis

Der Use Case ist fertig und offline geprüft. Der Hackathon läuft ohne Jury, deshalb gibt es statt `score` und `leaderboard` einen Selbstcheck.

| Paket | Inhalt | Größe |
|---|---|---|
| `dist/musterbank-teams.zip` | Bank, 15 Tickets, 16 Review-Diffs, Doku, Aufgabenmenü, 9 reine Wheels, frisches `.git` mit einem Commit | 4,4 MB |
| `dist/musterbank-loesungen.zip` | Plan, Lösungsheft, `check.py`, 29 Prüfungen, 11 Patches | unter 0,1 MB |
| `dist/SHA256SUMS` | Prüfsummen beider Zips | |

## Gebaut

- **Produktivcode:** 3.340 Zeilen Python, dazu 256 Zeilen Templates, CSS und SQL.
- **Bestandstests:** 158 Tests, 1.205 Zeilen, 96 % Coverage, rund 20 Sekunden Laufzeit.
- **Eingebaut:** 8 Geld-Fehler, nicht idempotente Überweisungs-API, langsames Tagesende, 8 Mängel bei der Barrierefreiheit.
- **Tickets:** 8 Features und 7 Challenges.
- **Reviews:** 8 Diffs mit Verstoß und 8 saubere, davon 5 schwierige Fälle.

## Simulation der Sandbox

Beide Zips wurden frisch entpackt und mit `--network none` durchgespielt, auf jedem Image einmal nur mit `python3` und einmal zusätzlich mit `pip`, `venv` und `git`. Alle 6 Läufe endeten ohne Abweichung.

Laufzeiten in Sekunden:

| Image | Python | Variante | Setup | Daten | Tests mit Coverage | Tagesende | Alle Checks |
|---|---|---|---|---|---|---|---|
| Ubuntu 22.04 | 3.10.12 | minimal | 0,08 | 1,49 | 20,21 | 3,49 | 9,09 |
| Ubuntu 22.04 | 3.10.12 | voll | 1,77 | 1,50 | 19,59 | 3,51 | 9,15 |
| Ubuntu 24.04 | 3.12.3 | minimal | 0,09 | 1,45 | 20,52 | 3,76 | 9,13 |
| Ubuntu 24.04 | 3.12.3 | voll | 1,92 | 1,42 | 21,51 | 3,34 | 9,03 |
| Ubuntu 26.04 | 3.14.4 | minimal | 0,10 | 1,46 | 19,42 | 3,45 | 8,98 |
| Ubuntu 26.04 | 3.14.4 | voll | 1,51 | 1,39 | 18,39 | 3,48 | 8,89 |

Die Prüfsumme des Tagesendes ist auf allen Python-Versionen gleich.

## Definition of Done

| Kriterium | Ergebnis |
|---|---|
| Unverändertes Repo: Bestandstests grün | erfüllt, 158 von 158 |
| Unverändertes Repo: Fehler-Checks rot | erfüllt, 8 von 8 |
| Jeder Geld-Patch allein macht genau seinen Check grün | erfüllt, je Patch geprüft |
| Performance-Patch ändert die Prüfsumme nicht | erfüllt |
| Alle Patches: alle Prüfungen grün | erfüllt, 29 von 29 |
| Alle Patches ergeben die Prüfsumme des sauberen Stands | erfüllt |
| Parallel-Checks deterministisch | erfüllt, je 10 Läufe. Eine bewusst naive Idempotenz-Lösung fiel 10 von 10 Mal durch, die Referenz bestand 10 von 10 Mal. |
| `.git` im Teilnehmer-Zip mit genau einem Commit | erfüllt |

Auf dem unveränderten Repo bestehen 2 der 29 Prüfungen. Das ist richtig so: „Abbruch mitten im Body" und „Abgelehnte Überweisungen hinterlassen keine Buchung" funktionieren schon im Ausgangsstand.

## Großer Datensatz

`--customers 40000` ergibt 58.624 Konten und 6,2 Mio. Buchungen. Die Erzeugung dauert 29 Sekunden.

| Stand | Tagesende | Prüfsumme |
|---|---|---|
| Ausgangsstand | 120,9 s | `4f9f6f31…` |
| Performance-Patch | 8,9 s | `4f9f6f31…` |

Das ist Faktor 13,6 bei identischer Prüfsumme.

## Leak-Check

Ein Subagent ohne Kenntnis des Lösungspakets hat das entpackte Teilnehmer-Zip durchsucht. Er fand keine direkten Nennungen von Fehlern, Lösungen oder Jury und keine Spuren des Entwicklungsrechners. `.git` enthielt nur den einen Commit.

Behoben wurden seine Funde zu:
- Beispiel in MB-206 mit echten PR-Nummern
- Glossarbeispiel im Festgeld-Test, Testkonstante `NOON`, nur binär exakte Testbeträge
- Fettdruck und treffsichere Beispiele im Glossar und in ADR-001
- Ticket-Formulierungen in MB-108, MB-203, MB-205 und MB-207
- Echter Firmenname „Telefonica" und weitere reale Namensbestandteile
- Künstlich wirkende Stellen: Liste bearbeiteter Konten, ungenutzter Seitentitel, ungenutzter Logger, Logofarbe

## Offene Punkte

1. **Leak-Check nicht wiederholt:** Er lief auf dem Zip vor den Korrekturen. Die Korrekturen sind per Suche bestätigt, ein zweiter unabhängiger Lauf fand nicht statt.
2. **Bewusst akzeptierte Muster:** Wer genau liest, sieht weiter den Wechsel zwischen exakten und schwachen Assertions, die Ausnahmen in den Hausregeln passend zu den schwierigen Reviews und `moment.date()` neben `berlin_date()`. Das gehört zur Aufgabe, denn der Maßstab muss in der Doku stehen und die Fehler müssen im Code stehen.
3. **Umfang:** Rund 3.600 Zeilen liegen etwas unter den geplanten 4.000. Ich habe nicht künstlich aufgefüllt.
4. **Plattform:** Geprüft wurde nur auf arm64, nicht auf x86_64. Der Code ist reines Python, Laufzeiten sind aber nicht übertragbar. „Einige Minuten" für das Tagesende sind hier rund zwei und können in der Sandbox länger sein.
5. **Sandbox-Version:** Die genaue Ubuntu- und Python-Version ist nicht bestätigt. Geprüft sind 22.04, 24.04 und 26.04.
6. **Feature-Tickets und Strangler:** Es gibt dafür weder Referenzlösung noch Check, ihre Lösbarkeit ist also nicht belegt.
7. **Namen:** Firmen- und Personennamen sind erfunden, aber nicht gegen ein Register geprüft.
