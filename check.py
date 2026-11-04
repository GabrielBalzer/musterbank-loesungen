#!/usr/bin/env python3
"""Selbstcheck für das Musterbank-Repo.

    python3 check.py ../musterbank            alle Bereiche
    python3 check.py ../musterbank bugs       nur einen: bugs, idempotenz, a11y, reviews
    python3 check.py ../musterbank bugs -v    mit Fehlermeldungen
"""
import argparse
import os
import subprocess
import sys

HERE = os.path.dirname(os.path.abspath(__file__))
CHECKS = os.path.join(HERE, "checks")
AREAS = ["bugs", "idempotenz", "a11y", "reviews"]


def tool_environment(repo):
    """Interpreter and PYTHONPATH with the test tools of the checked repo."""
    env = dict(os.environ)
    env["MUSTERBANK_REPO"] = repo
    venv_python = os.path.join(repo, ".venv", "bin", "python")
    deps = os.path.join(repo, ".deps")
    if not os.path.exists(venv_python) and not os.path.isdir(deps):
        subprocess.run([sys.executable, os.path.join(repo, "run.py"), "setup"], check=True)
    if os.path.exists(venv_python):
        env["PYTHONPATH"] = repo
        return venv_python, env
    env["PYTHONPATH"] = os.pathsep.join([repo, deps])
    return sys.executable, env


def main():
    parser = argparse.ArgumentParser(description="Selbstcheck für das Musterbank-Repo")
    parser.add_argument("repo", help="Pfad zum Musterbank-Repo")
    parser.add_argument("area", nargs="?", choices=AREAS + ["all"], default="all")
    parser.add_argument("-v", "--verbose", action="store_true", help="Fehlermeldungen anzeigen")
    args = parser.parse_args()

    repo = os.path.abspath(args.repo)
    if not os.path.exists(os.path.join(repo, "core", "bank.py")):
        sys.exit("Das sieht nicht nach dem Musterbank-Repo aus: %s" % repo)
    python, env = tool_environment(repo)
    areas = AREAS if args.area == "all" else [args.area]
    files = [os.path.join(CHECKS, "test_%s.py" % area) for area in areas]
    command = [python, "-m", "pytest", "-c", os.path.join(CHECKS, "pytest.ini"), "--rootdir", CHECKS,
               "-p", "no:cacheprovider", "--tb=short" if args.verbose else "--tb=no"] + files
    sys.exit(subprocess.call(command, cwd=CHECKS, env=env))


if __name__ == "__main__":
    main()
