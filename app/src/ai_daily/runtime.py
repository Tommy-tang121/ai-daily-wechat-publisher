import json
import os
from datetime import date as calendar_date
from pathlib import Path

from .content import Content
from .cover import generate_cover
from .daily_run import DailyRun
from .publishing import WeChatPublisher
from .storage import Store


DEFAULT_SETTINGS = {
    "title": "AI 行业热点新闻",
    "author": "",
    "max_words": 150,
    "schedule_time": "10:00",
    "data_source": "https://aihot.virxact.com/",
}


# Keep the editorial categories from the original daily instead of exposing
# the source site's changing section labels directly in the article.
SECTION_LABEL_MAP = {
    "模型": "模型相关",
    "产品": "产品相关",
    "行业": "行业动态",
    "论文": "论文研究",
    "观点": "Agent技巧",
    "Agent": "Agent技巧",
}


def _map_category(section_label: str) -> str:
    for keyword, category in SECTION_LABEL_MAP.items():
        if keyword in section_label:
            return category
    return "行业动态"


def load_environment(app_dir: Path) -> None:
    """Load the new app/.env, then legacy root/.env only when absent."""
    candidates = [app_dir.parent / ".env", app_dir / ".env"]
    existing_keys = set(os.environ)
    loaded = {}
    for path in candidates:
        if not path.is_file():
            continue
        for line in path.read_text(encoding="utf-8").splitlines():
            if "=" in line and not line.lstrip().startswith("#"):
                key, value = line.split("=", 1)
                loaded[key.strip()] = value.strip()
    for key, value in loaded.items():
        if key not in existing_keys:
            os.environ[key] = value


class AihotSource:
    def __call__(self, date: str) -> list[dict]:
        import requests

        response = requests.get(
            f"https://aihot.virxact.com/api/public/daily/{date}",
            headers={
                "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 Chrome/125 Safari/537.36",
                "Accept": "application/json",
            },
            timeout=20,
        )
        response.raise_for_status()
        items = []
        for section in response.json().get("sections", []):
            for item in section.get("items", []):
                link = item.get("permalink") or item.get("sourceUrl")
                if link:
                    items.append(
                        {
                            "title": item.get("title", ""),
                            "summary": item.get("summary", ""),
                            "source": item.get("sourceName", ""),
                            "source_url": link,
                            "category": _map_category(section.get("label", "")),
                        }
                    )
        return items


class OpenAiCompatibleLlm:
    def __call__(self, messages: list[dict]) -> str:
        import requests
        import time

        api_key = os.environ.get("LLM_API_KEY")
        if not api_key:
            raise RuntimeError("未配置 LLM_API_KEY")
        base = os.environ.get("LLM_BASE_URL", "https://api.openai.com/v1").rstrip("/")
        payload = {
            "model": os.environ.get("LLM_MODEL", "gpt-4o-mini"),
            "messages": messages,
            "max_tokens": 8000,
        }
        last_error = None
        for attempt in range(3):
            try:
                response = requests.post(
                    f"{base}/chat/completions",
                    headers={"Authorization": f"Bearer {api_key}"},
                    json=payload,
                    timeout=(15, 120),
                )
                response.raise_for_status()
                return response.json()["choices"][0]["message"]["content"]
            except requests.RequestException as exc:
                last_error = exc
                if attempt < 2:
                    time.sleep(2**attempt)
        raise RuntimeError(f"LLM 连接失败：{last_error}")


def build_runner(app_dir: Path, preview_only: bool = False) -> DailyRun:
    load_environment(app_dir)
    settings = DEFAULT_SETTINGS.copy()
    legacy = app_dir / "data" / "config.json"
    if legacy.is_file():
        legacy_values = json.loads(legacy.read_text(encoding="utf-8"))
        settings.update({key: legacy_values[key] for key in settings if key in legacy_values})
    if preview_only:
        publisher = lambda article: (_ for _ in ()).throw(RuntimeError("预览模式禁止创建微信草稿"))
    else:
        publisher = WeChatPublisher(settings["title"], author=settings["author"])

    def cover(article: dict, values: dict) -> dict:
        path = generate_cover(
            app_dir / "static" / "runtime-covers",
            article["date"],
            values.get("title", settings["title"]),
            values.get("author", settings["author"]),
        )
        return {"cover_path": str(path), "cover_url": f"/static/runtime-covers/{path.name}"}

    runtime_covers_dir = (app_dir / "static" / "runtime-covers").resolve()

    def remove_runtime_cover(path: Path) -> None:
        if path.is_symlink():
            return
        resolved = path.resolve()
        if resolved.is_relative_to(runtime_covers_dir) and resolved.is_file():
            resolved.unlink()

    def cleanup(article: dict) -> None:
        cover_path = article.get("cover_path")
        if not cover_path:
            return
        remove_runtime_cover(Path(cover_path))

    def cleanup_date(run_date: str) -> None:
        try:
            calendar_date.fromisoformat(run_date)
        except (TypeError, ValueError):
            return
        for path in runtime_covers_dir.glob(f"{run_date}.*"):
            remove_runtime_cover(path)

    store = Store(app_dir / "data" / "ai_daily.db")
    store.initialize_settings(settings)
    return DailyRun(
        store,
        Content(AihotSource(), OpenAiCompatibleLlm()),
        publisher,
        cover=cover,
        settings=settings,
        cleanup=cleanup,
        cleanup_date=cleanup_date,
    )
