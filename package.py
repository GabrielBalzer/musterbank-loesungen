#!/usr/bin/env python3
"""Build dist/musterbank-teams.zip, dist/musterbank-loesungen.zip and dist/SHA256SUMS.

Runs on the development machine only. Aborts on anything that is not on the allow list,
and on traces of the machine or hints at the solutions in the participant repo.
"""
import getpass
import hashlib
import os
import re
import shutil
import socket
import subprocess
import sys
import tempfile
import zipfile

HERE = os.path.dirname(os.path.abspath(__file__))
ROOT = os.path.dirname(HERE)
REPO = os.path.join(ROOT, "musterbank")
DIST = os.path.join(ROOT, "dist")
FIXED_DATE = (2026, 1, 1, 0, 0, 0)

TEAM_TOP = {"run.py", "README.md", "CHALLENGES.md", "THIRD_PARTY.md", "requirements-dev.txt", "pytest.ini", ".gitignore",
            "core", "payments", "statements", "web", "tools", "tests", "tickets", "reviews", "docs", "vendor"}
TEAM_GENERATED = {"data", ".venv", ".deps", ".coverage", ".pytest_cache", "__pycache__", ".DS_Store"}
SOLUTION_TOP = {"PLAN.md", "LOESUNG.md", "BERICHT.md", "check.py", "package.py", "checks", "patches"}
SKIP = {"__pycache__", ".pytest_cache", ".DS_Store"}
FORBIDDEN_NAMES = {"CLAUDE.md", "AGENTS.md", ".claude", ".env"}
FORBIDDEN_SUFFIXES = (".sqlite", ".sqlite-wal", ".sqlite-shm", ".db", ".log", ".pem", ".pyc")
TEAM_HINTS = re.compile(
    r"\bjury\b|l(oe|ö)sung|musterbank-loesungen|hidden.?test|\bbugs?\b|bugfix|absichtlich|eingebaut|defekt|defect"
    r"|golden.?master|\bTODO\b|\bFIXME\b|\bHACK\b|selbstcheck|check\.py",
    re.I,
)
GIT_ENV = {
    "GIT_AUTHOR_NAME": "Musterbank AG",
    "GIT_AUTHOR_EMAIL": "it@example.org",
    "GIT_AUTHOR_DATE": "2026-01-01T00:00:00+00:00",
    "GIT_COMMITTER_NAME": "Musterbank AG",
    "GIT_COMMITTER_EMAIL": "it@example.org",
    "GIT_COMMITTER_DATE": "2026-01-01T00:00:00+00:00",
    "GIT_CONFIG_GLOBAL": os.devnull,
    "GIT_CONFIG_NOSYSTEM": "1",
}


def fail(message):
    sys.exit("package: " + message)


def machine_traces():
    values = {getpass.getuser(), socket.gethostname(), os.path.expanduser("~"), ROOT}
    for key in ("user.name", "user.email"):
        found = subprocess.run(["git", "config", key], cwd=ROOT, capture_output=True, text=True).stdout.strip()
        if found:
            values.add(found)
    patterns = [re.escape(v) for v in values if v]
    # split so this line does not match itself
    patterns += ["/" + "Users/", "/" + r"home/\w", "/private" + "/tmp", "[A-Z]:" + r"\\Users"]
    return re.compile("|".join(patterns), re.I)


def is_text(path):
    with open(path, "rb") as fh:
        return b"\0" not in fh.read(4096)


def walk(top):
    for folder, dirs, files in os.walk(top):
        dirs[:] = sorted(d for d in dirs if d not in SKIP)
        for name in sorted(files):
            if name not in SKIP:
                yield os.path.join(folder, name)


def check_tree(tree, traces, hints=None):
    for path in walk(tree):
        relative = os.path.relpath(path, tree)
        parts = relative.split(os.sep)
        if parts[0] == ".git":
            continue
        if FORBIDDEN_NAMES & set(parts) or path.endswith(FORBIDDEN_SUFFIXES):
            fail("verbotene Datei: %s" % relative)
        if path.endswith(".whl"):
            if not path.endswith("-py3-none-any.whl"):
                fail("kein reines Wheel: %s" % relative)
            continue
        if not is_text(path):
            fail("unerwartete Binärdatei: %s" % relative)
        with open(path, encoding="utf-8") as fh:
            for number, line in enumerate(fh, 1):
                if traces.search(line):
                    fail("Spur des Entwicklungsrechners: %s:%d" % (relative, number))
                if hints and hints.search(line):
                    fail("verräterischer Text: %s:%d: %s" % (relative, number, line.strip()))


def copy_allowed(source, target, allowed, generated=frozenset()):
    for name in sorted(os.listdir(source)):
        if name in generated:
            continue
        if name not in allowed:
            fail("nicht auf der Positivliste: %s" % os.path.join(os.path.basename(source), name))
        path = os.path.join(source, name)
        if os.path.isdir(path):
            shutil.copytree(path, os.path.join(target, name), ignore=shutil.ignore_patterns(*SKIP))
        else:
            shutil.copy(path, os.path.join(target, name))
    missing = allowed - set(os.listdir(target))
    if missing:
        fail("fehlt: %s" % ", ".join(sorted(missing)))


