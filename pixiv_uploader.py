import importlib.util
import json
import mimetypes
import os
import re
import shutil
import sqlite3
import tempfile
import subprocess
import sys
import time
import uuid
from pathlib import Path
from typing import Callable, Dict, Iterable, List, Optional, Tuple

import requests


PIXIV_BROWSER_CHANNELS = ["msedge", "chrome", "chromium"]
PIXIV_VISIBILITY_OPTIONS = ["public", "mypixiv", "private"]
PIXIV_AGE_OPTIONS = ["all", "R-18", "R-18G"]
PIXIV_UPLOAD_MODE_OPTIONS = [
    {"value": "browser", "label": "浏览器自动填写"},
    {"value": "direct", "label": "Cookie + CSRF 直传"},
]
PIXIV_BROWSER_USER_DATA_DIRS = {
    "msedge": Path(os.environ.get("LOCALAPPDATA", "")) / "Microsoft" / "Edge" / "User Data",
    "chrome": Path(os.environ.get("LOCALAPPDATA", "")) / "Google" / "Chrome" / "User Data",
    "chromium": Path(os.environ.get("LOCALAPPDATA", "")) / "Chromium" / "User Data",
}
PIXIV_DIRECT_TOKEN_PATTERNS = [
    re.compile(r"""g_csrfToken\s*=\s*["'](?P<token>[^"']+)""", re.IGNORECASE),
    re.compile(r""""csrfToken"\s*:\s*"(?P<token>[^"]+)""", re.IGNORECASE),
    re.compile(r""""token"\s*:\s*"(?P<token>[^"]+)""", re.IGNORECASE),
    re.compile(r"""name=["']csrf-token["']\s+content=["'](?P<token>[^"']+)""", re.IGNORECASE),
]


class _BasePixivUploader:
    def __init__(self, settings: dict, log_fn: Optional[Callable[[str], None]] = None):
        self.settings = settings
        self.log_fn = log_fn or (lambda message: None)

    def _log(self, message: str) -> None:
        self.log_fn(message)

    def ensure_ready(self) -> bool:
        return True

    def close(self) -> None:
        return None

    def capture_debug_snapshot(self, tag_hint: str = "") -> dict:
        raise RuntimeError("当前 Pixiv 上传模式不支持调试快照。")


def _browser_label(browser_channel: str) -> str:
    mapping = {
        "msedge": "Microsoft Edge",
        "chrome": "Google Chrome",
        "chromium": "Chromium",
    }
    key = str(browser_channel or "msedge").strip().lower()
    return mapping.get(key, key or "浏览器")


def _resolve_browser_user_data_dir(browser_channel: str) -> Path:
    channel = str(browser_channel or "msedge").strip().lower()
    path = PIXIV_BROWSER_USER_DATA_DIRS.get(channel)
    if path is None or not str(path):
        raise RuntimeError(f"暂不支持从 {browser_channel} 导入 Pixiv 登录态")
    return path


def _browser_profile_candidates(user_data_dir: Path) -> List[str]:
    local_state_path = user_data_dir / "Local State"
    names: List[str] = []
    try:
        payload = json.loads(local_state_path.read_text(encoding="utf-8"))
    except Exception:
        payload = {}

    profile_section = payload.get("profile", {}) if isinstance(payload, dict) else {}
    last_used = str(profile_section.get("last_used") or "").strip()
    if last_used:
        names.append(last_used)

    info_cache = profile_section.get("info_cache", {})
    if isinstance(info_cache, dict):
        for raw_name in info_cache.keys():
            name = str(raw_name or "").strip()
            if name and name not in names:
                names.append(name)

    for candidate in sorted(user_data_dir.glob("Profile *")):
        if candidate.is_dir() and candidate.name not in names:
            names.append(candidate.name)

    for fixed in ("Default",):
        fixed_path = user_data_dir / fixed
        if fixed_path.is_dir() and fixed not in names:
            names.insert(0, fixed)

    return names


def _cookie_db_candidates(user_data_dir: Path, profile_name: str) -> List[Path]:
    profile_dir = user_data_dir / profile_name
    return [
        profile_dir / "Network" / "Cookies",
        profile_dir / "Cookies",
    ]


def _snapshot_sqlite_database(source: Path, target: Path) -> None:
    source_uri = f"{source.resolve().as_uri()}?mode=ro"
    target.parent.mkdir(parents=True, exist_ok=True)
    if target.exists():
        target.unlink()
    source_conn = sqlite3.connect(source_uri, uri=True)
    target_conn = sqlite3.connect(str(target))
    try:
        source_conn.backup(target_conn)
        target_conn.commit()
    finally:
        target_conn.close()
        source_conn.close()


def _copy_regular_auth_file(source: Path, target: Path, *, required: bool = False) -> None:
    try:
        target.parent.mkdir(parents=True, exist_ok=True)
        shutil.copy2(source, target)
    except FileNotFoundError:
        if required:
            raise
    except OSError:
        if required:
            raise


def _copy_browser_auth_files(user_data_dir: Path, profile_name: str, destination_root: Path) -> None:
    destination_root.mkdir(parents=True, exist_ok=True)
    local_state = user_data_dir / "Local State"
    if local_state.exists():
        _copy_regular_auth_file(local_state, destination_root / "Local State", required=True)

    source_profile = user_data_dir / profile_name
    target_profile = destination_root / profile_name
    (target_profile / "Network").mkdir(parents=True, exist_ok=True)

    for relative in (
        Path("Preferences"),
        Path("Secure Preferences"),
    ):
        source = source_profile / relative
        if not source.exists():
            continue
        target = target_profile / relative
        _copy_regular_auth_file(source, target)

    cookie_snapshot_errors: List[str] = []
    cookie_snapshot_done = False
    for source in _cookie_db_candidates(user_data_dir, profile_name):
        if not source.exists():
            continue
        target = destination_root / profile_name / source.relative_to(source_profile)
        try:
            _snapshot_sqlite_database(source, target)
            cookie_snapshot_done = True
        except Exception as exc:
            cookie_snapshot_errors.append(f"{source.name}: {exc}")

    if not cookie_snapshot_done:
        if cookie_snapshot_errors:
            raise RuntimeError("无法生成浏览器 Cookie 快照: " + "；".join(cookie_snapshot_errors))
        raise FileNotFoundError(f"没有找到 {profile_name} 的 Cookie 数据库")


def _pixiv_cookie_domain_matches(domain: str, host: str = "www.pixiv.net") -> bool:
    raw = str(domain or "").strip().lower()
    request_host = str(host or "www.pixiv.net").strip().lower()
    if not raw:
        return False
    if raw.startswith("."):
        raw = raw[1:]
    return request_host == raw or request_host.endswith(f".{raw}")


def _build_pixiv_cookie_header(cookies: Iterable[dict], host: str = "www.pixiv.net") -> str:
    selected: Dict[str, str] = {}
    for item in cookies:
        if not isinstance(item, dict):
            continue
        domain = str(item.get("domain") or "").strip()
        name = str(item.get("name") or "").strip()
        value = str(item.get("value") or "")
        if not name or not _pixiv_cookie_domain_matches(domain, host=host):
            continue
        selected[name] = value
    return "; ".join(f"{name}={value}" for name, value in sorted(selected.items()))


def _extract_pixiv_csrf_token(html: str) -> str:
    source = str(html or "")
    for pattern in PIXIV_DIRECT_TOKEN_PATTERNS:
        match = pattern.search(source)
        if match:
            token = str(match.group("token") or "").strip()
            if token:
                return token
    return ""


def _is_pixiv_login_html(html: str, url: str = "") -> bool:
    page_url = str(url or "").strip().lower()
    page_html = str(html or "").lower()
    if "accounts.pixiv.net/login" in page_url:
        return True

    has_password_input = (
        'type="password"' in page_html
        or "type='password'" in page_html
        or 'autocomplete="current-password"' in page_html
        or "autocomplete='current-password'" in page_html
    )
    has_login_form = (
        ('name="pixiv_id"' in page_html or "name='pixiv_id'" in page_html)
        or ('autocomplete="username"' in page_html or "autocomplete='username'" in page_html)
        or ('form' in page_html and 'action="https://accounts.pixiv.net/login"' in page_html)
        or ("form" in page_html and "action='https://accounts.pixiv.net/login'" in page_html)
    )
    return has_password_input and has_login_form


def _looks_like_cookie_access_block(error_text: str) -> bool:
    text = str(error_text or "").strip().lower()
    if not text:
        return False
    return any(
        needle in text
        for needle in (
            "unable to open database file",
            "permission denied",
            "access is denied",
            "being used by another process",
            "file is locked or in use",
            "winerror 32",
        )
    )


def _should_fallback_to_interactive_browser_auth(errors: List[str]) -> bool:
    return any(_looks_like_cookie_access_block(message) for message in (errors or []))


def _looks_like_transient_page_state_error(error_text: str) -> bool:
    text = str(error_text or "").strip().lower()
    if not text:
        return False
    return any(
        needle in text
        for needle in (
            "page.content",
            "page.evaluate",
            "page.goto",
            "unable to retrieve content because the page is navigating",
            "execution context was destroyed",
            "most likely because of a navigation",
            "navigation interrupted by another one",
            "timeout",
            "exceeded",
        )
    )


