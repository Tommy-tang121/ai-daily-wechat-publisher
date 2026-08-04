import json
import logging
from pathlib import Path

from .article_format import DEFAULT_DATA_SOURCE, build_markdown


logger = logging.getLogger("ai_daily")


class ContentError(RuntimeError):
    def __init__(self, message: str, diagnostics: dict | None = None):
        super().__init__(message)
        self.diagnostics = diagnostics or {}


class ContentRetryExhaustedError(ContentError):
    pass


class Content:
    """Builds one complete, attributable daily article from injected adapters."""

    def __init__(self, source, llm):
        self.source = source
        self.llm = llm

    def build(self, date: str, settings: dict, progress=None) -> dict:
        def report(stage: str, status: str, message: str) -> None:
            if progress:
                progress(stage, status, message)

        report("scraping", "progress", "正在抓取当日资讯")
        items = self.source(date)
        if not items or any(not item.get("source_url") for item in items):
            raise ContentError("抓取结果缺少可追溯链接")
        report("scraping", "complete", f"已抓取 {len(items)} 条资讯")
        report("rewriting", "progress", f"正在一次改写全部 {len(items)} 条资讯")
        article = self._rewrite_daily(date, items, settings)
        report("rewriting", "complete", f"已完成全部 {len(items)} 条改写")
        return article

    def _rewrite_daily(self, date: str, items: list[dict], settings: dict) -> dict:
        last_error = None
        for attempt in range(1, 3):
            try:
                retry_reason = str(last_error) if last_error else ""
                return self._rewrite_once(date, items, settings, retry_reason)
            except ContentError as exc:
                last_error = exc
                diagnostics = exc.diagnostics
                logger.warning(
                    "stage=rewriting_invalid attempt=%s reason=%s finish_reason=%s "
                    "response_chars=%s prompt_tokens=%s completion_tokens=%s",
                    attempt,
                    str(exc),
                    diagnostics.get("finish_reason", "unknown"),
                    diagnostics.get("response_chars", "unknown"),
                    diagnostics.get("prompt_tokens", "unknown"),
                    diagnostics.get("completion_tokens", "unknown"),
                )
        failure_reason = str(last_error)
        if last_error.diagnostics.get("finish_reason") == "length":
            failure_reason += "；模型输出达到长度上限"
        raise ContentRetryExhaustedError(f"{failure_reason}（已自动重试一次）") from last_error

    def _rewrite_once(self, date: str, items: list[dict], settings: dict, retry_reason: str = "") -> dict:
        prompt_path = Path(__file__).parents[2] / "prompts" / "rewrite.md"
        prompt = prompt_path.read_text(encoding="utf-8")
        prompt = prompt.replace("{{MAX_CHARS}}", str(settings.get("max_words", 150)))
        prompt = prompt.replace("{{DAILY_DATA}}", self._daily_input(date, items))
        user_message = f"请根据以上要求处理今日的 {len(items)} 条 AI 新闻。"
        if retry_reason:
            user_message = (
                f"上一次返回未通过校验：{retry_reason}。这是最后一次尝试，请重新处理完整的 "
                f"{len(items)} 条 AI 新闻，并严格原样返回全部编号。"
            )
        result = self.llm([
            {
                "role": "system",
                "content": prompt,
            },
            {
                "role": "user",
                "content": user_message,
            },
        ])
        raw_value = result.content if hasattr(result, "content") else result
        diagnostics = {
            "finish_reason": getattr(result, "finish_reason", "") or "unknown",
            "response_chars": len(raw_value) if isinstance(raw_value, str) else 0,
            "prompt_tokens": getattr(result, "prompt_tokens", None) or "unknown",
            "completion_tokens": getattr(result, "completion_tokens", None) or "unknown",
        }
        if not isinstance(raw_value, str):
            raise ContentError("LLM 返回格式无效：content 不是文本", diagnostics)
        raw = raw_value.strip()
        diagnostics["response_chars"] = len(raw)
        try:
            payload = self._parse_json(raw)
        except ContentError as exc:
            exc.diagnostics = diagnostics
            raise
        if not isinstance(payload, dict):
            raise ContentError("LLM 返回格式无效：最外层必须是 JSON 对象", diagnostics)
        opening = payload.get("todayObservation")
        closing = payload.get("editorComment")
        rewritten = payload.get("items")
        if not isinstance(opening, str) or not opening.strip():
            raise ContentError("LLM 返回格式无效：todayObservation 缺失或为空", diagnostics)
        if not isinstance(closing, str) or not closing.strip():
            raise ContentError("LLM 返回格式无效：editorComment 缺失或为空", diagnostics)
        if not isinstance(rewritten, list):
            raise ContentError("LLM 返回格式无效：items 缺失或不是数组", diagnostics)

        expected_ids = set(range(1, len(items) + 1))
        returned_ids = [
            item.get("id")
            for item in rewritten
            if isinstance(item, dict) and type(item.get("id")) is int
        ]
        duplicate_ids = sorted({item_id for item_id in returned_ids if returned_ids.count(item_id) > 1})
        if duplicate_ids:
            duplicates = ", ".join(str(item_id) for item_id in duplicate_ids)
            raise ContentError(f"LLM 返回条目编号无效：重复编号 {duplicates}", diagnostics)
        unknown_ids = sorted(set(returned_ids) - expected_ids)
        if unknown_ids:
            unknown = ", ".join(str(item_id) for item_id in unknown_ids)
            raise ContentError(f"LLM 返回条目编号无效：未知编号 {unknown}", diagnostics)
        returned_by_id = {
            item["id"]: item
            for item in rewritten
            if isinstance(item, dict) and type(item.get("id")) is int
        }
        missing_ids = sorted(expected_ids - returned_by_id.keys())
        if missing_ids:
            missing = ", ".join(str(item_id) for item_id in missing_ids)
            raise ContentError(f"LLM 返回条目不完整：缺少编号 {missing}", diagnostics)
        invalid_ids = [
            item_id
            for item_id in sorted(expected_ids)
            if not returned_by_id[item_id].get("title") or not returned_by_id[item_id].get("rewritten")
        ]
        if invalid_ids:
            invalid = ", ".join(str(item_id) for item_id in invalid_ids)
            raise ContentError(f"LLM 返回条目不完整：编号 {invalid} 缺少标题或正文", diagnostics)
        rewritten = [returned_by_id[item_id] for item_id in sorted(expected_ids)]
        opening = opening.strip()
        closing = closing.strip()
        rewritten_items = [
            {
                "title": edited["title"],
                "body": edited["rewritten"],
                "source": origin.get("source", ""),
                "source_url": origin["source_url"],
                "category": origin.get("category", "行业动态"),
            }
            for origin, edited in zip(items, rewritten)
        ]
        return {
            "date": date,
            "items": rewritten_items,
            "opening": opening,
            "closing": closing,
            "markdown": build_markdown(
                opening,
                rewritten_items,
                closing,
                settings.get("data_source", DEFAULT_DATA_SOURCE),
            ),
        }

    @staticmethod
    def _daily_input(date: str, items: list[dict]) -> str:
        entries = [f"日期：{date}", f"本次必须完整返回 {len(items)} 条资讯。"]
        for index, item in enumerate(items, start=1):
            entries.extend([
                f"### 条目 {index}",
                f"编号：{index}",
                f"标题：{item.get('title', '')}",
                f"内容：{item.get('summary', '')}",
                f"来源：{item.get('source', '')}",
            ])
        return "\n".join(entries)

    @staticmethod
    def _parse_json(raw: str) -> dict:
        if raw.startswith("```"):
            raw = raw.split("\n", 1)[1].rsplit("```", 1)[0].strip()
        try:
            return json.loads(raw)
        except json.JSONDecodeError as exc:
            raise ContentError(f"LLM 返回 JSON 无法解析：位置 {exc.pos}") from exc
