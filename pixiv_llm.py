import base64
import io
import json
import re
from pathlib import Path
from typing import Dict, List, Optional
from urllib.parse import urlparse

import requests
from PIL import Image


DEFAULT_PIXIV_LLM_SYSTEM_PROMPT = """你是 Pixiv 标签整理助手。
任务：把给定的 AI 绘图 metadata 提示词整理成适合 Pixiv 投稿的标签。

规则：
1. 只能基于输入里明确出现的概念生成标签，不要脑补新角色、新服装、新场景。
2. 输出日文 Pixiv 风格标签，尽量使用简短、常见、可搜索的标签。
3. 去掉质量词、渲染词、无意义 prompt 噪音，例如 masterpiece、best quality、absurdres。
4. 不要输出解释、序号、井号、句子。
5. 最多输出 10 个标签。
6. 只返回 JSON，格式必须是 {\"tags\":[\"女の子\",\"エルフ耳\"]}。
"""

DEFAULT_PIXIV_LLM_VISION_PROMPT = """你是 Pixiv 图像标签整理助手。
任务：观察给定图片内容，输出适合 Pixiv 投稿的日文标签。

规则：
1. 只能基于图片里能明确看到的内容生成标签，不要脑补角色名、作品名或设定背景。
2. 输出日文 Pixiv 风格标签，尽量使用简短、常见、可搜索的标签。
3. 优先描述主体、服饰、发色、瞳色、动作、场景、构图等直接可见信息。
4. 不要输出解释、序号、井号、句子。
5. 最多输出 10 个标签。
6. 只返回 JSON，格式必须是 {\"tags\":[\"女の子\",\"青い目\"]}。
"""

def _openai_compatible_endpoint(base_url: str, *, kind: str = "chat/completions") -> str:
    base = str(base_url or "").strip().rstrip("/")
    if not base:
        raise RuntimeError("LLM Base URL 为空")

    parsed = urlparse(base)
    path = parsed.path.rstrip("/")
    if path.endswith("/chat/completions"):
        root = base[: -len("/chat/completions")]
        return f"{root}/{kind}"
    if path.endswith("/v1"):
        return f"{base}/{kind}"
    if path:
        return f"{base}/v1/{kind}"
    return f"{base}/v1/{kind}"

def fetch_openai_compatible_models(base_url: str, api_key: str = "", timeout: int = 30) -> List[Dict[str, str]]:
    endpoint = _openai_compatible_endpoint(base_url, kind="models")
    headers = {"Accept": "application/json"}
    if api_key:
        headers["Authorization"] = f"Bearer {str(api_key).strip()}"

    response = requests.get(endpoint, headers=headers, timeout=max(5, int(timeout)))
    if response.status_code >= 400:
        raise RuntimeError(f"读取模型列表失败（HTTP {response.status_code}）：{response.text[:300]}")

    try:
        payload = response.json()
    except Exception as exc:
        raise RuntimeError("模型列表接口返回了无法解析的 JSON") from exc

    raw_items = payload.get("data") or payload.get("models") or []
    items: List[Dict[str, str]] = []
    seen = set()
    for raw in raw_items:
        if not isinstance(raw, dict):
            continue
        model_id = str(raw.get("id") or raw.get("name") or "").strip()
        if not model_id:
            continue
        lowered = model_id.lower()
        if lowered in seen:
            continue
        seen.add(lowered)
        items.append({"value": model_id, "label": model_id})

    items.sort(key=lambda item: item["label"].lower())
    return items