def _read_pixiv_auth_from_page(context, page) -> dict:
    deadline = time.time() + 15.0
    last_exc = None
    while time.time() < deadline:
        try:
            try:
                page.wait_for_load_state("domcontentloaded", timeout=5000)
            except Exception as exc:
                if not _looks_like_transient_page_state_error(exc):
                    raise

            final_url = page.url
            cookies = context.cookies(["https://www.pixiv.net/", _BrowserPixivUploader.UPLOAD_URL])
            cookie_header = _build_pixiv_cookie_header(cookies)
            html = ""
            try:
                html = page.content()
            except Exception as exc:
                if not _looks_like_transient_page_state_error(exc):
                    raise
                if cookie_header and (
                    "pixiv.net/upload.php" in final_url
                    or "pixiv.net/illustration/create" in final_url
                ):
                    return {
                        "html": "",
                        "url": final_url,
                        "loginRequired": False,
                        "cookie": cookie_header,
                        "csrfToken": "",
                    }
                raise
            login_required = _is_pixiv_login_html(html, final_url)
            csrf_token = ""
            if not login_required:
                try:
                    csrf_token = page.evaluate(
                        """() => {
                            const asText = (value) => (typeof value === 'string' ? value.trim() : '');
                            if (asText(window.g_csrfToken)) return asText(window.g_csrfToken);
                            const meta =
                                document.querySelector('meta[name="csrf-token"]') ||
                                document.querySelector('meta[name="global-data"]');
                            if (meta && asText(meta.content)) return asText(meta.content);
                            for (const script of Array.from(document.scripts || [])) {
                                const text = script.textContent || '';
                                const patterns = [
                                    /g_csrfToken\\s*=\\s*["']([^"']+)/i,
                                    /"csrfToken"\\s*:\\s*"([^"]+)/i,
                                    /"token"\\s*:\\s*"([^"]+)/i,
                                ];
                                for (const pattern of patterns) {
                                    const match = text.match(pattern);
                                    if (match && asText(match[1])) return asText(match[1]);
                                }
                            }
                            return '';
                        }"""
                    )
                except Exception as exc:
                    if not _looks_like_transient_page_state_error(exc):
                        raise
                    csrf_token = ""
                if not csrf_token:
                    csrf_token = _extract_pixiv_csrf_token(html)
            return {
                "html": html,
                "url": final_url,
                "loginRequired": login_required,
                "cookie": cookie_header,
                "csrfToken": csrf_token,
            }
        except Exception as exc:
            if not _looks_like_transient_page_state_error(exc):
                raise
            last_exc = exc
            page.wait_for_timeout(350)

    if last_exc is not None:
        raise RuntimeError(f"Pixiv 页面仍在跳转，请稍候再试：{last_exc}")
    raise RuntimeError("Pixiv 页面未能及时稳定")


def _build_pixiv_import_result(
    *,
    browser_channel: str,
    browser_name: str,
    profile_name: str,
    cookie_header: str,
    csrf_token: str,
    source: str,
) -> dict:
    message = f"已从 {browser_name} 的 {profile_name} 导入 Pixiv 登录态"
    if not csrf_token:
        message += "，但还没有拿到 CSRF Token"
    return {
        "browserChannel": browser_channel,
        "browserLabel": browser_name,
        "profileName": profile_name,
        "cookie": cookie_header,
        "csrfToken": csrf_token,
        "cookieCount": max(1, cookie_header.count(";") + 1),
        "source": source,
        "needsCsrfProbe": not bool(csrf_token),
        "message": message,
    }


def _interactive_pixiv_browser_auth(playwright, browser_channel: str, browser_name: str, log_fn: Callable[[str], None]) -> dict:
    log = log_fn or (lambda message: None)
    with tempfile.TemporaryDirectory(prefix="pixiv_auth_interactive_") as temp_dir_name:
        temp_root = Path(temp_dir_name)
        launch_kwargs = {
            "user_data_dir": str(temp_root),
            "headless": False,
        }
        if browser_channel != "chromium":
            launch_kwargs["channel"] = browser_channel

        context = None
        try:
            context = playwright.chromium.launch_persistent_context(**launch_kwargs)
            page = context.pages[0] if context.pages else context.new_page()
            page.goto(_BrowserPixivUploader.UPLOAD_URL, wait_until="domcontentloaded", timeout=45000)
            try:
                page.bring_to_front()
            except Exception:
                pass

            log(f"[Pixiv] {browser_name} 的 Cookie 数据库当前被占用，已改为临时登录窗口导入。")
            log("[Pixiv] 请在弹出的浏览器窗口里登录 Pixiv；登录完成后会自动抓取 Cookie 和 CSRF。")

            deadline = time.time() + 300
            while time.time() < deadline:
                snapshot = _read_pixiv_auth_from_page(context, page)
                if (
                    not snapshot["loginRequired"]
                    and snapshot["cookie"]
                ):
                    cookie_header = snapshot["cookie"]
                    csrf_token = snapshot["csrfToken"]
                    if csrf_token:
                        log(f"[Pixiv] 已通过 {browser_name} 临时登录窗口导入 Pixiv 登录态。")
                    else:
                        log(f"[Pixiv] 已通过 {browser_name} 临时登录窗口拿到 Pixiv Cookie，但还没有抓到 CSRF Token。")
                    return _build_pixiv_import_result(
                        browser_channel=browser_channel,
                        browser_name=browser_name,
                        profile_name="interactive-login",
                        cookie_header=cookie_header,
                        csrf_token=csrf_token,
                        source="interactive-login",
                    )
                page.wait_for_timeout(1000)

            raise RuntimeError("等待 Pixiv 登录超时；请在弹出的浏览器窗口里完成登录后重试")
        finally:
            if context is not None:
                try:
                    context.close()
                except Exception:
                    pass


