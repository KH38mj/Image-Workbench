import importlib
import json
import sys
import tempfile
import types
import unittest
from pathlib import Path
from unittest.mock import patch


def _load_webview_app():
    fake_webview = types.SimpleNamespace(
        FileDialog=types.SimpleNamespace(OPEN="open", SAVE="save", FOLDER="folder"),
        create_window=lambda *args, **kwargs: None,
        start=lambda *args, **kwargs: None,
    )
    sys.modules["webview"] = fake_webview

    if "webview_app" in sys.modules:
        return importlib.reload(sys.modules["webview_app"])
    return importlib.import_module("webview_app")


class WebviewConfigRegressionTests(unittest.TestCase):
    def test_save_config_scrubs_sensitive_pixiv_fields_but_keeps_session_values(self):
        webview_app = _load_webview_app()

        with tempfile.TemporaryDirectory() as temp_dir_name:
            config_path = Path(temp_dir_name) / "webview_config.json"
            with patch.object(webview_app, "CONFIG_PATH", config_path):
                bridge = webview_app.WebviewBridge()
                pixiv_settings = bridge._normalize_pixiv_settings(
                    {
                        "cookie": "cookie-value",
                        "csrf_token": "csrf-value",
                        "llm_api_key": "llm-secret",
                    }
                )
                bridge._config["pixiv"] = pixiv_settings
                bridge._save_config()

                saved = json.loads(config_path.read_text(encoding="utf-8"))
                self.assertEqual(saved["pixiv"]["cookie"], "")
                self.assertEqual(saved["pixiv"]["csrf_token"], "")
                self.assertEqual(saved["pixiv"]["llm_api_key"], "")

                resumed = bridge._normalize_pixiv_settings({})
                self.assertEqual(resumed["cookie"], "cookie-value")
                self.assertEqual(resumed["csrf_token"], "csrf-value")
                self.assertEqual(resumed["llm_api_key"], "llm-secret")

    def test_loading_legacy_config_rewrites_sensitive_fields_to_blank(self):
        webview_app = _load_webview_app()

        with tempfile.TemporaryDirectory() as temp_dir_name:
            config_path = Path(temp_dir_name) / "webview_config.json"
            config_path.write_text(
                json.dumps(
                    {
                        "pixiv": {
                            "cookie": "legacy-cookie",
                            "csrf_token": "legacy-csrf",
                            "llm_api_key": "legacy-key",
                        }
                    },
                    ensure_ascii=False,
                    indent=2,
                ),
                encoding="utf-8",
            )

            with patch.object(webview_app, "CONFIG_PATH", config_path):
                webview_app.WebviewBridge()
                rewritten = json.loads(config_path.read_text(encoding="utf-8"))

            self.assertEqual(rewritten["pixiv"]["cookie"], "")
            self.assertEqual(rewritten["pixiv"]["csrf_token"], "")
            self.assertEqual(rewritten["pixiv"]["llm_api_key"], "")


if __name__ == "__main__":
    unittest.main()
