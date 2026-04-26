"""
Login / credential helpers.
Credentials are stored in credentials.txt as  username:password  lines.
"""

from pathlib import Path

CRED_FILE = Path("credentials.txt")


def _init_credentials() -> None:
    if not CRED_FILE.exists():
        CRED_FILE.write_text("admin:admin\n", encoding="utf-8")


def load_credentials() -> dict[str, str]:
    _init_credentials()
    creds: dict[str, str] = {}
    for line in CRED_FILE.read_text(encoding="utf-8").splitlines():
        if ":" in line:
            u, pw = line.split(":", 1)
            creds[u.strip()] = pw.strip()
    return creds


def verify(username: str, password: str) -> bool:
    return load_credentials().get(username.strip()) == password.strip()
