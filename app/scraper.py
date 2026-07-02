import requests

HEADERS = {
    "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/125.0.0.0 Safari/537.36",
    "Accept": "application/json, text/plain, */*",
}

SECTION_LABEL_MAP = {
    "模型": "模型相关",
    "产品": "产品相关",
    "行业": "行业动态",
    "论文": "论文研究",
    "观点": "Agent技巧",
    "Agent": "Agent技巧",
}

def _map_category(section_label):
    for key, cat in SECTION_LABEL_MAP.items():
        if key in section_label:
            return cat
    return "行业动态"

def fetch_and_parse(date_str):
    url = f"https://aihot.virxact.com/api/public/daily/{date_str}"
    try:
        resp = requests.get(url, headers=HEADERS, timeout=15)
        resp.raise_for_status()
        raw = resp.json()
    except requests.Timeout:
        raise RuntimeError(f"请求超时: {url}")
    except requests.RequestException as e:
        raise RuntimeError(f"请求失败: {str(e)}")

    items = []
    sections = raw.get("sections", []) if isinstance(raw, dict) else []
    for section in sections:
        label = section.get("label", "")
        category = _map_category(label)
        for item in section.get("items", []):
            items.append({
                "title": item.get("title", ""),
                "content": item.get("summary", item.get("content", "")),
                "source": item.get("sourceName", item.get("source", "")),
                "category": category,
            })
    return items

def fetch_news(date_str):
    url = f"https://aihot.virxact.com/api/public/daily/{date_str}"
    try:
        resp = requests.get(url, headers=HEADERS, timeout=15)
        resp.raise_for_status()
        return resp.json()
    except requests.Timeout:
        return {"error": f"请求超时: {url}"}
    except requests.RequestException as e:
        return {"error": f"请求失败: {str(e)}"}

def parse_news(raw_data):
    if isinstance(raw_data, dict) and "error" in raw_data:
        return raw_data
    items = []
    sections = raw_data.get("sections", []) if isinstance(raw_data, dict) else []
    for section in sections:
        label = section.get("label", "")
        category = _map_category(label)
        for item in section.get("items", []):
            items.append({
                "title": item.get("title", ""),
                "content": item.get("summary", item.get("content", "")),
                "source": item.get("sourceName", item.get("source", "")),
                "category": category,
            })
    return items
