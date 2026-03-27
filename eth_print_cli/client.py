"""SavaPage webprint API client for ETH Zurich."""

import json
from pathlib import Path

import requests

BASE_URL = "https://webprint.ethz.ch"
SESSION_DIR = Path.home() / ".config" / "eth-print-cli"
SESSION_FILE = SESSION_DIR / "session.json"

SUPPORTED_EXTENSIONS = {
    ".pdf", ".html", ".txt", ".ps",
    ".bmp", ".gif", ".jpg", ".jpeg", ".png", ".svg", ".tiff",
}


class WebPrintError(Exception):
    pass


class AuthError(WebPrintError):
    pass


class Client:
    def __init__(self):
        self.session = requests.Session()
        self.session.verify = True
        self._load_session()

    def _load_session(self):
        if SESSION_FILE.exists():
            data = json.loads(SESSION_FILE.read_text())
            self.session.cookies.update(data.get("cookies", {}))
            self._user = data.get("user")
        else:
            self._user = None

    def _save_session(self):
        SESSION_DIR.mkdir(parents=True, exist_ok=True)
        data = {
            "cookies": dict(self.session.cookies),
            "user": self._user,
        }
        SESSION_FILE.write_text(json.dumps(data))

    def _api_call(self, request, dto=None, **extra):
        payload = {
            "request": request,
            "webAppType": "USER",
        }
        if self._user:
            payload["user"] = self._user
        if dto is not None:
            payload["dto"] = json.dumps(dto)
        payload.update(extra)

        resp = self.session.post(f"{BASE_URL}/api", data=payload)
        resp.raise_for_status()
        result = resp.json()

        code = result.get("result", {}).get("code", "3")
        if code == "99":
            raise AuthError(
                result["result"].get("txt", "Authentication required")
            )
        return result

    @property
    def user(self):
        return self._user

    def login(self, username, password):
        """Authenticate with ETH credentials."""
        resp = self.session.post(
            f"{BASE_URL}/api",
            data={
                "request": "login",
                "webAppType": "USER",
                "dto": json.dumps({
                    "authMode": "NAME",
                    "authId": username,
                    "authPw": password,
                }),
            },
        )
        resp.raise_for_status()
        result = resp.json()
        code = result.get("result", {}).get("code")

        if code == "0":
            self._user = username
            self._save_session()
            return True

        # code 99 = another session active, still counts as success
        if code == "99":
            self._user = username
            self._save_session()
            return True

        msg = result.get("result", {}).get("txt", "Login failed")
        raise AuthError(msg)

    def logout(self):
        """End the current session."""
        try:
            self._api_call("logout")
        except Exception:
            pass
        if SESSION_FILE.exists():
            SESSION_FILE.unlink()
        self._user = None
        self.session.cookies.clear()

    def upload(self, file_path):
        """Upload a file to the webprint inbox. Returns True on success."""
        path = Path(file_path)
        if not path.exists():
            raise WebPrintError(f"File not found: {path}")

        suffix = path.suffix.lower()
        if suffix not in SUPPORTED_EXTENSIONS:
            raise WebPrintError(
                f"Unsupported file type: {suffix}. "
                f"Supported: {', '.join(sorted(SUPPORTED_EXTENSIONS))}"
            )

        with open(path, "rb") as f:
            resp = self.session.post(
                f"{BASE_URL}/upload/webprint",
                files={"file": (path.name, f)},
            )

        resp.raise_for_status()
        result = resp.json()
        code = result.get("result", {}).get("code")

        if code != "0":
            msg = result.get("result", {}).get("txt", "Upload failed")
            raise WebPrintError(msg)

        statuses = result.get("filesStatus", {})
        failed = [name for name, ok in statuses.items() if not ok]
        if failed:
            raise WebPrintError(f"Upload failed for: {', '.join(failed)}")

        return True

    def print_job(
        self,
        printer="CARD-STUD",
        copies=1,
        color=False,
        duplex=True,
        media="iso_a4_210x297mm",
        pages="",
        job_index=-1,
    ):
        """Submit a print job for documents in the inbox."""
        sides = "two-sided-long-edge" if duplex else "one-sided"
        color_mode = "color" if color else "monochrome"

        dto = {
            "user": self._user,
            "printer": printer,
            "jobName": "",
            "jobIndex": job_index,
            "landscapeView": False,
            "pageScaling": "FIT",
            "copies": copies,
            "ranges": pages,
            "collate": True,
            "removeGraphics": False,
            "ecoprint": False,
            "clearScope": None,
            "separateDocs": True,
            "archive": False,
            "options": {
                "media-source": "auto",
                "media": media,
                "sides": sides,
                "print-color-mode": color_mode,
                "number-up": "1",
            },
            "delegation": None,
            "jobTicket": False,
            "jobTicketType": "PRINT",
        }

        result = self._api_call("printer-print", dto=dto)
        code = result.get("result", {}).get("code")
        msg = result.get("result", {}).get("txt", "")

        if code != "0":
            raise WebPrintError(msg or "Print failed")

        return msg or "Print job submitted"

    def clear_inbox(self):
        """Delete all documents from the inbox."""
        result = self._api_call("inbox-clear")
        code = result.get("result", {}).get("code")
        return code == "0"

    def get_balance(self):
        """Get account balance (returned in the stats)."""
        result = self._api_call("user-get-stats")
        code = result.get("result", {}).get("code")
        if code != "0":
            raise WebPrintError("Failed to get stats")
        # Balance is in the dto
        dto = result.get("dto")
        if isinstance(dto, str):
            dto = json.loads(dto)
        if dto and "accountInfo" in dto:
            return dto["accountInfo"].get("balance", "unknown")
        return "unknown"

    def check_session(self):
        """Check if the current session is still valid."""
        try:
            resp = self.session.post(
                f"{BASE_URL}/api",
                data={
                    "request": "user-get-stats",
                    "webAppType": "USER",
                    "user": self._user or "",
                },
            )
            resp.raise_for_status()
            result = resp.json()
            return result.get("result", {}).get("code") == "0"
        except Exception:
            return False
