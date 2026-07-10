from app.config import get_config
from app.scraper import fetch_and_parse
from app.rewriter import rewrite_news
from app.markdown import format_article
from app.markdown import build_markdown
from app.cover_generator import generate_cover


class PipelineError(RuntimeError):
    pass


def run_pipeline(date_str, max_words=150, on_progress=None):
    try:
        items = fetch_and_parse(date_str)
    except RuntimeError as e:
        raise PipelineError(str(e))

    if on_progress:
        on_progress("scraping", "complete", f"抓取完成 ({len(items)}条)", 25)

    def _progress(cur, tot):
        if on_progress:
            pct = 25 + int(25 * cur / max(tot, 1))
            msg = "正在请求 AI 改写（约 30 秒）..." if cur == 0 else f"重写中 ({cur}/{tot})..."
            on_progress("rewriting", "progress", msg, pct)

    result = rewrite_news(items, max_words, _progress)

    if on_progress:
        on_progress("rewriting", "complete", "重写完成", 50)

    cfg = get_config()
    article_text = build_markdown(result, date_str, cfg.get("title", ""), cfg.get("data_source", ""))
    formatted = format_article(article_text)

    if on_progress:
        on_progress("formatting", "complete", "排版完成", 75)

    generate_cover(date_str, cfg.get("title", ""), cfg.get("author", ""))

    return {
        "items": result["items"],
        "opening": result.get("opening", ""),
        "closing": result.get("closing", ""),
        "markdown": formatted,
    }