class OpenAICompatiblePixivTagger:
    def __init__(
        self,
        *,
        base_url: str,
        api_key: str,
        model: str,
        temperature: float = 0.1,
        timeout: int = 60,
        system_prompt: Optional[str] = None,
        vision_system_prompt: Optional[str] = None,
    ):
        self.base_url = str(base_url or "").strip()
        self.api_key = str(api_key or "").strip()
        self.model = str(model or "").strip()
        self.temperature = max(0.0, min(float(temperature), 2.0))
        self.timeout = max(5, int(timeout))
        self.system_prompt = str(system_prompt or DEFAULT_PIXIV_LLM_SYSTEM_PROMPT).strip()
        self.vision_system_prompt = str(vision_system_prompt or DEFAULT_PIXIV_LLM_VISION_PROMPT).strip()

    def is_ready(self) -> bool:
        return bool(self.base_url and self.model)

    def _endpoint(self) -> str:
        return _openai_compatible_endpoint(self.base_url, kind="chat/completions")

    def _headers(self) -> Dict[str, str]:
        headers = {
            "Content-Type": "application/json",
            "Accept": "application/json",
        }
        if self.api_key:
            headers["Authorization"] = f"Bearer {self.api_key}"
        return headers

    def _extract_content(self, payload: Dict) -> str:
        choices = payload.get("choices") or []
        if not choices:
            raise RuntimeError("LLM 响应里没有 choices")
        message = choices[0].get("message") or {}
        content = message.get("content", "")
        if isinstance(content, list):
            parts: List[str] = []
            for item in content:
                if isinstance(item, dict) and item.get("type") == "text":
                    parts.append(str(item.get("text") or ""))
                elif isinstance(item, str):
                    parts.append(item)
            return "".join(parts).strip()
        return str(content or "").strip()

    def _parse_json_text(self, content: str) -> Dict:
        text = str(content or "").strip()
        if not text:
            raise RuntimeError("LLM 返回了空内容")

        fenced = re.search(r"```(?:json)?\s*(\{.*?\})\s*```", text, re.S)
        if fenced:
            text = fenced.group(1).strip()
        else:
            match = re.search(r"\{.*\}", text, re.S)
            if match:
                text = match.group(0).strip()

        try:
            return json.loads(text)
        except json.JSONDecodeError as exc:
            raise RuntimeError(f"LLM 返回内容不是合法 JSON：{text[:200]}") from exc

    def _image_to_data_url(self, image_path: Path, *, max_side: int = 1280, quality: int = 85) -> str:
        path = Path(image_path)
        if not path.exists():
            raise RuntimeError(f"图像不存在：{path}")

        with Image.open(path) as image:
            image = image.convert("RGBA")
            image.thumbnail((max_side, max_side))
            canvas = Image.new("RGB", image.size, (255, 255, 255))
            canvas.paste(image, mask=image.getchannel("A"))

            buffer = io.BytesIO()
            canvas.save(buffer, format="JPEG", quality=quality, optimize=True)
        encoded = base64.b64encode(buffer.getvalue()).decode("ascii")
        return f"data:image/jpeg;base64,{encoded}"

    def _normalize_tags(self, values, limit: int = 10) -> List[str]:
        tags: List[str] = []
        seen = set()
        for value in values or []:
            text = str(value or "").strip().strip("#")
            text = re.sub(r"\s+", " ", text)
            if not text:
                continue
            lowered = text.lower()
            if lowered in seen:
                continue
            seen.add(lowered)
            tags.append(text)
            if len(tags) >= limit:
                break
        return tags

    def generate_tags(self, metadata_tags: List[str], *, limit: int = 10) -> List[str]:
        if not self.is_ready():
            raise RuntimeError("LLM 配置不完整，需要 Base URL 和 Model")

        if not metadata_tags:
            return []

        body = {
            "model": self.model,
            "temperature": self.temperature,
            "messages": [
                {"role": "system", "content": self.system_prompt},
                {
                    "role": "user",
                    "content": json.dumps(
                        {
                            "metadata_tags": metadata_tags,
                            "limit": int(limit),
                            "target": "pixiv_japanese_tags",
                        },
                        ensure_ascii=False,
                    ),
                },
            ],
        }
        response = requests.post(
            self._endpoint(),
            headers=self._headers(),
            json=body,
            timeout=self.timeout,
        )
        if response.status_code >= 400:
            raise RuntimeError(f"LLM 请求失败（HTTP {response.status_code}）：{response.text[:300]}")

        try:
            payload = response.json()
        except Exception as exc:
            raise RuntimeError("LLM 返回了无法解析的 JSON 响应") from exc

        content = self._extract_content(payload)
        parsed = self._parse_json_text(content)
        tags = self._normalize_tags(parsed.get("tags"), limit=limit)
        if not tags:
            raise RuntimeError("LLM 没有返回可用标签")
        return tags

    def generate_tags_from_image(self, image_path: Path, *, limit: int = 10) -> List[str]:
        if not self.is_ready():
            raise RuntimeError("LLM 配置不完整，需要 Base URL 和 Model")

        data_url = self._image_to_data_url(Path(image_path))
        body = {
            "model": self.model,
            "temperature": self.temperature,
            "messages": [
                {"role": "system", "content": self.vision_system_prompt},
                {
                    "role": "user",
                    "content": [
                        {
                            "type": "text",
                            "text": json.dumps(
                                {
                                    "limit": int(limit),
                                    "target": "pixiv_japanese_tags_from_image",
                                },
                                ensure_ascii=False,
                            ),
                        },
                        {
                            "type": "image_url",
                            "image_url": {"url": data_url},
                        },
                    ],
                },
            ],
        }
        response = requests.post(
            self._endpoint(),
            headers=self._headers(),
            json=body,
            timeout=self.timeout,
        )
        if response.status_code >= 400:
            raise RuntimeError(f"LLM 图像打标失败（HTTP {response.status_code}）：{response.text[:300]}")

        try:
            payload = response.json()
        except Exception as exc:
            raise RuntimeError("LLM 图像打标返回了无法解析的 JSON 响应") from exc

        content = self._extract_content(payload)
        parsed = self._parse_json_text(content)
        tags = self._normalize_tags(parsed.get("tags"), limit=limit)
        if not tags:
            raise RuntimeError("LLM 没有返回可用的图像标签")
        return tags
