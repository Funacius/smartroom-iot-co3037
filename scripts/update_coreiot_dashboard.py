"""Update the existing CoreIOT dashboard in place; no new dashboard is created.

Login is entered privately in the terminal. --remember-session stores only the
session tokens, encrypted by Windows DPAPI for the current Windows account.
Future authorized updates can use --non-interactive while that session is valid.
"""

import argparse
import ctypes
import datetime
import getpass
import json
import os
from pathlib import Path
import sys
import urllib.error
import urllib.request
import uuid

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
from coreiot.dashboard_patch import DEFAULT_DASHBOARD_URL, entity_id, patch_fan_switch  # noqa: E402

HOST = "https://app.coreiot.io"
CACHE = ROOT / "runtime/coreiot-user-session.dpapi"


class APIError(RuntimeError):
    def __init__(self, status, path):
        self.status = status
        super().__init__(f"CoreIOT HTTP {status}: {path}. No credentials were logged.")


class NoRedirect(urllib.request.HTTPRedirectHandler):
    def redirect_request(self, req, fp, code, msg, headers, newurl):
        raise RuntimeError("Unexpected redirect from CoreIOT; refusing to forward credentials")


def request(path, token=None, data=None):
    if not path.startswith("/api/"):
        raise ValueError("Only CoreIOT API paths are allowed")
    headers = {"Accept": "application/json"}
    if token:
        headers["X-Authorization"] = "Bearer " + token
    if data is not None:
        headers["Content-Type"] = "application/json"
    req = urllib.request.Request(
        HOST + path,
        data=None if data is None else json.dumps(data).encode("utf-8"),
        headers=headers,
    )
    try:
        with urllib.request.build_opener(NoRedirect()).open(req, timeout=20) as response:
            return json.load(response)
    except urllib.error.HTTPError as exc:
        raise APIError(exc.code, path) from None
    except urllib.error.URLError:
        raise RuntimeError("Cannot reach CoreIOT; check the network. No credentials were logged.") from None


def dpapi(data, decrypt=False):
    if os.name != "nt":
        raise RuntimeError("Remembered sessions require Windows DPAPI; omit --remember-session")

    class Blob(ctypes.Structure):
        _fields_ = [("size", ctypes.c_ulong), ("data", ctypes.POINTER(ctypes.c_ubyte))]

    buffer = ctypes.create_string_buffer(data)
    source = Blob(len(data), ctypes.cast(buffer, ctypes.POINTER(ctypes.c_ubyte)))
    output = Blob()
    crypt = ctypes.WinDLL("crypt32", use_last_error=True)
    kernel = ctypes.WinDLL("kernel32", use_last_error=True)
    kernel.LocalFree.argtypes = [ctypes.c_void_p]
    kernel.LocalFree.restype = ctypes.c_void_p
    function = crypt.CryptUnprotectData if decrypt else crypt.CryptProtectData
    function.argtypes = [
        ctypes.POINTER(Blob),
        ctypes.c_void_p,
        ctypes.c_void_p,
        ctypes.c_void_p,
        ctypes.c_void_p,
        ctypes.c_ulong,
        ctypes.POINTER(Blob),
    ]
    function.restype = ctypes.c_int
    if not function(ctypes.byref(source), None, None, None, None, 1, ctypes.byref(output)):
        raise RuntimeError("Windows could not unlock/save this session for the current Windows account")
    try:
        return ctypes.string_at(output.data, output.size)
    finally:
        kernel.LocalFree(output.data)


def save_session(session):
    CACHE.parent.mkdir(parents=True, exist_ok=True)
    encrypted = dpapi(json.dumps({"host": HOST, **session}).encode())
    temporary = CACHE.with_suffix(".dpapi.tmp")
    temporary.write_bytes(encrypted)
    temporary.replace(CACHE)


