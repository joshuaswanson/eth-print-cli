"""SavaPage webprint API client for ETH Zurich."""

import json
import mimetypes
import tempfile
from pathlib import Path

import requests

BASE_URL = "https://webprint.ethz.ch"
SESSION_DIR = Path.home() / ".config" / "eth-print-cli"
SESSION_FILE = SESSION_DIR / "session.json"

SUPPORTED_EXTENSIONS = {
    ".pdf", ".html", ".txt", ".ps",
    ".bmp", ".gif", ".jpg", ".jpeg", ".png", ".svg", ".tiff",
}


# Target media sizes in points (1 point = 1/72 inch)
MEDIA_DIMENSIONS = {
    "iso_a4_210x297mm": (595.28, 841.89),
    "iso_a3_297x420mm": (841.89, 1190.55),
    "na_letter_8.5x11in": (612.0, 792.0),
}

# How far off (in points) a PDF page can be before we consider it mismatched
_SIZE_TOLERANCE = 5.0


def _points_to_size_name(w, h):
    """Try to match point dimensions to a known paper size name."""
    for name, (tw, th) in MEDIA_DIMENSIONS.items():
        if (abs(w - tw) < _SIZE_TOLERANCE and abs(h - th) < _SIZE_TOLERANCE) or \
           (abs(w - th) < _SIZE_TOLERANCE and abs(h - tw) < _SIZE_TOLERANCE):
            # Extract friendly name like "A4" from "iso_a4_210x297mm"
            parts = name.split("_")
            return parts[1].upper() if len(parts) > 1 else name
    # Fall back to mm dimensions
    w_mm = w * 25.4 / 72
    h_mm = h * 25.4 / 72
    return f"{w_mm:.0f}x{h_mm:.0f}mm"


def resize_pdf(input_path, target_media):
    """Resize a PDF to match the target media size if needed.

    Returns (path_to_upload, temp_file_to_cleanup, source_size_name).
    temp_file_to_cleanup is None if no resize was needed.
    source_size_name is None if no resize was needed.
    """
    target_dims = MEDIA_DIMENSIONS.get(target_media)
    if target_dims is None:
        return input_path, None, None

    try:
        import fitz
    except ImportError:
        return input_path, None, None

    doc = fitz.open(str(input_path))
    target_w, target_h = target_dims
    needs_resize = False
    source_size = None

    for page in doc:
        pw, ph = page.rect.width, page.rect.height
        # Check both orientations (portrait and landscape)
        portrait_match = (
            abs(pw - target_w) < _SIZE_TOLERANCE
            and abs(ph - target_h) < _SIZE_TOLERANCE
        )
        landscape_match = (
            abs(pw - target_h) < _SIZE_TOLERANCE
            and abs(ph - target_w) < _SIZE_TOLERANCE
        )
        if not portrait_match and not landscape_match:
            needs_resize = True
            source_size = _points_to_size_name(pw, ph)
            break

    if not needs_resize:
        doc.close()
        return input_path, None, None

    # Build a new PDF with pages scaled to the target size
    new_doc = fitz.open()
    for page in doc:
        pw, ph = page.rect.width, page.rect.height

        # Preserve orientation: if source is landscape, make target landscape too
        if pw > ph:
            page_w, page_h = max(target_w, target_h), min(target_w, target_h)
        else:
            page_w, page_h = min(target_w, target_h), max(target_w, target_h)

        new_page = new_doc.new_page(width=page_w, height=page_h)
        scale = min(page_w / pw, page_h / ph)
        x_off = (page_w - pw * scale) / 2
        y_off = (page_h - ph * scale) / 2
        dest = fitz.Rect(x_off, y_off, x_off + pw * scale, y_off + ph * scale)
        new_page.show_pdf_page(dest, doc, page.number)

    tmp = tempfile.NamedTemporaryFile(
        suffix=".pdf", prefix="ethprint_", delete=False
    )
    new_doc.save(tmp.name)
    new_doc.close()
    doc.close()
    tmp.close()

    return Path(tmp.name), tmp.name, source_size


class WebPrintError(Exception):
    pass


class AuthError(WebPrintError):
    pass


def _browser_login(username, password):
    """Use playwright to log in via the real web UI and extract session cookies.

    SavaPage requires a Wicket-initialized server session that can only be
    created by rendering the page with JavaScript. A plain requests POST to
    /api will fail with 'no user info' without this step.
    """
    try:
        from playwright.sync_api import sync_playwright
    except ImportError:
        raise AuthError(
            "playwright is required for login. "
            "Install it with: pip install playwright && playwright install chromium"
        )

    with sync_playwright() as p:
        browser = p.chromium.launch(headless=True)
        context = browser.new_context(ignore_https_errors=True)
        page = context.new_page()

        page.goto(f"{BASE_URL}/user", wait_until="networkidle")

        # Fill in the login form
        page.fill("#sp-login-user-name", username)
        page.fill("#sp-login-user-password", password)
        page.click("#sp-btn-login-name")

        # Wait for navigation to the main page (successful login)
        try:
            page.wait_for_function(
                """() => {
                    const el = document.querySelector('#page-main');
                    return el && el.classList.contains('ui-page-active');
                }""",
                timeout=10000,
            )
        except Exception:
            # Check for error message
            error_text = page.text_content("body")
            browser.close()
            if "invalid" in error_text.lower() or "denied" in error_text.lower():
                raise AuthError("Invalid username or password")
            raise AuthError("Login failed (timeout waiting for main page)")

        # Extract cookies
        cookies = context.cookies()
        browser.close()

    cookie_dict = {}
    for c in cookies:
        if "ethz.ch" in c["domain"]:
            cookie_dict[c["name"]] = c["value"]

    if not cookie_dict:
        raise AuthError("No session cookies received after login")

    return cookie_dict


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
        """Authenticate with ETH credentials via headless browser."""
        cookies = _browser_login(username, password)
        self.session.cookies.update(cookies)
        self._user = username
        self._save_session()
        return True

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

        content_type = mimetypes.guess_type(path.name)[0] or "application/octet-stream"
        with open(path, "rb") as f:
            resp = self.session.post(
                f"{BASE_URL}/upload/webprint",
                files={"file": (path.name, f, content_type)},
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
