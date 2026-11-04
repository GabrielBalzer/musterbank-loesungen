"""Nachweise für die Fehler in der Kernbank. Jeder Test wird für sich grün."""
import threading
from datetime import datetime, timezone

import pytest
import sqlite_sync
from conftest import noon


def _iban_check(country, bban):
    digits = "".join(str(int(ch, 36)) for ch in bban + country + "00")
    return "%s%02d%s" % (country, 98 - int(digits) % 97, bban)


@pytest.mark.parametrize("amount,cents", [(19.99, 1999), (0.29, 29), (1.15, 115), (4.35, 435), (1.1, 110), (8.2, 820)])
def test_m1(amount, cents):
    """M1 Betragsumrechnung ist centgenau"""
    from core.money import to_cents

    assert to_cents(amount) == cents


def test_m2(bank, customer):
    """M2 Festgeld rechnet mit ACT/360"""
    iban = bank.open_account(customer, "FESTGELD", opened_on="2025-02-01", maturity_date="2025-05-01")
    bank.post_booking(iban, 10000000, "CREDIT", at=noon(2025, 2, 1), value_date="2025-02-01")
    assert bank.calculate_interest(iban, "2025-02-01", "2025-05-01") == 62500


def test_m3(db_path, bank, customer):
    """M3 Parallele Abbuchungen verlieren keinen Saldo"""
    from core.bank import BankCore

    iban = bank.open_account(customer, "GIRO", opened_on="2025-01-01")
    bank.post_booking(iban, 100000, "CREDIT", at=noon(2025, 1, 2), value_date="2025-01-02")
    errors = []
    opened = threading.Barrier(3)
    start = threading.Barrier(3)

    def worker():
        try:
            local = BankCore(db_path)
            opened.wait()
            start.wait()
            local.debit(iban, 10000, at=noon(2025, 1, 3))
            local.close()
        except Exception as exc:
            errors.append(exc)

    with sqlite_sync.instrumented():
        threads = [threading.Thread(target=worker) for _ in range(2)]
        for thread in threads:
            thread.start()
        # opening a connection reads the schema version, so the lockstep starts only afterwards
        opened.wait()
        sqlite_sync.arm()
        start.wait()
        for thread in threads:
            thread.join(30)
    assert not errors, errors
    assert bank.get_balance(iban) == 80000
    assert bank.check_balance(iban)


@pytest.mark.parametrize("moment,expected", [
    (datetime(2025, 3, 31, 22, 30, tzinfo=timezone.utc), "2025-04-01"),
    (datetime(2025, 1, 15, 23, 30, tzinfo=timezone.utc), "2025-01-16"),
])
def test_m4(bank, customer, moment, expected):
    """M4 Buchungstag und Valuta nach Berliner Zeit"""
    iban = bank.open_account(customer, "GIRO", opened_on="2025-01-01")
    booking_id = bank.post_booking(iban, 500, "CREDIT", at=moment)
    row = bank.db.execute("SELECT booking_date, value_date FROM bookings WHERE id = ?", (booking_id,)).fetchone()
    assert row[0] == expected
    assert row[1] == expected


@pytest.mark.parametrize("balance,cents", [(1500, 5), (3500, 11)])
def test_m5(bank, customer, balance, cents):
    """M5 Zinsen werden kaufmännisch gerundet"""
    iban = bank.open_account(customer, "TAGESGELD", opened_on="2025-01-01")
    bank.post_booking(iban, balance, "CREDIT", at=noon(2025, 1, 2), value_date="2025-01-02")
    assert bank.calculate_interest(iban, "2025-02-01", "2025-04-14") == cents


def test_m6():
    """M6 IBAN-Prüfung achtet auf die Länge"""
    from core.iban import build_de_iban, validate_iban

    valid = build_de_iban("01234500", 1000001)
    assert validate_iban(valid)
    assert not validate_iban(valid + "00")
    assert not validate_iban(valid + "12345")
    assert not validate_iban(_iban_check("DE", "012345000010"))
    assert validate_iban(_iban_check("FR", "0" * 23))
    assert validate_iban(_iban_check("AT", "0" * 16))


def test_m7(bank, customer):
    """M7 Monatsabschluss zählt den Monatsletzten mit"""
    iban = bank.open_account(customer, "TAGESGELD", opened_on="2025-01-01")
    bank.post_booking(iban, 7300000, "CREDIT", at=noon(2025, 2, 28), value_date="2025-02-28")
    bank.run_end_of_day("2025-03-31")
    assert bank.get_balance(iban) == 7300000 + 9300


def test_m8(bank, customer):
    """M8 Zinsen richten sich nach der Valuta"""
    iban = bank.open_account(customer, "TAGESGELD", opened_on="2025-01-01")
    bank.post_booking(iban, 7300000, "CREDIT", at=noon(2025, 3, 11), value_date="2025-03-01")
    assert bank.calculate_interest(iban, "2025-03-01", "2025-03-31") == 9300