def authenticate(non_interactive=False, remember=False, user_jwt=False):
    if CACHE.exists() and not user_jwt:
        try:
            stored = json.loads(dpapi(CACHE.read_bytes(), decrypt=True))
            if stored.get("host") != HOST:
                raise ValueError("Session host mismatch")
            try:
                request("/api/auth/user", stored["token"])
                return stored["token"]
            except APIError as exc:
                if exc.status != 401:
                    raise
            if stored.get("refreshToken"):
                renewed = request("/api/auth/token", data={"refreshToken": stored["refreshToken"]})
                request("/api/auth/user", renewed["token"])
                save_session(renewed)
                return renewed["token"]
        except (APIError, RuntimeError, ValueError, KeyError):
            if non_interactive:
                raise RuntimeError(
                    "Saved session unavailable/expired; run this command in your terminal to log in again"
                ) from None
            print("Saved session unavailable; please log in again.")
    if non_interactive:
        raise RuntimeError("No usable saved session. Run locally with --apply --remember-session first.")
    if user_jwt:
        session = {
            "token": getpass.getpass("CoreIOT USER JWT (hidden; not the gateway device token): ").strip()
        }
    else:
        username = input("CoreIOT account email: ").strip()
        password = getpass.getpass("CoreIOT account password (hidden, not stored): ")
        if not username or not password:
            raise RuntimeError("No login supplied; dashboard was not changed")
        session = request("/api/auth/login", data={"username": username, "password": password})
        del password
    if not session.get("token"):
        raise RuntimeError(
            "Login needs another authentication step. Use --jwt with your current user JWT locally."
        )
    request("/api/auth/user", session["token"])
    if remember:
        save_session({k: session[k] for k in ("token", "refreshToken") if k in session})
        print("Session encrypted for your Windows account. Account password was not stored.")
    return session["token"]


def dashboard_id(url):
    from urllib.parse import urlparse

    parsed = urlparse(url)
    if (
        parsed.scheme != "https"
        or parsed.netloc != "app.coreiot.io"
        or not parsed.path.startswith("/dashboards/")
    ):
        raise ValueError("Use the HTTPS dashboard URL on app.coreiot.io")
    return str(uuid.UUID(parsed.path.rstrip("/").split("/")[-1]))


def update_dashboard(token, target_id, apply=False):
    path = "/api/dashboard/" + target_id
    original = request(path, token)
    patched, plan = patch_fan_switch(original, target_id)
    print(json.dumps(plan, ensure_ascii=True, indent=2))
    if not plan["changed"]:
        print("Switch is already configured; dashboard ID and existing widgets are unchanged.")
        return plan
    directory = ROOT / "runtime/coreiot-backups"
    directory.mkdir(parents=True, exist_ok=True)
    stamp = datetime.datetime.now().strftime("%Y%m%d-%H%M%S-%f")
    backup = directory / f"{target_id}-{stamp}.before.json"
    backup.write_text(json.dumps(original, ensure_ascii=False, indent=2), encoding="utf-8")
    preview = directory / f"{target_id}-{stamp}.preview.json"
    preview.write_text(json.dumps(patched, ensure_ascii=False, indent=2), encoding="utf-8")
    print("Backup:", backup.relative_to(ROOT))
    if not apply:
        print("Preview only. Run with --apply to update this same dashboard.")
        return plan
    # Detect a dashboard saved by someone else while preparing this patch.
    if request(path, token) != original:
        raise RuntimeError("Dashboard changed during preparation; rerun to patch the latest version")
    if entity_id(patched.get("id")) != target_id:
        raise RuntimeError("Missing/mismatched existing dashboard ID; save was stopped")
    saved = request("/api/dashboard", token, patched)
    if entity_id(saved.get("id")) != target_id:
        raise RuntimeError("Unexpected save response; inspect the saved dashboard and local backup")
    verified = request(path, token)
    _, verification = patch_fan_switch(verified, target_id)
    if verification["changed"]:
        raise RuntimeError("Server did not retain the requested switch configuration; backup is available")
    plan.update(
        saved=True,
        verified=True,
        backup=str(backup.relative_to(ROOT)),
        dashboard_url=HOST + "/dashboards/all/" + target_id,
        verified_at=datetime.datetime.now(datetime.timezone.utc).isoformat(),
    )
    (ROOT / "evidence").mkdir(exist_ok=True)
    (ROOT / "evidence/coreiot_switch_update.json").write_text(json.dumps(plan, indent=2), encoding="utf-8")
    print("Updated the SAME dashboard. Refresh its browser tab; no import is needed.")
    return plan


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--url", default=DEFAULT_DASHBOARD_URL)
    parser.add_argument("--apply", action="store_true")
    parser.add_argument("--remember-session", action="store_true")
    parser.add_argument(
        "--non-interactive", action="store_true", help="Use only an existing encrypted session"
    )
    parser.add_argument(
        "--jwt", action="store_true", help="Enter a current USER JWT privately instead of account login"
    )
    parser.add_argument(
        "--forget-session", action="store_true", help="Remove the local encrypted session file"
    )
    args = parser.parse_args()
    if args.forget_session:
        CACHE.unlink(missing_ok=True)
        print("Local remembered session removed.")
        return 0
    target = dashboard_id(args.url)
    token = authenticate(args.non_interactive, args.remember_session, args.jwt)
    update_dashboard(token, target, args.apply)
    return 0


if __name__ == "__main__":
    try:
        raise SystemExit(main())
    except (RuntimeError, ValueError, KeyError) as exc:
        print(str(exc), file=sys.stderr)
        raise SystemExit(1) from None
