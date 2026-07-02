import re

def format_article(text):
    lines = text.split("\n")
    out = []

    for line in lines:
        stripped = line.strip()
        if not stripped:
            out.append("")
            continue
        if stripped.startswith("来源：") or stripped.startswith("数据来源："):
            out.append(stripped)
            continue
        text = stripped
        text = text.replace(",", "，")
        text = text.replace("!", "！")
        text = text.replace("?", "？")
        text = text.replace(":", "：")
        text = text.replace(";", "；")
        text = text.replace("(", "（")
        text = text.replace(")", "）")
        out.append(text)

    result = []
    blank = False
    for line in out:
        if line == "":
            if not blank:
                result.append("")
                blank = True
        else:
            result.append(line)
            blank = False

    return "\n".join(result)


def build_markdown(result, date_str="", title="", data_source=""):
    md = []
    if result.get("opening"):
        md.append("**今日观察**")
        md.append("")
        md.append(re.sub(r"\s*\n\s*", " ", result["opening"]).strip())
        md.append("")
    current_cat = None
    for item in result.get("items", []):
        if item["category"] != current_cat:
            current_cat = item["category"]
            md.append(f"**【{current_cat}】**")
            md.append("")
        md.append(f"**{item['title']}**")
        md.append("")
        md.append(item["body"])
        md.append("")
        md.append(f"来源：{item['source']}")
        md.append("")
    if result.get("closing"):
        md.append("**小编短评**")
        md.append("")
        md.append(re.sub(r"\s*\n\s*", " ", result["closing"]).strip())
        md.append("")
    if data_source:
        md.append("---")
        md.append("")
        md.append(f"数据来源：{data_source}")
    return "\n".join(md)