class _BrowserPixivUploader(_BasePixivUploader):
    """Best-effort Pixiv uploader driven by browser automation."""

    UPLOAD_URL = "https://www.pixiv.net/upload.php"
    LOGIN_TEXTS = ["Login", "Log in", "ログイン", "登录", "登入"]
    LOGIN_REQUIRED_SELECTORS = [
        "input[type='password']",
        "input[name='password']",
        "input[autocomplete='current-password']",
        "form[action*='login']",
        "button[type='submit']",
    ]
    UPLOAD_READY_SELECTORS = [
        "input[type='file']",
        "input[placeholder*='title' i]",
        "textarea[placeholder*='caption' i]",
        "textarea[placeholder*='description' i]",
    ]
    TAG_INPUT_SELECTORS = [
        "[role='combobox'] input:not([type='checkbox'])",
        "[role='combobox'] textarea",
        "[role='combobox'] [contenteditable='true']",
        "input[name*='tag' i]:not([type='checkbox'])",
        "input[id*='tag' i]:not([type='checkbox'])",
        "input[placeholder*='tag' i]",
        "input[placeholder*='Tag' i]",
        "input[placeholder*='銈裤偘']",
        "input[placeholder*='鏍囩']",
        "input[aria-label*='tag' i]",
        "input[aria-label*='銈裤偘']",
        "input[aria-label*='鏍囩']",
        "[role='combobox']",
    ]
    TAG_INPUT_LABELS = ["Tags", "Tag", "銈裤偘", "鏍囩"]
    TAG_AUTOCOMPLETE_SELECTORS = [
        "[role='listbox'] [role='option']",
        "[role='listbox'] button",
        "[role='presentation'] [role='option']",
        "[aria-controls][role='combobox'] ~ [role='listbox'] [role='option']",
    ]

    def __init__(self, settings: dict, log_fn: Optional[Callable[[str], None]] = None):
        super().__init__(settings, log_fn=log_fn)
        self._playwright = None
        self._context = None
        self._page = None

    def ensure_ready(self) -> bool:
        if importlib.util.find_spec("playwright") is None:
            self._log("[Pixiv] 正在安装 Playwright...")
            subprocess.check_call([sys.executable, "-m", "pip", "install", "-q", "playwright"])
        return True

    def close(self) -> None:
        if self._context is not None:
            try:
                self._context.close()
            except Exception:
                pass
        self._context = None
        self._page = None

        if self._playwright is not None:
            try:
                self._playwright.stop()
            except Exception:
                pass
        self._playwright = None

    def _profile_dir(self) -> Path:
        profile_dir = self.settings.get("profile_dir") or (Path(__file__).parent / ".pixiv_profile")
        profile_dir = Path(profile_dir)
        profile_dir.mkdir(parents=True, exist_ok=True)
        return profile_dir

    def _ensure_page(self):
        if self._page is not None and not self._page.is_closed():
            return self._page

        self.ensure_ready()
        from playwright.sync_api import sync_playwright

        self._playwright = sync_playwright().start()
        launch_kwargs = {
            "user_data_dir": str(self._profile_dir()),
            "headless": False,
            "viewport": {"width": 1440, "height": 1080},
        }

        browser_channel = self.settings.get("browser_channel", "msedge")
        if browser_channel != "chromium":
            launch_kwargs["channel"] = browser_channel

        self._context = self._playwright.chromium.launch_persistent_context(**launch_kwargs)
        self._page = self._context.pages[0] if self._context.pages else self._context.new_page()
        return self._page

    def _debug_dir(self) -> Path:
        out_dir = Path(__file__).parent / "tmp_pixiv_diag"
        out_dir.mkdir(parents=True, exist_ok=True)
        return out_dir

    def _locator_outer_html(self, locator) -> str:
        if locator is None or self._count(locator) <= 0:
            return ""
        try:
            return str(locator.first.evaluate("(el) => el.outerHTML || ''") or "")
        except Exception:
            return ""

    def _collect_tag_debug_elements(self, page, tag_hint: str = "") -> List[dict]:
        tag_container = self._find_tag_container(page)
        root = tag_container or page.locator("body").first
        try:
            values = root.evaluate(
                """(node, payload) => {
                    const normalize = (text) => (text || '').replace(/\\s+/g, ' ').trim();
                    const selectors = payload.selectors || [];
                    const hint = normalize(payload.hint || '');
                    const inputEl =
                        selectors.map((selector) => node.querySelector(selector)).find(Boolean) ||
                        node.querySelector('[role="combobox"] input, [role="combobox"] textarea, [role="combobox"] [contenteditable="true"], [role="combobox"]') ||
                        null;
                    const inputRect = inputEl ? inputEl.getBoundingClientRect() : null;
                    const items = [];
                    const elements = Array.from(node.querySelectorAll('button, a, [role="button"], [role="link"], [role="option"], span, div, li'));

                    for (const el of elements) {
                        if (!el || !el.isConnected) continue;
                        const rect = el.getBoundingClientRect();
                        if (!rect.width || !rect.height) continue;
                        if (inputRect) {
                            if (rect.top > inputRect.bottom + 240) continue;
                            if (rect.bottom < inputRect.top - 80) continue;
                        }
                        const text = normalize(el.textContent || '');
                        const ariaLabel = normalize(el.getAttribute('aria-label') || '');
                        const title = normalize(el.getAttribute('title') || '');
                        const combined = `${text} ${ariaLabel} ${title}`.trim();
                        if (!combined) continue;
                        if (hint && !combined.includes(hint) && !combined.includes(`#${hint}`)) continue;
                        items.push({
                            text,
                            ariaLabel,
                            title,
                            tag: el.tagName,
                            role: el.getAttribute('role') || '',
                            id: el.id || '',
                            className: typeof el.className === 'string' ? el.className : '',
                            rect: {
                                x: Math.round(rect.x),
                                y: Math.round(rect.y),
                                width: Math.round(rect.width),
                                height: Math.round(rect.height),
                            },
                        });
                        if (items.length >= 80) break;
                    }

                    return items;
                }""",
                {"selectors": self.TAG_INPUT_SELECTORS, "hint": tag_hint},
            )
        except Exception:
            return []
        return [item for item in (values or []) if isinstance(item, dict)]

    def capture_debug_snapshot(self, tag_hint: str = "") -> dict:
        page = self._ensure_page()
        page.wait_for_timeout(200)

        out_dir = self._debug_dir()
        stamp = time.strftime("%Y%m%d_%H%M%S")
        suffix = uuid.uuid4().hex[:6]
        prefix = f"pixiv_debug_{stamp}_{suffix}"
        json_path = out_dir / f"{prefix}.json"
        html_path = out_dir / f"{prefix}.html"
        screenshot_path = out_dir / f"{prefix}.png"

        tag_container = self._find_tag_container(page)
        suggestion_container = self._find_tag_suggestion_container(page)
        snapshot = {
            "tagHint": str(tag_hint or ""),
            "url": page.url,
            "title": page.title(),
            "activeElement": self._describe_active_element(page),
            "tagCount": self._read_tag_count(page),
            "tagInputValue": self._read_tag_input_value(page),
            "selectedTagChips": self._read_selected_tag_chips(page),
            "selectedTagInlineTokens": self._read_selected_tag_inline_tokens(page),
            "selectedTagTexts": self._read_selected_tag_texts(page),
            "tagContainerHtml": self._locator_outer_html(tag_container),
            "suggestionContainerHtml": self._locator_outer_html(suggestion_container),
            "nearbyTagElements": self._collect_tag_debug_elements(page, tag_hint=tag_hint),
        }

        html_path.write_text(page.content(), encoding="utf-8")
        json_path.write_text(json.dumps(snapshot, ensure_ascii=False, indent=2), encoding="utf-8")
        try:
            page.screenshot(path=str(screenshot_path), full_page=True)
        except Exception:
            screenshot_path.write_bytes(b"")

        self._log(f"[Pixiv Debug] Snapshot saved: {json_path}")
        return {
            "jsonPath": str(json_path),
            "htmlPath": str(html_path),
            "screenshotPath": str(screenshot_path),
            "tagCount": snapshot["tagCount"],
            "tagInputValue": snapshot["tagInputValue"],
            "selectedTagChips": snapshot["selectedTagChips"],
            "selectedTagInlineTokens": snapshot["selectedTagInlineTokens"],
            "url": snapshot["url"],
        }

    def _count(self, locator) -> int:
        try:
            return locator.count()
        except Exception:
            return 0

    def _first_locator(self, page, selectors: Iterable[str] = (), labels: Iterable[str] = (), texts: Iterable[str] = ()):
        for selector in selectors:
            locator = page.locator(selector)
            if self._count(locator) > 0:
                return locator.first

        for label in labels:
            locator = page.get_by_label(label, exact=False)
            if self._count(locator) > 0:
                return locator.first

        for text in texts:
            locator = page.get_by_text(text, exact=False)
            if self._count(locator) > 0:
                return locator.first

        return None

    def _is_fillable_locator(self, locator) -> bool:
        try:
            tag_name = str(locator.evaluate("el => (el.tagName || '').toLowerCase()") or "").lower()
            if tag_name == "textarea":
                return True
            if tag_name == "input":
                input_type = str(locator.get_attribute("type") or "text").lower()
                return input_type not in {"checkbox", "radio", "file", "hidden", "submit", "button", "image"}

            contenteditable = str(locator.get_attribute("contenteditable") or "").lower()
            role = str(locator.get_attribute("role") or "").lower()
            return contenteditable == "true" or role in {"textbox", "searchbox"}
        except Exception:
            return False

    def _coerce_fillable_locator(self, locator):
        if locator is None or self._count(locator) <= 0:
            return None

        primary = locator.first
        if self._is_fillable_locator(primary):
            return primary

        descendant_selector = (
            "input:not([type='checkbox']):not([type='radio']):not([type='file']):not([type='hidden']), "
            "textarea, [contenteditable='true'], [role='textbox'], [role='searchbox']"
        )
        try:
            descendants = primary.locator(descendant_selector)
            if self._count(descendants) > 0 and self._is_fillable_locator(descendants.first):
                return descendants.first
        except Exception:
            pass

        return None

    def _first_fillable_locator(self, page, selectors: Iterable[str] = (), labels: Iterable[str] = (), texts: Iterable[str] = ()):
        for selector in selectors:
            locator = self._coerce_fillable_locator(page.locator(selector))
            if locator is not None:
                return locator

        for label in labels:
            locator = self._coerce_fillable_locator(page.get_by_label(label, exact=False))
            if locator is not None:
                return locator

        for text in texts:
            locator = self._coerce_fillable_locator(page.get_by_text(text, exact=False))
            if locator is not None:
                return locator

        return None

    def _has_any_text(self, page, texts: Iterable[str]) -> bool:
        for text in texts:
            locator = page.get_by_text(text, exact=False)
            if self._count(locator) > 0:
                return True
        return False

    def _find_group_container(self, page, group_labels: Iterable[str]):
        for label in group_labels:
            title_locator = page.get_by_text(label, exact=False)
            if self._count(title_locator) <= 0:
                continue
            try:
                container = title_locator.first.locator(
                    "xpath=ancestor::*[self::section or self::fieldset or self::div][.//input[@type='radio' or @type='checkbox']][1]"
                )
                if self._count(container) > 0:
                    return container.first
            except Exception:
                continue
        return None

    def _find_tag_container(self, page):
        tag_input = self._first_fillable_locator(
            page,
            selectors=self.TAG_INPUT_SELECTORS,
            labels=self.TAG_INPUT_LABELS,
            texts=(),
        )
        if tag_input is not None:
            try:
                ancestors = tag_input.locator("xpath=ancestor::*[self::section or self::fieldset or self::div]")
                ancestor_count = min(self._count(ancestors), 12)
                suggestion_candidate = None
                hash_candidate = None
                for index in range(ancestor_count):
                    candidate = ancestors.nth(index)
                    try:
                        text = str(candidate.evaluate("(el) => (el.textContent || '').replace(/\\s+/g, ' ').trim()") or "")
                    except Exception:
                        continue
                    if not text:
                        continue
                    if re.search(r"\b\d+\s*/\s*10\b", text):
                        return candidate
                    if suggestion_candidate is None and re.search(
                        r"(推荐标签|おすすめタグ|suggested tags|recommended tags)",
                        text,
                        re.IGNORECASE,
                    ):
                        suggestion_candidate = candidate
                    if hash_candidate is None and "#" in text:
                        hash_candidate = candidate
                if suggestion_candidate is not None:
                    return suggestion_candidate
                if hash_candidate is not None:
                    return hash_candidate
                if ancestor_count > 0:
                    return ancestors.nth(0)
            except Exception:
                pass

        for label in ("标签", "タグ", "Tags", "Tag"):
            title_locator = page.get_by_text(label, exact=False)
            if self._count(title_locator) <= 0:
                continue
            try:
                container = title_locator.first.locator(
                    "xpath=ancestor::*[self::section or self::fieldset or self::div][.//*[self::input or self::textarea or @contenteditable='true' or @role='combobox']][1]"
                )
                if self._count(container) > 0:
                    return container.first
            except Exception:
                continue
        return None

    def _find_tag_suggestion_container(self, page):
        tag_container = self._find_tag_container(page)
        search_roots = [tag_container] if tag_container is not None else []
        search_roots.append(page.locator("body").first)

        for root in search_roots:
            if root is None:
                continue
            for label in ("推荐标签", "おすすめタグ", "Suggested tags", "Recommended tags"):
                locator = root.get_by_text(label, exact=False)
                if self._count(locator) <= 0:
                    continue
                try:
                    container = locator.first.locator(
                        "xpath=ancestor::*[self::section or self::fieldset or self::div][.//a or .//button or .//*[@role='option'] or .//*[@role='link']][1]"
                    )
                    if self._count(container) > 0:
                        return container.first
                except Exception:
                    continue
        return None

    def _read_tag_count(self, page) -> Optional[int]:
        container = self._find_tag_container(page)
        if container is None:
            return None
        try:
            text = str(container.evaluate("(el) => el.textContent || ''") or "")
        except Exception:
            return None
        match = re.search(r"(\d+)\s*/\s*10", text)
        if not match:
            return None
        try:
            return int(match.group(1))
        except Exception:
            return None

    def _normalize_tag_text(self, value: str) -> str:
        text = re.sub(r"\s+", " ", str(value or "")).strip()
        while text.startswith("#"):
            text = text[1:].strip()
        return text.lower()

    def _find_tag_input(self, page):
        tag_container = self._find_tag_container(page)
        return self._first_fillable_locator(
            tag_container or page,
            selectors=self.TAG_INPUT_SELECTORS,
            labels=self.TAG_INPUT_LABELS,
            texts=(),
        )

    def _read_fillable_locator_value(self, locator) -> str:
        if locator is None:
            return ""
        try:
            return str(
                locator.evaluate(
                    """(el) => {
                        const tag = (el.tagName || '').toLowerCase();
                        const role = (el.getAttribute('role') || '').toLowerCase();
                        const editable = (el.getAttribute('contenteditable') || '').toLowerCase() === 'true';
                        let value = '';
                        if (tag === 'input' || tag === 'textarea') {
                            value = el.value || '';
                        } else if (editable || role === 'textbox' || role === 'searchbox') {
                            value = el.textContent || '';
                        } else {
                            value = (el.value || el.textContent || '') + '';
                        }
                        return value.replace(/\\s+/g, ' ').trim();
                    }"""
                )
                or ""
            ).strip()
        except Exception:
            return ""

    def _read_tag_input_value(self, page) -> str:
        locator = self._find_tag_input(page)
        return self._read_fillable_locator_value(locator)

    def _clear_fillable_locator_text(self, locator) -> bool:
        if locator is None:
            return False
        current_value = self._read_fillable_locator_value(locator)
        if not current_value:
            return False
        try:
            cleared = locator.evaluate(
                """(el) => {
                    const tag = (el.tagName || '').toLowerCase();
                    const role = (el.getAttribute('role') || '').toLowerCase();
                    const editable = (el.getAttribute('contenteditable') || '').toLowerCase() === 'true';
                    if (tag === 'input' || tag === 'textarea') {
                        el.value = '';
                    } else if (editable || role === 'textbox' || role === 'searchbox') {
                        el.textContent = '';
                    } else {
                        return false;
                    }
                    el.dispatchEvent(new Event('input', { bubbles: true }));
                    el.dispatchEvent(new Event('change', { bubbles: true }));
                    return true;
                }"""
            )
            if cleared:
                return True
        except Exception:
            pass
        try:
            locator.fill("")
            return True
        except Exception:
            return False

    def _log_tag_state(self, page, context: str, tag: str) -> None:
        count = self._read_tag_count(page)
        selected = self._read_selected_tag_chips(page)
        inline_selected = self._read_selected_tag_inline_tokens(page)
        input_value = self._read_tag_input_value(page)
        self._log(
            f"[Pixiv] Tag state after {context}: tag={tag}, count={count}, input={input_value or '<empty>'}, selected={selected}, inline={inline_selected}"
        )

    def _read_selected_tag_texts(self, page) -> List[str]:
        tag_container = self._find_tag_container(page)
        if tag_container is None:
            return []
        tag_input = self._first_fillable_locator(
            tag_container,
            selectors=[
                "[role='combobox'] input:not([type='checkbox'])",
                "[role='combobox'] textarea",
                "[role='combobox'] [contenteditable='true']",
                "input[name*='tag' i]:not([type='checkbox'])",
                "input[id*='tag' i]:not([type='checkbox'])",
                "input[placeholder*='tag' i]",
                "input[placeholder*='Tag' i]",
                "input[placeholder*='タグ']",
                "input[placeholder*='标签']",
                "input[aria-label*='tag' i]",
                "input[aria-label*='タグ']",
                "input[aria-label*='标签']",
                "[role='combobox']",
            ],
            labels=["Tags", "Tag", "タグ", "标签"],
            texts=(),
        )
        if tag_input is None:
            return []
        try:
            values = tag_input.evaluate(
                """(inputEl) => {
                    const normalize = (text) => (text || '').replace(/\\s+/g, ' ').trim();
                    const inputRect = inputEl.getBoundingClientRect();
                    const roots = [];
                    let node = inputEl.closest('[role="combobox"]') || inputEl.parentElement;
                    for (let depth = 0; node && depth < 4; depth += 1) {
                        roots.push(node);
                        node = node.parentElement;
                    }
                    const result = [];
                    const seen = new Set();

                    for (const root of roots) {
                        if (!root) continue;
                        const elements = Array.from(
                            root.querySelectorAll('button, [role="button"], span, div, a, li')
                        );
                        for (const el of elements) {
                            if (!el || !el.isConnected || el === inputEl) continue;
                            if (el.contains(inputEl)) continue;
                            if (el.closest('input, textarea, [contenteditable="true"], [role="textbox"], [role="searchbox"], [role="listbox"], [role="option"]')) {
                                continue;
                            }
                            const rect = el.getBoundingClientRect();
                            if (!rect.width || !rect.height) continue;
                            if (rect.top > inputRect.bottom + 12) continue;
                            if (rect.bottom < inputRect.top - 180) continue;

                            const candidates = [
                                normalize(el.textContent || ''),
                                normalize(el.getAttribute('aria-label') || ''),
                                normalize(el.getAttribute('title') || ''),
                            ];
                            for (const candidate of candidates) {
                                if (!candidate || !candidate.startsWith('#')) continue;
                                if (candidate.length <= 1) continue;
                                if (seen.has(candidate)) continue;
                                seen.add(candidate);
                                result.push(candidate);
                            }
                        }
                    }

                    return result.slice(0, 40);
                }"""
            )
        except Exception:
            return []
        return [str(value).strip() for value in (values or []) if str(value).strip()]

    def _read_selected_tag_chips(self, page) -> List[str]:
        tag_container = self._find_tag_container(page)
        if tag_container is None:
            return []
        try:
            values = tag_container.evaluate(
                """(container, payload) => {
                    const normalize = (text) => (text || '').replace(/\\s+/g, ' ').trim();
                    const selectors = payload.selectors || [];
                    const labels = (payload.labels || []).map((value) => normalize(value).toLowerCase()).filter(Boolean);
                    const stripDecorations = (text) =>
                        normalize(text)
                            .replace(/^#+/, '')
                            .replace(/[×✕✖✗✘✚＋+]+$/g, '')
                            .replace(/^[#＃]\s*/, '')
                            .trim();
                    const extractTokens = (text) => {
                        const normalized = normalize(text);
                        if (!normalized) return [];
                        const result = [];
                        const hashMatches = normalized.match(/#[^\\s#]+/g) || [];
                        for (const token of hashMatches) {
                            const cleaned = stripDecorations(token);
                            if (cleaned) result.push(cleaned);
                        }
                        const plain = stripDecorations(normalized);
                        if (
                            plain &&
                            !/^\d+\s*\/\s*\d+$/.test(plain) &&
                            !labels.includes(plain.toLowerCase()) &&
                            !/^(recommended tags|suggested tags|推荐标签|おすすめタグ)$/i.test(plain)
                        ) {
                            result.push(plain);
                        }
                        return result;
                    };
                    const isEditable = (el) =>
                        !!el.closest('input, textarea, [contenteditable="true"], [role="textbox"], [role="searchbox"], [role="listbox"], [role="option"]');
                    const inputEl =
                        selectors.map((selector) => container.querySelector(selector)).find(Boolean) ||
                        container.querySelector('[role="combobox"] input, [role="combobox"] textarea, [role="combobox"] [contenteditable="true"], [role="combobox"]') ||
                        null;
                    if (!inputEl) return [];
                    const inputRect = inputEl.getBoundingClientRect();
                    const result = [];
                    const seen = new Set();
                    const elements = Array.from(
                        container.querySelectorAll('button, [role="button"], a, [role="link"], span, div, li')
                    );

                    for (const el of elements) {
                        if (!el || !el.isConnected || el === inputEl) continue;
                        if (el.contains(inputEl)) continue;
                        if (isEditable(el)) continue;
                        const rect = el.getBoundingClientRect();
                        if (!rect.width || !rect.height) continue;
                        if (rect.top > inputRect.bottom + 8) continue;
                        if (rect.bottom < inputRect.top - 36) continue;

                        const plainText = normalize(el.textContent || '');
                        const lowerText = plainText.toLowerCase();
                        if (labels.some((label) => lowerText === label || lowerText.endsWith(' ' + label))) {
                            continue;
                        }

                        const candidates = [
                            plainText,
                            normalize(el.getAttribute('aria-label') || ''),
                            normalize(el.getAttribute('title') || ''),
                        ];
                        for (const candidate of candidates) {
                            for (const token of extractTokens(candidate)) {
                                if (token.length <= 1) continue;
                                if (seen.has(token)) continue;
                                seen.add(token);
                                result.push(token);
                            }
                        }
                    }

                    return result.slice(0, 20);
                }""",
                {"selectors": self.TAG_INPUT_SELECTORS, "labels": self.TAG_INPUT_LABELS},
            )
        except Exception:
            return []
        return [str(value).strip() for value in (values or []) if str(value).strip()]

    def _read_selected_tag_inline_tokens(self, page) -> List[str]:
        tag_container = self._find_tag_container(page)
        if tag_container is None:
            return []
        try:
            values = tag_container.evaluate(
                """(container, payload) => {
                    const normalize = (text) => (text || '').replace(/\\s+/g, ' ').trim();
                    const selectors = payload.selectors || [];
                    const stripDecorations = (text) =>
                        normalize(text)
                            .replace(/^#+/, '')
                            .replace(/[×✕✖✗✘✚＋+]+$/g, '')
                            .replace(/^[#＃]\s*/, '')
                            .trim();
                    const addHashTokens = (target, text, seen) => {
                        const normalized = normalize(text);
                        if (!normalized) return;
                        const matches = normalized.match(/#[^\s#]+/g) || [];
                        for (const token of matches) {
                            const cleaned = stripDecorations(token);
                            if (!cleaned || cleaned.length <= 1 || seen.has(cleaned)) continue;
                            seen.add(cleaned);
                            target.push(cleaned);
                        }
                    };
                    const inputEl =
                        selectors.map((selector) => container.querySelector(selector)).find(Boolean) ||
                        container.querySelector('[role="combobox"] input, [role="combobox"] textarea, [role="combobox"] [contenteditable="true"], [role="combobox"]') ||
                        null;
                    if (!inputEl) return [];

                    const inputRect = inputEl.getBoundingClientRect();
                    const roots = [];
                    const pushRoot = (el) => {
                        if (!el || !el.isConnected || roots.includes(el)) return;
                        roots.push(el);
                    };
                    pushRoot(inputEl.closest('[role="combobox"]'));
                    pushRoot(inputEl.parentElement);
                    pushRoot(inputEl.closest('div'));

                    const result = [];
                    const seen = new Set();
                    for (const root of roots) {
                        if (!root) continue;
                        const rootRect = root.getBoundingClientRect();
                        if (!rootRect.width || !rootRect.height) continue;
                        if (rootRect.top > inputRect.bottom + 48) continue;
                        if (rootRect.bottom < inputRect.top - 24) continue;

                        addHashTokens(result, root.textContent || '', seen);
                        addHashTokens(result, root.getAttribute('aria-label') || '', seen);
                        addHashTokens(result, root.getAttribute('title') || '', seen);

                        const inlineNodes = Array.from(root.querySelectorAll('button, [role="button"], a, [role="link"], span, div, li'));
                        for (const el of inlineNodes) {
                            if (!el || !el.isConnected) continue;
                            const rect = el.getBoundingClientRect();
                            if (!rect.width || !rect.height) continue;
                            if (rect.top > inputRect.bottom + 24) continue;
                            if (rect.bottom < inputRect.top - 24) continue;
                            addHashTokens(result, el.textContent || '', seen);
                            addHashTokens(result, el.getAttribute('aria-label') || '', seen);
                            addHashTokens(result, el.getAttribute('title') || '', seen);
                        }
                    }

                    return result.slice(0, 20);
                }""",
                {"selectors": self.TAG_INPUT_SELECTORS},
            )
        except Exception:
            return []
        return [str(value).strip() for value in (values or []) if str(value).strip()]

    def _has_selected_tag(self, page, tag: str) -> bool:
        normalized_tag = self._normalize_tag_text(tag)
        if not normalized_tag:
            return False

        candidates = self._read_selected_tag_chips(page)
        inline_candidates = self._read_selected_tag_inline_tokens(page)
        for value in [*candidates, *inline_candidates]:
            normalized_value = self._normalize_tag_text(value)
            if not normalized_value:
                continue
            if normalized_value == normalized_tag:
                return True
            if normalized_value.startswith(normalized_tag):
                next_char = normalized_value[len(normalized_tag):len(normalized_tag) + 1]
                if not next_char or next_char in {" ", "\n", "\t", "/", "(", "（", "[", "【", "-", "－", "—", "・", ":", "：", ",", "，", ".", "。", "×", "✕", "✖"}:
                    return True
            if normalized_tag.startswith(normalized_value):
                return True
        return False

    def _wait_for_tag_commit(
        self,
        page,
        tag: str,
        current_count: Optional[int],
        tag_present_before: bool,
        timeout_ms: int = 2200,
    ) -> tuple[bool, Optional[int]]:
        deadline = time.time() + (timeout_ms / 1000)
        while time.time() < deadline:
            updated_count = self._read_tag_count(page)
            if current_count is not None and updated_count is not None and updated_count > current_count:
                return True, updated_count
            if not tag_present_before and self._has_selected_tag(page, tag):
                return True, updated_count
            page.wait_for_timeout(120)

        updated_count = self._read_tag_count(page)
        if current_count is not None and updated_count is not None and updated_count > current_count:
            return True, updated_count
        if not tag_present_before and self._has_selected_tag(page, tag):
            return True, updated_count
        if current_count is None and updated_count is not None:
            return True, updated_count
        return False, updated_count

    def _get_active_autocomplete_root(self, page):
        try:
            details = page.evaluate(
                """() => {
                    const el = document.activeElement;
                    if (!el) return null;
                    const controls = el.getAttribute('aria-controls') || '';
                    if (!controls) return null;
                    return { controls };
                }"""
            )
        except Exception:
            return None

        if not details:
            return None
        controls = str(details.get("controls") or "").strip()
        if not controls:
            return None

        root = page.locator(f"#{controls}")
        if self._count(root) <= 0:
            return None
        return root.first

    def _find_visible_tag_autocomplete(self, page):
        roots = []
        active_root = self._get_active_autocomplete_root(page)
        if active_root is not None:
            roots.append(active_root)
        roots.append(page)

        for root in roots:
            for selector in self.TAG_AUTOCOMPLETE_SELECTORS:
                locator = root.locator(selector)
                count = min(self._count(locator), 12)
                for index in range(count):
                    item = locator.nth(index)
                    try:
                        if item.is_visible():
                            return item
                    except Exception:
                        continue
        return None

    def _wait_for_tag_autocomplete(self, page, timeout_ms: int = 800) -> bool:
        deadline = time.time() + (timeout_ms / 1000)
        while time.time() < deadline:
            if self._find_visible_tag_autocomplete(page) is not None:
                return True
            page.wait_for_timeout(80)
        return self._find_visible_tag_autocomplete(page) is not None

    def _normalize_visible_text(self, value: str) -> str:
        return re.sub(r"\s+", " ", str(value or "")).strip()

    def _matches_tag_candidate_text(self, text: str, candidates: Iterable[str], *, require_hash: bool = False) -> bool:
        normalized = self._normalize_visible_text(text)
        if not normalized:
            return False
        if require_hash and not normalized.startswith("#"):
            return False

        for candidate in candidates:
            wanted = self._normalize_visible_text(candidate)
            if not wanted:
                continue
            if normalized == wanted:
                return True
            if normalized.startswith(wanted):
                next_char = normalized[len(wanted):len(wanted) + 1]
                if not next_char or next_char in {" ", "\t", "\n", "/", "(", "（", "[", "【", "-", "－", "—", "・", ":", "：", ",", "，", ".", "。"}:
                    return True
        return False

    def _click_matching_text_candidate(self, root, candidates: List[str], *, require_hash: bool = False) -> Optional[str]:
        locator = root.locator("a, button, [role='option'], [role='button'], [role='link'], li, span, div")
        count = min(self._count(locator), 80)
        for index in range(count):
            item = locator.nth(index)
            try:
                if not item.is_visible():
                    continue
                text = str(item.evaluate("(el) => (el.textContent || '').replace(/\\s+/g, ' ').trim()") or "")
            except Exception:
                continue
            if not self._matches_tag_candidate_text(text, candidates, require_hash=require_hash):
                continue
            if self._click_locator_or_interactive_ancestor(item):
                return text
        return None

    def _click_matching_tag_autocomplete(self, page, tag: str) -> bool:
        candidates = [f"#{tag}", tag]
        roots = []
        active_root = self._get_active_autocomplete_root(page)
        if active_root is not None:
            roots.append(("active", active_root))
        roots.append(("page", page))

        for root_name, root in roots:
            for selector in self.TAG_AUTOCOMPLETE_SELECTORS:
                locator = root.locator(selector)
                count = min(self._count(locator), 12)
                for index in range(count):
                    item = locator.nth(index)
                    try:
                        if not item.is_visible():
                            continue
                        text = str(item.evaluate("(el) => (el.textContent || '').replace(/\\s+/g, ' ').trim()") or "")
                    except Exception:
                        continue
                    if not text:
                        continue
                    if not any(text == candidate or text.startswith(candidate + " ") or text.startswith(candidate + "\n") for candidate in candidates):
                        continue
                    if self._click_locator_or_interactive_ancestor(item):
                        self._log(f"[Pixiv] Clicked autocomplete option from {root_name}: {text}")
                        return True
        return False

    def _click_locator_or_interactive_ancestor(self, locator) -> bool:
        if locator is None or self._count(locator) <= 0:
            return False

        target = locator.first
        try:
            interactive = target.locator(
                "xpath=ancestor-or-self::*[self::button or self::a or @role='option' or @role='button' or @role='link' or @tabindex][1]"
            )
            if self._count(interactive) > 0:
                target = interactive.first
        except Exception:
            pass

        for kwargs in ({"force": True}, {}):
            try:
                target.click(**kwargs)
                return True
            except Exception:
                continue
        return False

    def _click_exact_tag_text_via_dom(self, root, candidates: List[str], *, require_hash: bool = False) -> Optional[str]:
        try:
            clicked = root.evaluate(
                """(node, payload) => {
                        const normalize = (text) => (text || '').replace(/\\s+/g, ' ').trim();
                        const wanted = (payload.values || []).map(normalize).filter(Boolean);
                        const requireHash = !!payload.requireHash;
                        if (!wanted.length) return null;

                        const isEditable = (element) =>
                            !!element.closest('input, textarea, [contenteditable="true"], [role="textbox"], [role="searchbox"]');

                        const matchesWanted = (text) => {
                            if (!text) return false;
                            if (requireHash && !text.startsWith('#')) return false;
                            return wanted.some((value) => {
                                if (text === value) return true;
                                if (!text.startsWith(value)) return false;
                                const nextChar = text.slice(value.length, value.length + 1);
                                return !nextChar || /[\\s\\/\\(（\\[【\\-－—・:：,，.。]/.test(nextChar);
                            });
                        };

                        const interactiveSelector = 'a, button, [role="option"], [role="button"], [role="link"], li, span, div';
                        const elements = Array.from(node.querySelectorAll(interactiveSelector));

                        const tryClick = (element) => {
                            const target =
                                element.closest('button, a, [role="option"], [role="button"], [role="link"], [tabindex]') || element;
                            try {
                                target.scrollIntoView({ block: 'nearest', inline: 'nearest' });
                                target.dispatchEvent(new MouseEvent('mousedown', { bubbles: true }));
                                target.dispatchEvent(new MouseEvent('mouseup', { bubbles: true }));
                                target.click();
                                return normalize(target.textContent || element.textContent || '');
                            } catch (err) {
                                return null;
                            }
                        };

                        for (const element of elements) {
                            if (isEditable(element)) continue;
                            const text = normalize(element.textContent);
                            if (!text) continue;
                            if (!matchesWanted(text)) continue;
                            const clickedText = tryClick(element);
                            if (clickedText) {
                                return clickedText;
                            }
                        }
                        return null;
                    }""",
                    {"values": candidates, "requireHash": require_hash},
                )
            return str(clicked).strip() if clicked else None
        except Exception:
            return None

    def _describe_active_element(self, page) -> str:
        try:
            details = page.evaluate(
                """() => {
                    const el = document.activeElement;
                    if (!el) return null;
                    const text = (el.value || el.textContent || '').replace(/\\s+/g, ' ').trim();
                    return {
                        tag: (el.tagName || '').toLowerCase(),
                        type: el.getAttribute('type') || '',
                        role: el.getAttribute('role') || '',
                        placeholder: el.getAttribute('placeholder') || '',
                        ariaControls: el.getAttribute('aria-controls') || '',
                        ariaExpanded: el.getAttribute('aria-expanded') || '',
                        id: el.id || '',
                        name: el.getAttribute('name') || '',
                        className: typeof el.className === 'string' ? el.className : '',
                        text: text.slice(0, 80),
                    };
                }"""
            )
        except Exception:
            return "unknown"

        if not details:
            return "none"

        summary = ", ".join(
            f"{key}={value}"
            for key, value in details.items()
            if value
        )
        return summary or "unknown"

    def _confirm_after_suggestion_click(
        self,
        page,
        tag: str,
        current_count: Optional[int],
        source: str,
        tag_present_before: bool,
    ) -> tuple[bool, Optional[int]]:
        committed, updated_count = self._wait_for_tag_commit(
            page,
            tag,
            current_count,
            tag_present_before,
            timeout_ms=800,
        )
        if committed:
            return True, updated_count

        self._log(f"[Pixiv] Suggestion click from {source} needs explicit Enter: {tag}")
        page.keyboard.press("Enter")
        committed, updated_count = self._wait_for_tag_commit(
            page,
            tag,
            current_count,
            tag_present_before,
            timeout_ms=1200,
        )
        if committed:
            return True, updated_count

        locator = self._find_tag_input(page)
        if locator is not None:
            try:
                locator.click()
                locator.evaluate("(el) => el.focus()")
            except Exception:
                pass

            self._log(f"[Pixiv] Suggestion click from {source} needs refocus Enter: {tag}")
            page.keyboard.press("Enter")
            committed, updated_count = self._wait_for_tag_commit(
                page,
                tag,
                current_count,
                tag_present_before,
                timeout_ms=1200,
            )
            if committed:
                return True, updated_count

            self._log(f"[Pixiv] Suggestion click from {source} needs refocus Tab: {tag}")
            page.keyboard.press("Tab")
            committed, updated_count = self._wait_for_tag_commit(
                page,
                tag,
                current_count,
                tag_present_before,
                timeout_ms=1200,
            )
            if committed:
                return True, updated_count

        self._log_tag_state(page, f"{source} confirm fallback failure", tag)
        return False, updated_count

    def _click_matching_tag_suggestion(self, page, tag: str, current_count: Optional[int]) -> Optional[int]:
        suggestion_container = self._find_tag_suggestion_container(page)
        hashed_candidate = f"#{tag}"
        roots = []
        if suggestion_container is not None:
            roots.append(("suggestion", suggestion_container))
        if not roots:
            self._log(f"[Pixiv] No suggestion container found for: {tag}")
            return None

        for root_name, root in roots:
            clicked_text = self._click_matching_text_candidate(
                root,
                [hashed_candidate],
                require_hash=True,
            )
            if clicked_text:
                self._log(f"[Pixiv] Clicked visible suggestion candidate from {root_name}: {clicked_text}")
                committed, updated_count = self._confirm_after_suggestion_click(
                    page,
                    tag,
                    current_count,
                    f"{root_name}/visible-hash",
                    tag_present_before=False,
                )
                if committed:
                    return updated_count
                self._log(f"[Pixiv] Visible suggestion click from {root_name} did not confirm: {tag}")

            clicked_text = self._click_matching_text_candidate(
                root,
                [hashed_candidate, tag],
                require_hash=False,
            )
            if clicked_text:
                self._log(f"[Pixiv] Clicked loose visible suggestion candidate from {root_name}: {clicked_text}")
                committed, updated_count = self._confirm_after_suggestion_click(
                    page,
                    tag,
                    current_count,
                    f"{root_name}/visible-loose",
                    tag_present_before=False,
                )
                if committed:
                    return updated_count
                self._log(f"[Pixiv] Loose visible suggestion click from {root_name} did not confirm: {tag}")

            clicked_text = self._click_exact_tag_text_via_dom(
                root,
                [hashed_candidate],
                require_hash=True,
            )
            if clicked_text:
                self._log(f"[Pixiv] Clicked DOM suggestion fallback from {root_name}: {clicked_text}")
                committed, updated_count = self._confirm_after_suggestion_click(
                    page,
                    tag,
                    current_count,
                    f"{root_name}/dom-hash",
                    tag_present_before=False,
                )
                if committed:
                    return updated_count
                self._log(f"[Pixiv] DOM suggestion fallback from {root_name} did not confirm: {tag}")

            clicked_text = self._click_exact_tag_text_via_dom(
                root,
                [hashed_candidate, tag],
                require_hash=False,
            )
            if clicked_text:
                self._log(f"[Pixiv] Clicked loose DOM suggestion fallback from {root_name}: {clicked_text}")
                committed, updated_count = self._confirm_after_suggestion_click(
                    page,
                    tag,
                    current_count,
                    f"{root_name}/dom-loose",
                    tag_present_before=False,
                )
                if committed:
                    return updated_count
                self._log(f"[Pixiv] Loose DOM suggestion fallback from {root_name} did not confirm: {tag}")
        self._log(f"[Pixiv] Suggestion container did not yield a confirmed match for: {tag}")
        return None

    def _is_login_required(self, page) -> bool:
        if self._is_upload_ready(page):
            return False

        current_url = page.url.lower()
        if "accounts.pixiv.net" in current_url or "/login" in current_url:
            return True

        login_form = self._first_locator(page, selectors=self.LOGIN_REQUIRED_SELECTORS)
        if login_form is not None and self._has_any_text(page, self.LOGIN_TEXTS):
            return True

        return False

    def _wait_for_login(self, page, timeout_seconds: int = 300) -> None:
        page.goto(self.UPLOAD_URL, wait_until="domcontentloaded")

        if not self._is_login_required(page):
            return

        self._log("[Pixiv] Pixiv login is required for this browser profile.")
        if not self.settings.get("auto_submit", True):
            self._log("[Pixiv] Please finish logging in inside the browser, then click Open Pixiv Draft again.")
            raise RuntimeError("Pixiv login is required. Please finish logging in, then click Open Pixiv Draft again.")

        self._log("[Pixiv] Please finish logging in inside the browser. The uploader will continue after login.")
        deadline = time.time() + timeout_seconds
        while time.time() < deadline:
            page.wait_for_timeout(1000)
            if not self._is_login_required(page):
                return

        raise RuntimeError("Waiting for Pixiv login timed out.")

    def _is_upload_ready(self, page) -> bool:
        return self._first_locator(page, selectors=self.UPLOAD_READY_SELECTORS) is not None

    def _wait_for_upload_ready(self, page, timeout_seconds: int = 60) -> None:
        deadline = time.time() + timeout_seconds
        while time.time() < deadline:
            if self._is_login_required(page):
                self._wait_for_login(page, timeout_seconds=max(10, int(deadline - time.time())))
                page.goto(self.UPLOAD_URL, wait_until="domcontentloaded")
            if self._is_upload_ready(page):
                return
            page.wait_for_timeout(1000)
        raise RuntimeError(f"Pixiv upload page did not become ready in time (current page: {page.url})")

    def _open_upload_page(self):
        page = self._ensure_page()
        self._wait_for_login(page)
        page.goto(self.UPLOAD_URL, wait_until="domcontentloaded")
        self._wait_for_upload_ready(page)
        return page

    def _fill_text(self, page, value: str, *, selectors: Iterable[str] = (), labels: Iterable[str] = (), texts: Iterable[str] = ()) -> bool:
        if value is None:
            return False

        locator = self._first_fillable_locator(page, selectors=selectors, labels=labels, texts=texts)
        if locator is None:
            return False

        locator.click()
        locator.fill("")
        locator.type(value, delay=10)
        return True

    def _click_text(self, page, candidates: Iterable[str]) -> bool:
        for text in candidates:
            for getter in (
                lambda value: page.get_by_role("button", name=value, exact=False),
                lambda value: page.get_by_role("link", name=value, exact=False),
                lambda value: page.get_by_role("radio", name=value, exact=False),
                lambda value: page.get_by_role("checkbox", name=value, exact=False),
                lambda value: page.get_by_text(value, exact=False),
            ):
                locator = getter(text)
                if self._count(locator) > 0:
                    locator.first.click()
                    return True
        return False

    def _click_choice_in_group(self, group, candidates: Iterable[str]) -> bool:
        for text in candidates:
            for getter in (
                lambda value: group.get_by_role("radio", name=value, exact=False),
                lambda value: group.get_by_role("checkbox", name=value, exact=False),
                lambda value: group.get_by_label(value, exact=False),
                lambda value: group.get_by_text(value, exact=False),
            ):
                locator = getter(text)
                if self._count(locator) > 0:
                    try:
                        locator.first.click()
                    except Exception:
                        try:
                            locator.first.check(force=True)
                        except Exception:
                            return False
                    return True
        return False

    def _set_toggle(self, page, enabled: bool, labels: Iterable[str]) -> bool:
        locator = self._first_locator(page, labels=labels, texts=labels)
        if locator is None:
            return False

        input_locator = locator
        try:
            if locator.get_attribute("type") != "checkbox":
                checkbox = locator.locator("input[type='checkbox']")
                if self._count(checkbox) > 0:
                    input_locator = checkbox.first
        except Exception:
            pass

        try:
            if enabled:
                input_locator.check(force=True)
            else:
                input_locator.uncheck(force=True)
        except Exception:
            locator.click()
        return True

    def _add_tags(self, page, tags: List[str]) -> bool:
        tags = [str(tag).strip() for tag in tags if str(tag).strip()][:10]
        if not tags:
            return True

        tag_container = self._find_tag_container(page)
        selectors = [
            "[role='combobox'] input:not([type='checkbox'])",
            "[role='combobox'] textarea",
            "[role='combobox'] [contenteditable='true']",
            "input[name*='tag' i]:not([type='checkbox'])",
            "input[id*='tag' i]:not([type='checkbox'])",
            "input[placeholder*='tag' i]",
            "input[placeholder*='Tag' i]",
            "input[placeholder*='タグ']",
            "input[placeholder*='标签']",
            "input[aria-label*='tag' i]",
            "input[aria-label*='タグ']",
            "input[aria-label*='标签']",
            "[role='combobox']",
        ]
        labels = ["Tags", "Tag", "タグ", "标签"]
        search_root = tag_container or page
        current_count = self._read_tag_count(page)
        self._log(f"[Pixiv] Preparing to add {len(tags)} tag(s).")

        for tag in tags:
            tag_present_before = self._has_selected_tag(page, tag)
            if tag_present_before:
                refreshed_count = self._read_tag_count(page)
                if refreshed_count is not None:
                    current_count = refreshed_count
                self._log(f"[Pixiv] Tag already present, skipping duplicate add: {tag}")
                continue

            locator = self._first_fillable_locator(
                search_root,
                selectors=selectors,
                labels=labels,
                texts=(),
            )
            if locator is None:
                raise RuntimeError(f"未找到 Pixiv 标签输入框，无法填写标签：{tag}")

            committed = False
            autocomplete_ready = False
            for strategy in ("Enter", "ArrowDownEnter", "RefocusEnter"):
                locator = self._first_fillable_locator(
                    search_root,
                    selectors=selectors,
                    labels=labels,
                    texts=(),
                )
                if locator is None:
                    break

                locator.click()
                try:
                    locator.evaluate("(el) => el.focus()")
                except Exception:
                    pass
                cleared_input = self._clear_fillable_locator_text(locator)
                if cleared_input:
                    self._log(f"[Pixiv] Cleared pending text before {strategy}: {tag}")

                locator.type(tag, delay=22)

                autocomplete_ready = self._wait_for_tag_autocomplete(page, timeout_ms=1200)
                if autocomplete_ready:
                    self._log(f"[Pixiv] Autocomplete ready for: {tag}")
                else:
                    page.wait_for_timeout(360)

                if strategy == "ArrowDownEnter":
                    try:
                        locator.press("ArrowDown")
                        page.wait_for_timeout(120)
                    except Exception:
                        pass
                elif strategy == "RefocusEnter":
                    try:
                        locator.click()
                        locator.evaluate("(el) => el.focus()")
                    except Exception:
                        pass

                self._log(f"[Pixiv] Active element before {strategy}: {self._describe_active_element(page)}")
                page.keyboard.press("Enter")
                committed_now, updated_count = self._wait_for_tag_commit(
                    page,
                    tag,
                    current_count,
                    tag_present_before,
                )
                if committed_now:
                    refreshed_count = self._read_tag_count(page)
                    if refreshed_count is not None:
                        current_count = refreshed_count
                    elif updated_count is not None:
                        current_count = updated_count
                    committed = True
                    suffix = " after refocus" if strategy == "RefocusEnter" else ""
                    if current_count is not None:
                        self._log(f"[Pixiv] Added tag{suffix}: {tag} ({current_count}/10)")
                    else:
                        self._log(f"[Pixiv] Added tag{suffix} without count feedback: {tag}")
                    break
                self._log(f"[Pixiv] Tag strategy {strategy} did not confirm: {tag}")
                self._log_tag_state(page, strategy, tag)

            if not committed and autocomplete_ready:
                if self._click_matching_tag_autocomplete(page, tag):
                    committed_now, updated_count = self._confirm_after_suggestion_click(
                        page,
                        tag,
                        current_count,
                        "autocomplete",
                        tag_present_before,
                    )
                    if committed_now:
                        refreshed_count = self._read_tag_count(page)
                        if refreshed_count is not None:
                            current_count = refreshed_count
                        elif updated_count is not None:
                            current_count = updated_count
                        committed = True
                        if current_count is not None:
                            self._log(f"[Pixiv] Added tag via autocomplete click: {tag} ({current_count}/10)")
                        else:
                            self._log(f"[Pixiv] Added tag via autocomplete click without count feedback: {tag}")
                    else:
                        self._log(f"[Pixiv] Autocomplete click did not confirm: {tag}")
                else:
                    self._log(f"[Pixiv] Autocomplete visible but no matching option clicked: {tag}")

            if not committed:
                updated_count = self._click_matching_tag_suggestion(page, tag, current_count)
                if current_count is not None and updated_count is not None and updated_count > current_count:
                    current_count = updated_count
                    committed = True
                    self._log(f"[Pixiv] Added tag via suggestion: {tag} ({current_count}/10)")
                elif current_count is None and updated_count is not None:
                    current_count = updated_count
                    committed = True
                    self._log(f"[Pixiv] Added tag via suggestion without count feedback: {tag}")

            if not committed:
                raise RuntimeError(f"Pixiv 未确认标签：{tag}")
        return True

    def _set_ai_generated_choice(self, page, enabled: bool) -> bool:
        desired = ["Yes", "是", "あり"] if enabled else ["No", "否", "なし"]
        group = self._find_group_container(page, ["AI生成作品", "AI-generated work", "AI生成"])
        if group is not None and self._click_choice_in_group(group, desired):
            return True
        return self._click_text(page, desired)

    def _set_choice(self, page, value: str, mapping: dict, *, group_labels: Iterable[str] = ()) -> bool:
        if value not in mapping:
            return False
        group = self._find_group_container(page, group_labels)
        if group is not None and self._click_choice_in_group(group, mapping[value]):
            return True
        return self._click_text(page, mapping[value])

    def _set_sexual_depiction_choice(self, page, enabled: bool) -> bool:
        return self._set_choice(
            page,
            "yes" if enabled else "no",
            {
                "yes": [
                    "有",
                    "Yes",
                    "あり",
                    "性描写あり",
                    "性的表現あり",
                    "Slightly sexual content",
                ],
                "no": [
                    "无",
                    "No",
                    "なし",
                    "性描写なし",
                    "性的表現なし",
                    "No sexual depiction",
                ],
            },
            group_labels=["性描写", "Sexual depiction", "Slightly sexual content", "性的表現"],
        )

    def upload_image(
        self,
        image_path: Path,
        *,
        title: str,
        caption: str,
        tags: List[str],
        visibility: str,
        age_restriction: str,
        sexual_depiction: bool,
        ai_generated: bool,
        auto_submit: bool,
        lock_tags: bool = False,
    ) -> None:
        image_path = Path(image_path)
        page = self._open_upload_page()
        self._log(f"[Pixiv] 准备上传: {image_path.name}")

        file_input = self._first_locator(page, selectors=["input[type='file']"])
        if file_input is None:
            raise RuntimeError("未找到 Pixiv 投稿页的文件输入框")
        file_input.set_input_files(str(image_path))
        page.wait_for_timeout(1500)

        self._fill_text(
            page,
            title,
            selectors=[
                "input[placeholder*='title' i]",
                "input[placeholder*='Title' i]",
                "input[placeholder*='タイトル']",
                "textarea[placeholder*='title' i]",
                "textarea[placeholder*='タイトル']",
            ],
            labels=["Title", "タイトル", "标题"],
        )
        self._fill_text(
            page,
            caption,
            selectors=[
                "textarea[placeholder*='caption' i]",
                "textarea[placeholder*='description' i]",
                "textarea[placeholder*='Caption' i]",
                "textarea[placeholder*='説明']",
                "textarea[placeholder*='描述']",
            ],
            labels=["Caption", "Description", "説明", "描述"],
        )
        self._add_tags(page, tags)
        self._set_toggle(
            page,
            lock_tags,
            [
                "Don't allow other users to edit tags",
                "不允许其他用户编辑标签",
                "タグ編集を許可しない",
                "タグ編集を他のユーザーに許可しない",
            ],
        )

        self._set_ai_generated_choice(page, ai_generated)

        self._set_choice(
            page,
            age_restriction,
            {
                "all": ["All ages", "全年龄", "全年龄向け"],
                "R-18": ["R-18"],
                "R-18G": ["R-18G"],
            },
            group_labels=["年龄限制", "Age restriction", "年齢制限"],
        )
        self._set_choice(
            page,
            visibility,
            {
                "public": ["Public", "公开"],
                "mypixiv": ["My pixiv only", "MyPixiv", "My pixiv"],
                "private": ["Private", "非公开"],
            },
            group_labels=["公开范围", "Visibility", "公開範囲"],
        )
        sexual_choice_applied = self._set_sexual_depiction_choice(page, sexual_depiction)
        if not sexual_choice_applied:
            message = "[Pixiv] 未能定位性描写选项，请手动确认该字段。"
            if auto_submit:
                raise RuntimeError(message)
            self._log(message)

        if auto_submit:
            if not self._click_text(page, ["Post", "Submit", "投稿する", "公开する", "投稿"]):
                raise RuntimeError("未找到 Pixiv 投稿按钮")
            page.wait_for_timeout(3000)
            self._log(f"[Pixiv] 已尝试投稿: {image_path.name}")
        else:
            self._log(f"[Pixiv] 已填好投稿表单，请检查后手动投稿: {image_path.name}")