def wheel_metadata(path):
    with zipfile.ZipFile(path) as archive:
        name = next(n for n in archive.namelist() if n.endswith(".dist-info/METADATA"))
        text = archive.read(name).decode("utf-8")
    head = text.split("\n\n", 1)[0]
    fields = {}
    classifiers = []
    for line in head.splitlines():
        key, _, value = line.partition(": ")
        if key == "Classifier" and value.startswith("License ::"):
            classifiers.append(value.split("::")[-1].strip())
        elif key in ("Name", "Version", "License-Expression", "License") and key not in fields:
            fields[key] = value.strip()
    license_name = fields.get("License-Expression") or (classifiers[0] if classifiers else fields.get("License", "siehe Paket"))
    return fields["Name"], fields["Version"], license_name


def third_party_text():
    lines = ["# Eingebettete Pakete", "",
             "Diese Pakete liegen als reine Wheels in `vendor/` und werden nur für die Tests gebraucht. Die Bank selbst nutzt ausschließlich die Standardbibliothek.",
             "", "| Paket | Version | Lizenz |", "|---|---|---|"]
    for name in sorted(os.listdir(os.path.join(REPO, "vendor")), key=str.lower):
        if name.endswith(".whl"):
            package, version, license_name = wheel_metadata(os.path.join(REPO, "vendor", name))
            lines.append("| %s | %s | %s |" % (package, version, license_name))
    return "\n".join(lines) + "\n"


def init_git(tree):
    env = dict(os.environ, **GIT_ENV)

    def git(*args):
        subprocess.run(["git"] + list(args), cwd=tree, env=env, check=True, capture_output=True)

    for path in walk(tree):
        os.chmod(path, 0o644)
    git("init", "-q", "--template=", "-b", "main", ".")
    git("add", "-A")
    git("commit", "-q", "-m", "Initial commit")
    for key in ("core.ignorecase", "core.precomposeunicode"):
        subprocess.run(["git", "config", "--unset", key], cwd=tree, env=env, capture_output=True)
    git("gc", "-q", "--prune=now")
    # the index stores stat data of this machine, a fresh one has none
    os.remove(os.path.join(tree, ".git", "index"))
    git("read-tree", "HEAD")
    for name in ("COMMIT_EDITMSG", "ORIG_HEAD"):
        target = os.path.join(tree, ".git", name)
        if os.path.exists(target):
            os.remove(target)
    count = subprocess.run(["git", "rev-list", "--count", "--all"], cwd=tree, env=env, capture_output=True, text=True, check=True)
    if count.stdout.strip() != "1":
        fail(".git enthält %s Commits statt genau einem" % count.stdout.strip())


def write_zip(tree, prefix, target):
    with zipfile.ZipFile(target, "w", zipfile.ZIP_DEFLATED, compresslevel=9) as archive:
        for folder, dirs, files in os.walk(tree):
            dirs.sort()
            relative_folder = os.path.relpath(folder, tree)
            if not files and not dirs:
                # git needs its empty folders such as refs/heads
                info = zipfile.ZipInfo(os.path.join(prefix, relative_folder).replace(os.sep, "/") + "/", FIXED_DATE)
                info.external_attr = (0o755 << 16) | 0x10
                archive.writestr(info, b"")
            for name in sorted(files):
                relative = os.path.normpath(os.path.join(relative_folder, name))
                info = zipfile.ZipInfo(os.path.join(prefix, relative).replace(os.sep, "/"), FIXED_DATE)
                info.external_attr = 0o644 << 16
                info.compress_type = zipfile.ZIP_DEFLATED
                with open(os.path.join(folder, name), "rb") as fh:
                    archive.writestr(info, fh.read())


def check_zip(path, prefix, allowed):
    with zipfile.ZipFile(path) as archive:
        names = archive.namelist()
    tops = {n.split("/")[1] for n in names}
    if not all(n.startswith(prefix + "/") for n in names):
        fail("%s enthält Dateien außerhalb von %s/" % (path, prefix))
    extra = tops - allowed - {".git"}
    if extra:
        fail("%s enthält: %s" % (path, ", ".join(sorted(extra))))
    return len(names)


def main():
    traces = machine_traces()
    with open(os.path.join(REPO, "THIRD_PARTY.md"), "w", encoding="utf-8") as fh:
        fh.write(third_party_text())
    shutil.rmtree(DIST, ignore_errors=True)
    os.makedirs(DIST)
    with tempfile.TemporaryDirectory() as work:
        team = os.path.join(work, "team")
        os.makedirs(team)
        copy_allowed(REPO, team, TEAM_TOP, TEAM_GENERATED)
        check_tree(team, traces, TEAM_HINTS)
        init_git(team)
        team_zip = os.path.join(DIST, "musterbank-teams.zip")
        write_zip(team, "musterbank", team_zip)
        team_count = check_zip(team_zip, "musterbank", TEAM_TOP)

        solutions = os.path.join(work, "solutions")
        os.makedirs(solutions)
        copy_allowed(HERE, solutions, SOLUTION_TOP)
        check_tree(solutions, traces)
        solutions_zip = os.path.join(DIST, "musterbank-loesungen.zip")
        write_zip(solutions, "musterbank-loesungen", solutions_zip)
        solution_count = check_zip(solutions_zip, "musterbank-loesungen", SOLUTION_TOP)

    with open(os.path.join(DIST, "SHA256SUMS"), "w", encoding="ascii") as fh:
        for path in (team_zip, solutions_zip):
            with open(path, "rb") as zipped:
                fh.write("%s  %s\n" % (hashlib.sha256(zipped.read()).hexdigest(), os.path.basename(path)))
    print("musterbank-teams.zip: %d Dateien, %.1f MB" % (team_count, os.path.getsize(team_zip) / 1e6))
    print("musterbank-loesungen.zip: %d Dateien, %.1f MB" % (solution_count, os.path.getsize(solutions_zip) / 1e6))


if __name__ == "__main__":
    main()
