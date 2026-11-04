"""MB-202: Duplikate, parallele Anfragen und abgebrochene Verbindungen."""
import http.client
import json
import socket
import threading
import time

import pytest
import sqlite_sync

EXTERNAL_BLZ = "09876500"


@pytest.fixture
def api(db_path, bank, customer):
    from core.iban import build_de_iban
    from payments.api import PaymentsServer

    debtor = bank.open_account(customer, "GIRO", opened_on="2025-01-01")
    bank.post_booking(debtor, 100000, "CREDIT")
    with sqlite_sync.instrumented():
        server = PaymentsServer(("127.0.0.1", 0), db_path)
        thread = threading.Thread(target=server.serve_forever, daemon=True)
        thread.start()
        yield {
            "port": server.server_address[1],
            "debtor": debtor,
            "creditor": build_de_iban(EXTERNAL_BLZ, 555),
            "total": bank.total_balance(),
        }
        server.shutdown()
        server.server_close()


def _body(api, amount=25.0, purpose="Rechnung"):
    return {"debtor_iban": api["debtor"], "creditor_iban": api["creditor"], "creditor_name": "Fremdbank Kunde",
            "amount": amount, "purpose": purpose}


def _post(api, body, key):
    conn = http.client.HTTPConnection("127.0.0.1", api["port"], timeout=45)
    headers = {"Content-Type": "application/json"}
    if key is not None:
        headers["Idempotency-Key"] = key
    conn.request("POST", "/transfers", json.dumps(body), headers)
    response = conn.getresponse()
    payload = json.loads(response.read() or b"{}")
    conn.close()
    return response.status, payload


def _debits(bank, api):
    return len([row for row in bank.list_bookings(api["debtor"]) if row["amount_cents"] < 0])


def _assert_books_are_consistent(bank, api):
    from tools.reconcile import find_differences

    assert bank.total_balance() == api["total"]
    assert find_differences(bank) == []


def test_key_required(bank, api):
    """Ohne Idempotency-Key antwortet die API mit 400"""
    assert _post(api, _body(api), None)[0] == 400
    assert _debits(bank, api) == 0


def test_sequential_duplicate(bank, api):
    """Wiederholung mit gleichem Key bucht einmal und antwortet gleich"""
    first = _post(api, _body(api), "dup-1")
    second = _post(api, _body(api), "dup-1")
    assert first[0] == 201
    assert second == first
    assert _debits(bank, api) == 1
    assert bank.get_balance(api["debtor"]) == 100000 - 2500
    _assert_books_are_consistent(bank, api)


def test_different_body_same_key(bank, api):
    """Gleicher Key mit anderem Inhalt ergibt 422"""
    assert _post(api, _body(api), "dup-2")[0] == 201
    assert _post(api, _body(api, amount=30.0), "dup-2")[0] == 422
    assert _debits(bank, api) == 1


def test_parallel_same_key(bank, api):
    """Parallele Anfragen mit gleichem Key buchen einmal"""
    answers = []

    def worker():
        answers.append(_post(api, _body(api), "par-1"))

    threads = [threading.Thread(target=worker) for _ in range(2)]
    sqlite_sync.arm()
    for thread in threads:
        thread.start()
    for thread in threads:
        thread.join(60)
    sqlite_sync.disarm()
    assert len(answers) == 2
    assert answers[0][0] == 201
    assert answers[0] == answers[1]
    assert _debits(bank, api) == 1
    _assert_books_are_consistent(bank, api)


def _raw_request(api, body, key, cut=None):
    raw = json.dumps(body).encode("utf-8")
    head = ("POST /transfers HTTP/1.1\r\nHost: 127.0.0.1\r\nContent-Type: application/json\r\n"
            "Idempotency-Key: %s\r\nContent-Length: %d\r\n\r\n" % (key, len(raw))).encode("ascii")
    sock = socket.create_connection(("127.0.0.1", api["port"]), timeout=10)
    sock.sendall(head + (raw if cut is None else raw[:cut]))
    sock.close()


def test_abort_after_send(db_path, bank, api):
    """Abbruch nach dem Senden: Wiederholung liefert das erste Ergebnis"""
    _raw_request(api, _body(api), "abort-1")
    deadline = time.time() + 10
    while _debits(bank, api) == 0 and time.time() < deadline:
        time.sleep(0.05)
    assert _debits(bank, api) == 1
    status, payload = _post(api, _body(api), "abort-1")
    assert status == 201
    assert payload["amount_cents"] == 2500
    assert _debits(bank, api) == 1
    _assert_books_are_consistent(bank, api)


def test_abort_mid_body(bank, api):
    """Abbruch mitten im Body bucht nichts"""
    _raw_request(api, _body(api), "abort-2", cut=20)
    time.sleep(0.3)
    assert _debits(bank, api) == 0
    assert _post(api, _body(api), "abort-2")[0] == 201
    assert _debits(bank, api) == 1


def test_rejection_is_remembered(bank, api):
    """Auch eine Ablehnung gilt für den Key"""
    too_much = _body(api, amount=999999.0)
    assert _post(api, too_much, "reject-1")[0] == 409
    bank.post_booking(api["debtor"], 200000000, "CREDIT")
    assert _post(api, too_much, "reject-1")[0] == 409
    assert _debits(bank, api) == 0


def test_rejection_leaves_no_transfer(bank, api):
    """Abgelehnte Überweisungen hinterlassen keine Buchung"""
    assert _post(api, _body(api, amount=999999.0), "reject-2")[0] == 409
    assert _debits(bank, api) == 0
    assert bank.get_balance(api["debtor"]) == 100000