def import_pixiv_browser_auth(settings: dict, log_fn: Optional[Callable[[str], None]] = None) -> dict:
    log = log_fn or (lambda message: None)
    browser_channel = str(settings.get("browser_channel") or "msedge").strip().lower()
    user_data_dir = _resolve_browser_user_data_dir(browser_channel)
    browser_name = _browser_label(browser_channel)

    if not user_data_dir.exists():
        raise RuntimeError(f"找不到 {browser_name} 的用户资料目录：{user_data_dir}")

    profiles = _browser_profile_candidates(user_data_dir)
    if not profiles:
        raise RuntimeError(f"在 {browser_name} 的用户资料目录里没有找到可读取的配置")

    if importlib.util.find_spec("playwright") is None:
        log("[Pixiv] 正在安装 Playwright，用于从浏览器静默导入登录态...")
        subprocess.check_call([sys.executable, "-m", "pip", "install", "-q", "playwright"])

    from playwright.sync_api import sync_playwright

    errors: List[str] = []
    with sync_playwright() as playwright:
        for profile_name in profiles:
            cookie_sources = [path for path in _cookie_db_candidates(user_data_dir, profile_name) if path.exists()]
            if not cookie_sources:
                continue

            log(f"[Pixiv] 正在尝试读取 {browser_name} 配置：{profile_name}")
            with tempfile.TemporaryDirectory(prefix="pixiv_auth_import_") as temp_dir_name:
                temp_root = Path(temp_dir_name)
                try:
                    _copy_browser_auth_files(user_data_dir, profile_name, temp_root)
                except Exception as exc:
                    errors.append(f"{profile_name}: 无法复制浏览器配置 ({exc})")
                    continue

                launch_kwargs = {
                    "user_data_dir": str(temp_root),
                    "headless": True,
                }
                if browser_channel != "chromium":
                    launch_kwargs["channel"] = browser_channel
                if profile_name != "Default":
                    launch_kwargs["args"] = [f"--profile-directory={profile_name}"]

                context = None
                try:
                    context = playwright.chromium.launch_persistent_context(**launch_kwargs)
                    page = context.pages[0] if context.pages else context.new_page()
                    page.goto(_BrowserPixivUploader.UPLOAD_URL, wait_until="domcontentloaded", timeout=45000)
                    snapshot = _read_pixiv_auth_from_page(context, page)
                    if snapshot["loginRequired"]:
                        errors.append(f"{profile_name}: Pixiv 登录态已失效")
                        continue

                    cookie_header = snapshot["cookie"]
                    if not cookie_header:
                        errors.append(f"{profile_name}: 没有读取到 Pixiv 登录 Cookie")
                        continue

                    csrf_token = snapshot["csrfToken"]
                    if csrf_token:
                        log(f"[Pixiv] 已从 {browser_name} 配置 {profile_name} 导入 Pixiv 登录态。")
                    else:
                        log(f"[Pixiv] 已从 {browser_name} 配置 {profile_name} 导入 Pixiv Cookie，但还没有拿到 CSRF Token。")
                    return _build_pixiv_import_result(
                        browser_channel=browser_channel,
                        browser_name=browser_name,
                        profile_name=profile_name,
                        cookie_header=cookie_header,
                        csrf_token=csrf_token,
                        source="browser-profile",
                    )
                except Exception as exc:
                    errors.append(f"{profile_name}: {exc}")
                finally:
                    if context is not None:
                        try:
                            context.close()
                        except Exception:
                            pass

        if _should_fallback_to_interactive_browser_auth(errors):
            return _interactive_pixiv_browser_auth(playwright, browser_channel, browser_name, log)

    detail = "；".join(errors[-3:]) if errors else "没有找到可用的 Pixiv 登录态"
    raise RuntimeError(f"无法从 {browser_name} 导入 Pixiv 登录态：{detail}")


