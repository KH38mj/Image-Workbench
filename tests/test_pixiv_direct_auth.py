from contextlib import closing
import sqlite3
import tempfile
import unittest
from pathlib import Path

import pixiv_uploader


class PixivDirectAuthHelpersTests(unittest.TestCase):
    def test_extract_pixiv_csrf_token_prefers_known_patterns(self):
        html = """
        <html>
          <head><script>window.g_csrfToken = "token-from-window";</script></head>
          <body></body>
        </html>
        """
        self.assertEqual(
            pixiv_uploader._extract_pixiv_csrf_token(html),
            "token-from-window",
        )

    def test_build_pixiv_cookie_header_filters_non_pixiv_domains(self):
        cookies = [
            {"name": "PHPSESSID", "value": "pixiv-session", "domain": ".pixiv.net"},
            {"name": "device_token", "value": "pixiv-device", "domain": "www.pixiv.net"},
            {"name": "sid", "value": "ignore-me", "domain": ".accounts.google.com"},
        ]
        self.assertEqual(
            pixiv_uploader._build_pixiv_cookie_header(cookies),
            "PHPSESSID=pixiv-session; device_token=pixiv-device",
        )

    def test_snapshot_sqlite_database_creates_readable_copy(self):
        with tempfile.TemporaryDirectory() as temp_dir:
            source = Path(temp_dir) / "Cookies"
            target = Path(temp_dir) / "copied" / "Cookies"

            with closing(sqlite3.connect(str(source))) as conn:
                conn.execute("create table cookies(name text, value text)")
                conn.execute("insert into cookies(name, value) values (?, ?)", ("PHPSESSID", "pixiv-session"))
                conn.commit()

            pixiv_uploader._snapshot_sqlite_database(source, target)

            with closing(sqlite3.connect(str(target))) as conn:
                row = conn.execute("select name, value from cookies").fetchone()

            self.assertEqual(row, ("PHPSESSID", "pixiv-session"))

    def test_copy_browser_auth_files_copies_cookie_snapshot(self):
        with tempfile.TemporaryDirectory() as temp_dir:
            root = Path(temp_dir)
            user_data_dir = root / "User Data"
            source_profile = user_data_dir / "Default"
            destination_root = root / "snapshot"
            cookie_db = source_profile / "Network" / "Cookies"

            (source_profile / "Network").mkdir(parents=True, exist_ok=True)
            (user_data_dir / "Local State").write_text('{"profile":{"last_used":"Default"}}', encoding="utf-8")
            (source_profile / "Preferences").write_text("{}", encoding="utf-8")

            with closing(sqlite3.connect(str(cookie_db))) as conn:
                conn.execute("create table cookies(name text, value text)")
                conn.execute("insert into cookies(name, value) values (?, ?)", ("device_token", "pixiv-device"))
                conn.commit()

            pixiv_uploader._copy_browser_auth_files(user_data_dir, "Default", destination_root)

            copied_local_state = destination_root / "Local State"
            copied_preferences = destination_root / "Default" / "Preferences"
            copied_cookie_db = destination_root / "Default" / "Network" / "Cookies"

            self.assertTrue(copied_local_state.exists())
            self.assertTrue(copied_preferences.exists())
            self.assertTrue(copied_cookie_db.exists())

            with closing(sqlite3.connect(str(copied_cookie_db))) as conn:
                row = conn.execute("select name, value from cookies").fetchone()

            self.assertEqual(row, ("device_token", "pixiv-device"))

    def test_interactive_fallback_detection_matches_locked_cookie_errors(self):
        errors = [
            "Default: 无法复制浏览器配置 (无法生成浏览器 Cookie 快照: Cookies: unable to open database file)",
        ]
        self.assertTrue(pixiv_uploader._should_fallback_to_interactive_browser_auth(errors))

    def test_interactive_fallback_detection_ignores_normal_login_errors(self):
        errors = [
            "Default: Pixiv 登录态已失效",
            "Profile 1: 没有读取到 Pixiv 登录 Cookie",
        ]
        self.assertFalse(pixiv_uploader._should_fallback_to_interactive_browser_auth(errors))

    def test_transient_page_state_error_matches_navigation_content_errors(self):
        message = "Page.content: Unable to retrieve content because the page is navigating and changing the content."
        self.assertTrue(pixiv_uploader._looks_like_transient_page_state_error(message))

    def test_transient_page_state_error_ignores_regular_runtime_errors(self):
        message = "Pixiv 登录态已失效，请重新导入 Cookie"
        self.assertFalse(pixiv_uploader._looks_like_transient_page_state_error(message))

    def test_build_pixiv_import_result_allows_missing_csrf(self):
        result = pixiv_uploader._build_pixiv_import_result(
            browser_channel="msedge",
            browser_name="Microsoft Edge",
            profile_name="interactive-login",
            cookie_header="PHPSESSID=abc; device_token=def",
            csrf_token="",
            source="interactive-login",
        )
        self.assertEqual(result["cookie"], "PHPSESSID=abc; device_token=def")
        self.assertEqual(result["csrfToken"], "")
        self.assertTrue(result["needsCsrfProbe"])
        self.assertIn("还没有拿到 CSRF Token", result["message"])

    def test_direct_uploader_cookie_only_probe_mode_is_allowed(self):
        uploader = pixiv_uploader._DirectPixivUploader({"cookie": "PHPSESSID=abc", "csrf_token": ""})
        try:
            self.assertTrue(uploader.ensure_ready(require_csrf=False))
            self.assertNotIn("x-csrf-token", uploader.session.headers)
        finally:
            uploader.close()


if __name__ == "__main__":
    unittest.main()
