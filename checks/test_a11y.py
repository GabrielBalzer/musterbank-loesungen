"""MB-205: statische Prüfung der gerenderten Seiten und des Stylesheets."""
import http.cookiejar
import os
import socket
import subprocess
import sys
import time
import urllib.error
import urllib.request
from urllib.parse import urlencode

import a11y_scan
import pytest
from conftest import REPO, noon


def _free_port():
    with socket.socket() as sock:
        sock.bind(("127.0.0.1", 0))
        return sock.getsockname()[1]


@pytest.fixture(scope="module")
def site(tmp_path_factory):
    from core.bank import BankCore
    from core.mailbox import Mailbox

    db = str(tmp_path_factory.mktemp("a11y") / "site.sqlite")
    bank = BankCore(db)
    customer = bank.createCustomer("Ida", "Probe", street="Testring 1", zip_code="00100", city="Musterstadt",
                                   email="ida@example.org")
    giro = bank.open_account(customer, "GIRO", opened_on="2025-01-01")
    savings = bank.open_account(customer, "TAGESGELD", opened_on="2025-01-01")
    bank.post_booking(giro, 100000, "CREDIT", at=noon(2025, 3, 3), purpose="Eingang", counterparty_name="Testfirma")
    bank.post_booking(savings, 5000, "CREDIT", at=noon(2025, 3, 3), purpose="Sparen")
    message = Mailbox(bank).deliver(customer, "Willkommen", "Guten Tag")
    number = bank.getCustomer(customer)["customer_no"]
    bank.close()

    port = _free_port()
    env = dict(os.environ)
    process = subprocess.Popen([sys.executable, "-m", "web", "--db", db, "--port", str(port),
                                "--payments-url", "http://127.0.0.1:9"], cwd=REPO, env=env,
                               stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
    base = "http://127.0.0.1:%d" % port
    opener = urllib.request.build_opener(urllib.request.HTTPCookieProcessor(http.cookiejar.CookieJar()))
    deadline = time.time() + 20
    pages = {}
    try:
        while True:
            try:
                pages["/login"] = opener.open(base + "/login", timeout=5).read().decode("utf-8")
                break
            except (urllib.error.URLError, OSError):
                if time.time() > deadline:
                    raise
                time.sleep(0.1)
        opener.open(base + "/login", data=urlencode({"customer_no": number, "pin": "1234"}).encode(), timeout=5).read()
        for path in ("/", "/accounts/%s" % giro, "/statements/%s?month=2025-03" % giro, "/transfer", "/move",
                     "/mailbox", "/mailbox/%d" % message, "/profile"):
            pages[path] = opener.open(base + path, timeout=5).read().decode("utf-8")
        css = opener.open(base + "/static/style.css", timeout=5).read().decode("utf-8")
    finally:
        process.terminate()
        process.wait(10)
    return {"pages": pages, "scans": {path: a11y_scan.scan(html) for path, html in pages.items()}, "css": css}


def test_a1(site):
    """A1 Sprache der Seite ist ausgezeichnet"""
    assert all(scan.html_lang == "de" for scan in site["scans"].values())


def test_a2(site):
    """A2 Alle Formularfelder haben ein Label"""
    missing = {path: scan.unlabelled_fields() for path, scan in site["scans"].items() if scan.unlabelled_fields()}
    assert not missing


def test_a3(site):
    """A3 Datentabellen haben Kopfzellen"""
    bad = [path for path, scan in site["scans"].items() if not all(scan.tables)]
    assert not bad
    assert any(scan.tables for scan in site["scans"].values())


def test_a4(site):
    """A4 Text hat mindestens 4,5:1 Kontrast"""
    assert a11y_scan.low_contrast(site["css"]) == []


def test_a5(site):
    """A5 Alles ist per Tastatur bedienbar"""
    mouse = {path: scan.mouse_only for path, scan in site["scans"].items() if scan.mouse_only}
    no_submit = {path: scan.forms_without_submit for path, scan in site["scans"].items() if scan.forms_without_submit}
    assert not mouse
    assert not no_submit


def test_a6(site):
    """A6 Der Fokus ist sichtbar"""
    assert not a11y_scan.focus_removed(site["css"])


def test_a7(site):
    """A7 Bilder haben einen Alternativtext"""
    assert all(scan.images_without_alt == 0 for scan in site["scans"].values())


def test_a8(site):
    """A8 Jede Seite hat einen eigenen Titel und eine Hauptüberschrift"""
    titles = [scan.title.strip() for scan in site["scans"].values()]
    assert len(set(titles)) >= 7
    assert all(scan.h1_count == 1 for scan in site["scans"].values())