class _DirectPixivUploader(_BasePixivUploader):
    CREATE_URL = "https://www.pixiv.net/ajax/work/create/illustration"
    PROGRESS_URL = "https://www.pixiv.net/ajax/work/create/illustration/progress"
    UPLOAD_URL = "https://www.pixiv.net/upload.php"
    USER_AGENT = (
        "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
        "AppleWebKit/537.36 (KHTML, like Gecko) Chrome/135.0.0.0 Safari/537.36"
    )

    def __init__(self, settings: dict, log_fn: Optional[Callable[[str], None]] = None):
        super().__init__(settings, log_fn=log_fn)
        self.session = requests.Session()
        self._refresh_session_headers()

    def _cookie(self) -> str:
        return str(self.settings.get("cookie") or "").strip()

    def _csrf_token(self) -> str:
        return str(self.settings.get("csrf_token") or "").strip()

    def _refresh_session_headers(self) -> None:
        headers = {
            "accept": "application/json, text/plain, */*",
            "origin": "https://www.pixiv.net",
            "referer": self.UPLOAD_URL,
            "user-agent": self.USER_AGENT,
            "cookie": self._cookie(),
        }
        csrf_token = self._csrf_token()
        if csrf_token:
            headers["x-csrf-token"] = csrf_token
        self.session.headers.clear()
        self.session.headers.update(headers)

    def ensure_ready(self, *, require_csrf: bool = True) -> bool:
        if not self._cookie():
            raise RuntimeError("Pixiv 直传模式缺少 Cookie")
        if require_csrf and not self._csrf_token():
            raise RuntimeError("Pixiv 直传模式缺少 CSRF Token")
        return True

    def close(self) -> None:
        self.session.close()

    def _restrict_value(self, visibility: str) -> str:
        if visibility == "private":
            return "private"
        if visibility == "mypixiv":
            return "mypixiv"
        return "public"

    def _x_restrict_value(self, age_restriction: str) -> str:
        mapping = {
            "all": "general",
            "R-18": "r18",
            "R-18G": "r18g",
        }
        return mapping.get(age_restriction, "general")

    def _guess_mime_type(self, image_path: Path) -> str:
        mime_type, _ = mimetypes.guess_type(str(image_path))
        return mime_type or "application/octet-stream"

    def _build_files(self, image_path: Path):
        file_key = uuid.uuid4().hex
        mime_type = self._guess_mime_type(image_path)
        file_item = (
            "files[]",
            (image_path.name, image_path.read_bytes(), mime_type),
        )
        return file_key, [file_item]

    def _build_payload(
        self,
        *,
        title: str,
        caption: str,
        tags: List[str],
        visibility: str,
        age_restriction: str,
        sexual_depiction: bool,
        ai_generated: bool,
        lock_tags: bool,
        file_key: str,
    ) -> List[tuple]:
        normalized_tags = [str(tag).strip() for tag in tags if str(tag).strip()][:10]
        payload = [
            ("title", title),
            ("caption", caption or ""),
            ("allowTagEdit", "false" if lock_tags else "true"),
            ("restrict", self._restrict_value(visibility)),
            ("xRestrict", self._x_restrict_value(age_restriction)),
            ("original", "true"),
            ("allowComment", "true"),
            ("responseAutoAccept", "false"),
            ("attributes[bl]", "false"),
            ("attributes[furry]", "false"),
            ("attributes[lo]", "false"),
            ("attributes[yuri]", "false"),
            ("ratings[antisocial]", "false"),
            ("ratings[drug]", "false"),
            ("ratings[religion]", "false"),
            ("ratings[thoughts]", "false"),
            ("ratings[violent]", "false"),
            ("sexual", "true" if sexual_depiction else "false"),
            ("imageOrder[0][fileKey]", file_key),
            ("imageOrder[0][type]", "newFile"),
        ]
        if ai_generated:
            payload.append(("aiType", "aiGenerated"))
        for tag in normalized_tags:
            payload.append(("tags[]", tag))
        return payload

    def _extract_error_message(self, response: requests.Response) -> str:
        try:
            payload = response.json()
        except Exception:
            return response.text.strip() or f"HTTP {response.status_code}"
        if isinstance(payload, dict):
            if payload.get("message"):
                return str(payload["message"])
            if isinstance(payload.get("body"), dict) and payload["body"].get("message"):
                return str(payload["body"]["message"])
        return response.text.strip() or f"HTTP {response.status_code}"

    def probe(self) -> dict:
        self.ensure_ready(require_csrf=False)
        self._refresh_session_headers()
        response = self.session.get(self.UPLOAD_URL, timeout=30)
        if response.status_code >= 400:
            raise RuntimeError(f"Pixiv 直传检测失败：{self._extract_error_message(response)}")

        final_url = str(response.url or self.UPLOAD_URL)
        html = response.text or ""
        if _is_pixiv_login_html(html, final_url):
            raise RuntimeError("Pixiv 登录态已失效，请重新导入 Cookie")

        csrf_token = _extract_pixiv_csrf_token(html) or self._csrf_token()
        if not csrf_token:
            raise RuntimeError("已访问 Pixiv 投稿页，但没有找到可用的 CSRF Token")

        return {
            "ok": True,
            "url": final_url,
            "csrfToken": csrf_token,
            "message": "Pixiv 直传鉴权可用",
        }

    def _poll_progress(self, convert_key: str, timeout_seconds: int = 180) -> str:
        deadline = time.time() + timeout_seconds
        last_state = ""
        while time.time() < deadline:
            response = self.session.get(
                self.PROGRESS_URL,
                params={"convertKey": convert_key, "lang": "zh"},
                timeout=30,
            )
            if response.status_code >= 400:
                raise RuntimeError(f"Pixiv 进度查询失败：{self._extract_error_message(response)}")
            payload = response.json()
            body = payload.get("body") or {}
            state = str(body.get("state") or body.get("status") or "").strip()
            if state and state != last_state:
                self._log(f"[Pixiv] 直传状态：{state}")
                last_state = state
            if str(body.get("illustId") or "").strip():
                return str(body["illustId"])
            if state.lower() in {"failure", "failed", "error"}:
                detail = str(body.get("message") or payload.get("message") or "Pixiv 投稿失败")
                raise RuntimeError(detail)
            time.sleep(2)
        raise RuntimeError("等待 Pixiv 直传结果超时")

    def upload_image(
        self,
        image_path: Path,
        *,
        title: str,
        caption: str,
        tags: List[str],
        visibility: str,
        age_restriction: str,
        sexual_depiction: bool,
        ai_generated: bool,
        auto_submit: bool,
        lock_tags: bool = False,
    ) -> None:
        self.ensure_ready()
        image_path = Path(image_path)
        self._log(f"[Pixiv] 直传准备上传: {image_path.name}")

        if not auto_submit:
            self._log("[Pixiv] 直传模式不支持手动停留确认，将按自动投稿执行。")

        file_key, files = self._build_files(image_path)
        payload = self._build_payload(
            title=title,
            caption=caption,
            tags=tags,
            visibility=visibility,
            age_restriction=age_restriction,
            sexual_depiction=sexual_depiction,
            ai_generated=ai_generated,
            lock_tags=lock_tags,
            file_key=file_key,
        )
        response = self.session.post(
            self.CREATE_URL,
            data=payload,
            files=files,
            timeout=120,
        )
        if response.status_code >= 400:
            raise RuntimeError(f"Pixiv 直传失败：{self._extract_error_message(response)}")

        try:
            result = response.json()
        except Exception as exc:
            raise RuntimeError("Pixiv 直传返回了无法解析的响应") from exc

        if result.get("error"):
            message = result.get("message") or "Pixiv 直传失败"
            raise RuntimeError(str(message))

        body = result.get("body") or {}
        convert_key = str(body.get("convertKey") or "").strip()
        illust_id = str(body.get("illustId") or "").strip()
        if not convert_key and not illust_id:
            raise RuntimeError("Pixiv 直传没有返回 convertKey 或 illustId")

        if not illust_id:
            self._log("[Pixiv] 文件已提交，正在等待 Pixiv 转换完成...")
            illust_id = self._poll_progress(convert_key)

        self._log(f"[Pixiv] 直传完成，作品 ID: {illust_id}")


