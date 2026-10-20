"""Validate the entire publishable tree, manifest and fresh commit identity.

Reports categories and file paths only, never matched values. This is an explicit
release boundary check, not a general guarantee that arbitrary data is safe.
"""
from pathlib import Path
import argparse
import hashlib
import json
import re
import subprocess
from urllib.parse import urlsplit, parse_qs

ROOT = Path(__file__).resolve().parents[1]
NAME = "Research Archive Maintainers"
EMAIL = "293658048+attm-agenticcoding@users.noreply.github.com"
ALLOWED = {
    ".gitignore", "README.md", "RIGHTS.md", "PUBLIC_MANIFEST.json",
    "data/crypto-calls.json", "data/momentum-metrics.json", "data/sources.json",
    "docs/METHODOLOGY.md", "docs/PUBLIC_SCOPE.md", "docs/PUBLIC_REVIEW.md",
    "reports/SNAPSHOT.md", "research/__init__.py", "research/scenarios.py",
    "research/tax.py", "research/fetch_prices.py", "research/fetch_kraken_prices.py",
    "scripts/check_public.py", "scripts/summarize.py",
    "tests/test_methods.py", "tests/test_snapshot.py", "tests/test_fetch_prices.py",
    "tests/test_public_policy.py",
}
PATTERNS = {
    "local_identity_path": re.compile(rb"(?:/(?:Users|home)/[A-Za-z0-9_.-]+|[A-Z]:\\Users\\[A-Za-z0-9_.-]+)"),
    "internal_resource_identifier": re.compile(rb"(?:appgprj_|appgver_|Automation_|libfile_|file_000000|g-p-)[A-Za-z0-9_-]{12,}"),
    "credential_candidate": re.compile(rb"(?:gh[pousr]_[A-Za-z0-9]{20,}|github_pat_[A-Za-z0-9_]{20,}|sk-(?:proj-)?[A-Za-z0-9_-]{30,}|eyJ[A-Za-z0-9_-]{15,}\.[A-Za-z0-9_-]{15,}\.[A-Za-z0-9_-]{15,}|-----BEGIN (?:RSA |EC |OPENSSH )?PRIVATE KEY-----)"),
    "private_notification_endpoint": re.compile(rb"(?:ntfy\.sh|api\.telegram\.org|hooks\.slack\.com|api\.pushover\.net)/[^\s\"<>]+"),
    "conversation_identifier": re.compile(rb'"(?:chatgpt_id|execution_thread|source_session|library_file_id)"\s*:'),
}
EMAIL_RE = re.compile(rb"[A-Za-z0-9._%+-]+@[A-Za-z0-9.-]+\.[A-Za-z]{2,}")
UUID_RE = re.compile(rb"\b[0-9a-f]{8}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{12}\b", re.I)


def scan_bytes(raw):
    if b"\0" in raw:
        raise ValueError("binary_content")
    raw.decode("utf-8")
    for category, pattern in PATTERNS.items():
        if pattern.search(raw):
            raise ValueError(category)
    if UUID_RE.search(raw):
        raise ValueError("opaque_identifier")
    for match in EMAIL_RE.finditer(raw):
        if match.group().decode() != EMAIL:
            raise ValueError("non_release_email")


def validate_url(value):
    parsed = urlsplit(value)
    if parsed.scheme != "https" or not parsed.netloc or parsed.username or parsed.password:
        raise ValueError("unsafe_source_url")
    if any(key.lower() in {"token", "signature", "key", "auth", "authorization", "access_token"}
           or key.lower().startswith("x-amz-") for key in parse_qs(parsed.query)):
        raise ValueError("signed_or_secret_query")


def publishable_files(root=ROOT):
    if (root / ".git").is_dir():
        # Generated downloads and caches are ignored, never admitted to release.
        raw = subprocess.check_output(["git", "-C", str(root), "ls-files", "-z", "--cached", "--others", "--exclude-standard"])
        return sorted(set(p.decode() for p in raw.split(b"\0") if p))
    return sorted(str(p.relative_to(root)) for p in root.rglob("*")
                  if p.is_file() and "__pycache__" not in p.parts and ".git" not in p.parts)


def check_metadata(root=ROOT):
    if not (root / ".git").is_dir():
        return "not_initialized"
    rows = subprocess.check_output(["git", "-C", str(root), "log", "--all", "--format=%an%x09%ae%x09%cn%x09%ce%x09%P"]).decode().splitlines()
    if len(rows) != 1:
        raise ValueError("release_must_have_one_fresh_root_commit")
    fields = rows[0].split("\t")
    if fields != [NAME, EMAIL, NAME, EMAIL, ""]:
        raise ValueError("unexpected_commit_identity_or_parent_history")
    return "one_fresh_root_commit_verified"


def check(write_manifest=False):
    files = publishable_files()
    missing = ALLOWED - set(files) - ({"PUBLIC_MANIFEST.json"} if write_manifest else set())
    extra = set(files) - ALLOWED
    if extra or missing:
        raise ValueError(f"file_allowlist_mismatch extra={sorted(extra)} missing={sorted(missing)}")
    records = []
    for relative in files:
        if relative == "PUBLIC_MANIFEST.json":
            continue
        raw = (ROOT / relative).read_bytes()
        if len(raw) > 2_000_000:
            raise ValueError(f"unexpected_large_payload: {relative}")
        try:
            scan_bytes(raw)
        except (ValueError, UnicodeError) as error:
            raise ValueError(f"{error}: {relative}") from None
        records.append({"path": relative, "bytes": len(raw), "sha256": hashlib.sha256(raw).hexdigest()})
    manifest = ROOT / "PUBLIC_MANIFEST.json"
    if write_manifest:
        manifest.write_text(json.dumps(records, indent=2) + "\n")
    if json.loads(manifest.read_text()) != records:
        raise ValueError("manifest_mismatch")
    # The self-describing manifest is scanned too; it cannot include its own hash.
    scan_bytes(manifest.read_bytes())
    metadata = check_metadata()
    return {"status": "passed", "public_files": len(records) + 1, "bytes_excluding_manifest": sum(r["bytes"] for r in records), "metadata": metadata}


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--write-manifest", action="store_true")
    args = parser.parse_args()
    print(json.dumps(check(args.write_manifest)))
