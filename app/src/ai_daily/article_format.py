import re


DEFAULT_DATA_SOURCE = "https://aihot.virxact.com/"


def format_article(text: str) -> str:
    normalized = []
    for line in text.split("\n"):
        stripped = line.strip()
        if not stripped:
            normalized.append("")
        elif stripped.startswith("来源：") or stripped.startswith("数据来源："):
            normalized.append(stripped)
        else:
            normalized.append(
                stripped.replace(",", "，").replace("!", "！").replace("?", "？")
                .replace(":", "：").replace(";", "；").replace("(", "（").replace(")", "）")
            )

    result = []
    previous_blank = False
    for line in normalized:
        if line == "":
            if not previous_blank:
                result.append(line)
            previous_blank = True
        else:
            result.append(line)
            previous_blank = False
    return "\n".join(result)


def build_markdown(opening: str, items: list[dict], closing: str,
                   data_source: str = DEFAULT_DATA_SOURCE) -> str:
    markdown = ["**今日观察**", "", re.sub(r"\s*\n\s*", " ", opening).strip(), ""]
    category = None
    for item in items:
        if item["category"] != category:
            category = item["category"]
            markdown.extend([f"**【{category}】**", ""])
        markdown.extend([f"**{item['title']}**", "", item["body"], "", f"来源：{item['source']}", ""])
    markdown.extend(["**小编短评**", "", re.sub(r"\s*\n\s*", " ", closing).strip(), ""])
    if data_source:
        markdown.extend(["---", "", f"数据来源：{data_source}"])
    return format_article("\n".join(markdown))
