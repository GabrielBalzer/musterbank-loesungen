"""Shared fixtures and the result table of the self check."""
import os
import sys
from collections import OrderedDict
from datetime import datetime, timezone

import pytest

REPO = os.environ.get("MUSTERBANK_REPO", "")
if REPO and REPO not in sys.path:
    sys.path.insert(0, REPO)

_results = OrderedDict()


def noon(year, month, day):
    return datetime(year, month, day, 12, 0, tzinfo=timezone.utc)


@pytest.fixture
def db_path(tmp_path):
    return str(tmp_path / "check.sqlite")


@pytest.fixture
def bank(db_path):
    from core.bank import BankCore

    instance = BankCore(db_path)
    yield instance
    instance.close()


@pytest.fixture
def customer(bank):
    return bank.createCustomer("Ida", "Probe")


@pytest.hookimpl(hookwrapper=True)
def pytest_runtest_makereport(item, call):
    outcome = yield
    report = outcome.get_result()
    if report.when == "setup" and not report.passed or report.when == "call":
        doc = (item.function.__doc__ or item.function.__name__).strip().splitlines()[0]
        area = os.path.basename(str(item.fspath))[5:-3]
        key = (area, item.function.__name__, doc)
        _results[key] = _results.get(key, True) and report.passed


def pytest_terminal_summary(terminalreporter):
    area_seen = None
    for (area, _name, doc), passed in _results.items():
        if area != area_seen:
            terminalreporter.write_line("")
            terminalreporter.write_line(area)
            area_seen = area
        terminalreporter.write_line("  %-58s %s" % (doc, "OK" if passed else "FEHLT"))
    total = len(_results)
    done = sum(1 for passed in _results.values() if passed)
    terminalreporter.write_line("")
    terminalreporter.write_line("%d von %d Prüfungen bestanden" % (done, total))
