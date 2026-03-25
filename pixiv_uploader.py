import importlib.util
import mimetypes
import subprocess
import sys
import time
import uuid
from pathlib import Path
from typing import Callable, Iterable, List, Optional

import requests


PIXIV_BROWSER_CHANNELS = ["msedge", "chrome", "chromium"]
PIXIV_VISIBILITY_OPTIONS = ["public", "mypixiv", "private"]
PIXIV_AGE_OPTIONS = ["all", "R-18", "R-18G"]
PIXIV_UPLOAD_MODE_OPTIONS = [
    {"value": "browser", "label": "浏览器自动填写"},
    {"value": "direct", "label": "Cookie + CSRF 直传"},
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


class _BrowserPixivUploader(_BasePixivUploader):
    """Best-effort Pixiv uploader driven by browser automation."""

    UPLOAD_URL = "https://www.pixiv.net/upload.php"
    LOGIN_TEXTS = ["Login", "Log in", "ログイン", "登录", "登入"]
    UPLOAD_READY_SELECTORS = [
        "input[type='file']",
        "input[placeholder*='title' i]",
        "textarea[placeholder*='caption' i]",
        "textarea[placeholder*='description' i]",
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

    def _has_any_text(self, page, texts: Iterable[str]) -> bool:
        for text in texts:
            locator = page.get_by_text(text, exact=False)
            if self._count(locator) > 0:
                return True
        return False

    def _wait_for_login(self, page, timeout_seconds: int = 300) -> None:
        page.goto(self.UPLOAD_URL, wait_until="domcontentloaded")

        if "login" not in page.url.lower() and not self._has_any_text(page, self.LOGIN_TEXTS):
            return

        self._log("[Pixiv] ?????????????? Pixiv?")
        if not self.settings.get("auto_submit", True):
            self._log("[Pixiv] ???????????????????????? Open Pixiv Draft?")
            raise RuntimeError("Pixiv ???????????????????? Open Pixiv Draft")

        self._log("[Pixiv] ???????????????????????")
        deadline = time.time() + timeout_seconds
        while time.time() < deadline:
            page.wait_for_timeout(1000)
            if "login" not in page.url.lower() and not self._has_any_text(page, self.LOGIN_TEXTS):
                return

        raise RuntimeError("?? Pixiv ????")

    def _is_upload_ready(self, page) -> bool:
        return self._first_locator(page, selectors=self.UPLOAD_READY_SELECTORS) is not None

    def _wait_for_upload_ready(self, page, timeout_seconds: int = 60) -> None:
        deadline = time.time() + timeout_seconds
        while time.time() < deadline:
            if "login" in page.url.lower() or self._has_any_text(page, self.LOGIN_TEXTS):
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

        locator = self._first_locator(page, selectors=selectors, labels=labels, texts=texts)
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

        locator = self._first_locator(
            page,
            selectors=[
                "input[placeholder*='tag' i]",
                "input[placeholder*='Tag' i]",
                "input[placeholder*='タグ']",
                "input[aria-label*='tag' i]",
                "input[aria-label*='タグ']",
            ],
            labels=["Tags", "Tag", "タグ", "标签"],
        )
        if locator is None:
            return False

        for tag in tags:
            locator.click()
            locator.fill("")
            locator.type(tag, delay=10)
            page.keyboard.press("Enter")
            page.wait_for_timeout(120)
        return True

    def _set_choice(self, page, value: str, mapping: dict) -> bool:
        if value not in mapping:
            return False
        return self._click_text(page, mapping[value])

    def upload_image(
        self,
        image_path: Path,
        *,
        title: str,
        caption: str,
        tags: List[str],
        visibility: str,
        age_restriction: str,
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

        self._set_toggle(page, ai_generated, ["AI-generated work", "AI生成作品", "AI生成"])

        self._set_choice(
            page,
            age_restriction,
            {
                "all": ["All ages", "全年龄", "全年龄向け"],
                "R-18": ["R-18"],
                "R-18G": ["R-18G"],
            },
        )
        self._set_choice(
            page,
            visibility,
            {
                "public": ["Public", "公开"],
                "mypixiv": ["My pixiv only", "MyPixiv", "My pixiv"],
                "private": ["Private", "非公开"],
            },
        )

        if auto_submit:
            if not self._click_text(page, ["Post", "Submit", "投稿する", "公开する", "投稿"]):
                raise RuntimeError("未找到 Pixiv 投稿按钮")
            page.wait_for_timeout(3000)
            self._log(f"[Pixiv] 已尝试投稿: {image_path.name}")
        else:
            self._log(f"[Pixiv] 已填好投稿表单，请检查后手动投稿: {image_path.name}")


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
        self.session.headers.update(
            {
                "accept": "application/json, text/plain, */*",
                "origin": "https://www.pixiv.net",
                "referer": self.UPLOAD_URL,
                "user-agent": self.USER_AGENT,
                "x-csrf-token": self._csrf_token(),
                "cookie": self._cookie(),
            }
        )

    def _cookie(self) -> str:
        return str(self.settings.get("cookie") or "").strip()

    def _csrf_token(self) -> str:
        return str(self.settings.get("csrf_token") or "").strip()

    def ensure_ready(self) -> bool:
        if not self._cookie():
            raise RuntimeError("Pixiv 直传模式缺少 Cookie")
        if not self._csrf_token():
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
            ("imageOrder[0][fileKey]", file_key),
            ("imageOrder[0][type]", "newFile"),
        ]
        if age_restriction == "all":
            payload.append(("sexual", "false"))
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

    def upload_image(
        self,
        image_path: Path,
        *,
        title: str,
        caption: str,
        tags: List[str],
        visibility: str,
        age_restriction: str,
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
            ai_generated=ai_generated,
            auto_submit=auto_submit,
            lock_tags=lock_tags,
        )
