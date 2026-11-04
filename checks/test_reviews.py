"""MB-206: reviews/verdicts.json gegen den Antwortschlüssel."""
import json
import os

import pytest
from conftest import REPO

KEY_FILE = os.path.join(os.path.dirname(os.path.abspath(__file__)), "reviews_key.json")


@pytest.fixture(scope="module")
def verdicts():
    path = os.path.join(REPO, "reviews", "verdicts.json")
    if not os.path.exists(path):
        pytest.fail("reviews/verdicts.json fehlt")
    with open(path, encoding="utf-8") as fh:
        return {entry["pr"]: entry for entry in json.load(fh)}


@pytest.fixture(scope="module")
def key():
    with open(KEY_FILE, encoding="utf-8") as fh:
        return json.load(fh)


def _rule_correct(key, verdicts, rule):
    wrong = []
    for pr, expected in key.items():
        if rule not in expected["rules"]:
            continue
        got = verdicts.get(pr, {})
        if got.get("verdict") != "reject" or rule not in got.get("rules", []):
            wrong.append(pr)
    return wrong


def test_r1(key, verdicts):
    """R1 Float für Geld erkannt"""
    assert _rule_correct(key, verdicts, "R1") == []


def test_r2(key, verdicts):
    """R2 Fehlender Idempotency-Key erkannt"""
    assert _rule_correct(key, verdicts, "R2") == []


def test_r3(key, verdicts):
    """R3 Personenbezogene Daten im Log erkannt"""
    assert _rule_correct(key, verdicts, "R3") == []


def test_r4(key, verdicts):
    """R4 SQL per Verkettung erkannt"""
    assert _rule_correct(key, verdicts, "R4") == []


def test_clean(key, verdicts):
    """Saubere Pull Requests nicht abgelehnt"""
    wrong = [pr for pr, expected in key.items()
             if expected["verdict"] == "approve" and verdicts.get(pr, {}).get("verdict") != "approve"]
    assert wrong == []
