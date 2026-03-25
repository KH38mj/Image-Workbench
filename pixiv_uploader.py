import importlib.util
import mimetypes
import re
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

    def _wait_for_tag_count_increment(self, page, current_count: Optional[int], timeout_ms: int = 1200) -> Optional[int]:
        if current_count is None:
            page.wait_for_timeout(min(timeout_ms, 400))
            return self._read_tag_count(page)

        deadline = time.time() + (timeout_ms / 1000)
        while time.time() < deadline:
            updated_count = self._read_tag_count(page)
            if updated_count is not None and updated_count > current_count:
                return updated_count
            page.wait_for_timeout(120)
        return self._read_tag_count(page)

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

    def _click_exact_tag_text_via_dom(self, root, candidates: List[str], *, require_hash: bool = False) -> bool:
        try:
            clicked = bool(
                root.evaluate(
                    """(node, payload) => {
                        const normalize = (text) => (text || '').replace(/\\s+/g, ' ').trim();
                        const wanted = (payload.values || []).map(normalize).filter(Boolean);
                        const requireHash = !!payload.requireHash;
                        if (!wanted.length) return false;

                        const isEditable = (element) =>
                            !!element.closest('input, textarea, [contenteditable="true"], [role="textbox"], [role="searchbox"]');

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
                                return true;
                            } catch (err) {
                                return false;
                            }
                        };

                        for (const element of elements) {
                            if (isEditable(element)) continue;
                            const text = normalize(element.textContent);
                            if (!text) continue;
                            if (requireHash && !text.startsWith('#')) continue;
                            for (const value of wanted) {
                                if (text === value) {
                                    if (tryClick(element)) return true;
                                }
                            }
                        }
                        return false;
                    }""",
                    {"values": candidates, "requireHash": require_hash},
                )
            )
            return clicked
        except Exception:
            return False

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

    def _confirm_after_suggestion_click(self, page, tag: str, current_count: Optional[int], source: str) -> Optional[int]:
        updated_count = self._wait_for_tag_count_increment(page, current_count, timeout_ms=800)
        if current_count is not None and updated_count is not None and updated_count > current_count:
            return updated_count
        if current_count is None:
            return updated_count

        self._log(f"[Pixiv] Suggestion click from {source} needs explicit Enter: {tag}")
        page.keyboard.press("Enter")
        updated_count = self._wait_for_tag_count_increment(page, current_count, timeout_ms=1200)
        if current_count is not None and updated_count is not None and updated_count > current_count:
            return updated_count
        if current_count is None:
            return updated_count
        return None

    def _click_matching_tag_suggestion(self, page, tag: str, current_count: Optional[int]) -> Optional[int]:
        suggestion_container = self._find_tag_suggestion_container(page)
        container = self._find_tag_container(page)
        hashed_candidate = f"#{tag}"
        roots = []
        if suggestion_container is not None:
            roots.append(("suggestion", suggestion_container))
        if container is not None and container is not suggestion_container:
            roots.append(("tag-container", container))
        roots.append(("page", page.locator("body").first))

        for root_name, root in roots:
            direct_candidates = [hashed_candidate] if root_name == "suggestion" else [hashed_candidate, tag]
            for candidate in direct_candidates:
                for getter in (
                    lambda value: root.get_by_role("option", name=value, exact=True),
                    lambda value: root.get_by_role("link", name=value, exact=True),
                    lambda value: root.get_by_role("button", name=value, exact=True),
                    lambda value: root.get_by_text(value, exact=True),
                ):
                    locator = getter(candidate)
                    if self._count(locator) <= 0:
                        continue
                    if not self._click_locator_or_interactive_ancestor(locator):
                        continue
                    self._log(f"[Pixiv] Clicked visible suggestion candidate from {root_name}: {candidate}")
                    updated_count = self._confirm_after_suggestion_click(page, tag, current_count, f"{root_name}/visible")
                    if updated_count is not None:
                        return updated_count
                    self._log(f"[Pixiv] Visible suggestion click from {root_name} did not confirm: {tag}")

            dom_candidates = [hashed_candidate] if root_name == "suggestion" else [hashed_candidate, tag]
            clicked = self._click_exact_tag_text_via_dom(
                root,
                dom_candidates,
                require_hash=(root_name == "suggestion"),
            )
            if clicked:
                self._log(f"[Pixiv] Clicked DOM suggestion fallback from {root_name}: {tag}")
                updated_count = self._confirm_after_suggestion_click(page, tag, current_count, f"{root_name}/dom")
                if updated_count is not None:
                    return updated_count
                self._log(f"[Pixiv] DOM suggestion fallback from {root_name} did not confirm: {tag}")
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
            locator = self._first_fillable_locator(
                search_root,
                selectors=selectors,
                labels=labels,
                texts=(),
            )
            if locator is None:
                raise RuntimeError(f"未找到 Pixiv 标签输入框，无法填写标签：{tag}")

            committed = False
            for strategy in ("Enter", "ArrowDownEnter", "Tab"):
                locator.click()
                try:
                    locator.press("Control+A")
                    locator.press("Delete")
                except Exception:
                    try:
                        locator.fill("")
                    except Exception:
                        pass

                locator.type(tag, delay=10)
                page.wait_for_timeout(150)
                if strategy == "ArrowDownEnter":
                    page.keyboard.press("ArrowDown")
                    page.wait_for_timeout(120)
                    page.keyboard.press("Enter")
                else:
                    page.keyboard.press(strategy)
                updated_count = self._wait_for_tag_count_increment(page, current_count)
                if current_count is not None and updated_count is not None and updated_count > current_count:
                    current_count = updated_count
                    committed = True
                    suffix = " via highlighted suggestion" if strategy == "ArrowDownEnter" else ""
                    self._log(f"[Pixiv] Added tag{suffix}: {tag} ({updated_count}/10)")
                    break
                if current_count is None:
                    committed = True
                    suffix = " via highlighted suggestion" if strategy == "ArrowDownEnter" else ""
                    self._log(f"[Pixiv] Submitted tag{suffix} without count feedback: {tag}")
                    break
                self._log(f"[Pixiv] Tag strategy {strategy} did not confirm: {tag}")

            if not committed:
                self._log(f"[Pixiv] Active element before suggestion fallback: {self._describe_active_element(page)}")
                updated_count = self._click_matching_tag_suggestion(page, tag, current_count)
                if current_count is not None and updated_count is not None and updated_count > current_count:
                    current_count = updated_count
                    committed = True
                    self._log(f"[Pixiv] Added tag via suggestion: {tag} ({updated_count}/10)")
                elif current_count is None and updated_count is not None:
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