def probe_pixiv_direct_auth(settings: dict, log_fn: Optional[Callable[[str], None]] = None) -> dict:
    uploader = _DirectPixivUploader(settings, log_fn=log_fn)
    try:
        result = uploader.probe()
        uploader._log(f"[Pixiv] {result['message']}: {result['url']}")
        return result
    finally:
        uploader.close()


class PixivUploader:
    def __init__(self, settings: dict, log_fn: Optional[Callable[[str], None]] = None):
        self.settings = settings
        self.log_fn = log_fn or (lambda message: None)
        mode = str(settings.get("upload_mode") or "browser").strip().lower()
        if mode == "direct":
            self._uploader = _DirectPixivUploader(settings, log_fn=self.log_fn)
        else:
            self._uploader = _BrowserPixivUploader(settings, log_fn=self.log_fn)

    def ensure_ready(self) -> bool:
        return self._uploader.ensure_ready()

    def close(self) -> None:
        self._uploader.close()

    def capture_debug_snapshot(self, tag_hint: str = "") -> dict:
        return self._uploader.capture_debug_snapshot(tag_hint=tag_hint)

    def upload_image(
        self,
        image_path: Path,
        *,
        title: str,
        caption: str,
        tags: List[str],
        visibility: str,
        age_restriction: str,
        sexual_depiction: bool,
        ai_generated: bool,
        auto_submit: bool,
        lock_tags: bool = False,
    ) -> None:
        self._uploader.upload_image(
            image_path,
            title=title,
            caption=caption,
            tags=tags,
            visibility=visibility,
            age_restriction=age_restriction,
            sexual_depiction=sexual_depiction,
            ai_generated=ai_generated,
            auto_submit=auto_submit,
            lock_tags=lock_tags,
        )
