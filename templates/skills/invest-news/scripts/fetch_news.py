import akshare as ak
import argparse
import sys
import json
import os
from datetime import datetime


def resolve_default_data_root():
    """
    自动推断默认落盘目录：
    1) OpenClaw runtime shared: /root/.openclaw/workspace/data/news
    2) Local workspace_data: <repo>/workspace_data/news
    """
    script_dir = os.path.dirname(__file__)

    # Fallback 1: Production OpenClaw Workspace Data
    runtime_shared_candidate = "/root/.openclaw/workspace/data/news"
    if os.path.isdir(os.path.dirname(runtime_shared_candidate)):
        return runtime_shared_candidate

    # Fallback 2: Local Repo workspace_data (development)
    local_shared_candidate = os.path.abspath(os.path.join(script_dir, "../../../workspace_data/news"))
    if os.path.isdir(os.path.dirname(local_shared_candidate)):
        return local_shared_candidate

    return runtime_shared_candidate


# 可由 OPENCLAW_DATA_DIR 显式覆盖。
DATA_ROOT = os.environ.get("OPENCLAW_DATA_DIR", resolve_default_data_root())

def resolve_company_dict_path():
    script_dir = os.path.dirname(__file__)
    # Production: ~/.openclaw/workspace/data/references/companies.json
    runtime = "/root/.openclaw/workspace/data/references/companies.json"
    if os.path.exists(runtime):
        return runtime
    # Local dev: <repo>/workspace_data/references/companies.json
    local = os.path.abspath(os.path.join(script_dir, "../../../workspace_data/references/companies.json"))
    if os.path.exists(local):
        return local
    return runtime

COMPANY_DICT_PATH = os.environ.get("OPENCLAW_COMPANY_DICT", resolve_company_dict_path())


def build_fingerprint(item):
    """
    简单去重键：来源 + 标题 + 链接 + 公司。
    """
    return "||".join(
        [
            str(item.get("source", "")).strip(),
            str(item.get("title", "")).strip(),
            str(item.get("url", "")).strip(),
            str(item.get("company", "")).strip(),
        ]
    )


def load_existing_fingerprints(raw_path):
    """
    从当天 raw 文件读取已有指纹，避免重复追加。
    """
    fingerprints = set()
    if not os.path.exists(raw_path):
        return fingerprints

    with open(raw_path, "r", encoding="utf-8") as f:
        for line in f:
            line = line.strip()
            if not line:
                continue
            try:
                item = json.loads(line)
                fingerprints.add(build_fingerprint(item))
            except json.JSONDecodeError:
                # 跳过损坏行，不中断主流程
                continue
    return fingerprints


def deduplicate_news(news_list, existing_fingerprints):
    """
    最小去重：先去重已有文件中的重复，再去重当前批次内部重复。
    """
    if not news_list:
        return []

    unique_items = []
    seen = set(existing_fingerprints)
    for item in news_list:
        fp = build_fingerprint(item)
        if fp in seen:
            continue
        seen.add(fp)
        unique_items.append(item)
    return unique_items

def load_company_dict(path):
    with open(path, "r", encoding="utf-8") as f:
        payload = json.load(f)
    companies = payload.get("companies", [])
    if not companies:
        raise ValueError("No companies configured in companies.json")
    return companies


def normalize_text(value):
    return str(value).strip().lower()


def resolve_company(subject):
    companies = load_company_dict(COMPANY_DICT_PATH)
    lookup = normalize_text(subject)

    for company in companies:
        aliases = [normalize_text(x) for x in company.get("aliases", [])]
        if lookup in aliases:
            return company
        if lookup == normalize_text(company.get("id", "")):
            return company
        if lookup == normalize_text(company.get("symbol", "")):
            return company

    raise ValueError(
        f"Unknown company subject: {subject}. Please configure it in {COMPANY_DICT_PATH}."
    )


def enrich_company_fields(item, company_meta):
    enriched = dict(item)
    enriched["company"] = company_meta["id"]
    enriched["company_name"] = company_meta["name"]
    enriched["company_symbol"] = company_meta["symbol"]
    enriched["company_market"] = company_meta["market"]
    return enriched


def match_company_keywords(title, company_meta):
    """
    匹配公司及其相关的新闻，并返回匹配类型和匹配词。
    返回 (bool, match_type, matched_keyword)
    """
    text = str(title or "")
    
    # 优先级 1: 公司直接别名
    aliases = [company_meta["name"], company_meta["symbol"]] + company_meta.get("aliases", [])
    aliases = [str(k).strip() for k in aliases if str(k).strip()]
    for k in aliases:
        if k in text: return True, "company", k
        
    # 优先级 2: 旗下品牌/产品
    brands = [str(k).strip() for k in company_meta.get("brands", []) if str(k).strip()]
    for k in brands:
        if k in text: return True, "brand", k
        
    # 优先级 3: 竞争对手
    competitors = [str(k).strip() for k in company_meta.get("competitors", []) if str(k).strip()]
    for k in competitors:
        if k in text: return True, "competitor", k
        
    # 优先级 4: 行业关键词
    industry = [str(k).strip() for k in company_meta.get("industry_keywords", []) if str(k).strip()]
    for k in industry:
        if k in text: return True, "industry", k
        
    return False, "none", ""


def fetch_em_news(company_meta):
    """
    东方财富个股新闻。
    """
    results = []
    try:
        em_news = ak.stock_news_em(symbol=company_meta["symbol"])
        for _, row in em_news.head(20).iterrows():
            title = row["新闻标题"]
            is_match, match_type, match_kw = match_company_keywords(title, company_meta)
            if not is_match:
                continue
            base = {
                "ts": row["发布时间"],
                "source": "东方财富",
                "title": title,
                "content": row["新闻内容"],
                "url": row["新闻链接"] if "新闻链接" in row else "N/A",
                "raw_type": "个股动态",
                "match_type": match_type,
                "match_keyword": match_kw,
            }
            results.append(enrich_company_fields(base, company_meta))
    except Exception:
        pass
    return results


def fetch_cls_news(company_meta):
    """
    财联社滚动电报（按 subject 定向过滤）。
    """
    results = []
    try:
        cls_news = ak.stock_info_global_cls(symbol="全部")
        
        # 收集所有维度的关键词来做 Pandas 过滤
        keywords = [company_meta["name"], company_meta["symbol"]] + company_meta.get("aliases", []) + \
                   company_meta.get("brands", []) + company_meta.get("competitors", []) + \
                   company_meta.get("industry_keywords", [])
        keywords = [str(k).strip() for k in keywords if str(k).strip()]
        
        masks = [
            cls_news["标题"].str.contains(k, na=False, regex=False)
            | cls_news["内容"].str.contains(k, na=False, regex=False)
            for k in keywords
        ]
        if not masks:
            return results
            
        mask = masks[0]
        for m in masks[1:]:
            mask = mask | m
            
        filtered_cls = cls_news[mask]
        for _, row in filtered_cls.head(30).iterrows():
            title = row["标题"]
            content = row["内容"]
            is_match, match_type, match_kw = match_company_keywords(title + content, company_meta)
            if not is_match:
                continue
            base = {
                "ts": f"{row['发布日期']} {row['发布时间']}",
                "source": "财联社",
                "title": title,
                "content": content,
                "url": "https://www.cls.cn/",
                "raw_type": "定向电报",
                "match_type": match_type,
                "match_keyword": match_kw,
            }
            results.append(enrich_company_fields(base, company_meta))
    except Exception:
        pass
    return results


def fetch_specific_signals(subject, source="all"):
    """
    按来源抓取特定主体新闻。
    source: em | cls | all
    """
    if not subject:
        return []

    company_meta = resolve_company(subject)
    results = []
    if source in ("em", "all"):
        results.extend(fetch_em_news(company_meta))
    if source in ("cls", "all"):
        results.extend(fetch_cls_news(company_meta))
    return results


def parse_args(argv):
    parser = argparse.ArgumentParser(description="Fetch raw news and append deduplicated JSONL records.")
    parser.add_argument("subject", help="Target subject/company, e.g. 00700")
    parser.add_argument(
        "--source",
        choices=["em", "cls", "all"],
        default="all",
        help="News source to fetch: em (Eastmoney), cls (Cailianpress), or all",
    )
    return parser.parse_args(argv)


def save_to_raw(news_list):
    today = datetime.now().strftime("%Y-%m-%d")
    raw_path = os.path.join(DATA_ROOT, f"raw/{today}.jsonl")
    if not news_list:
        return raw_path, 0

    os.makedirs(os.path.dirname(raw_path), exist_ok=True)

    existing_fingerprints = load_existing_fingerprints(raw_path)
    unique_news = deduplicate_news(news_list, existing_fingerprints)

    if not unique_news:
        return raw_path, 0

    with open(raw_path, "a", encoding="utf-8") as f:
        for item in unique_news:
            f.write(json.dumps(item, ensure_ascii=False) + "\n")
    return raw_path, len(unique_news)


if __name__ == "__main__":
    try:
        args = parse_args(sys.argv[1:])
        company = resolve_company(args.subject)
        signals = fetch_specific_signals(args.subject, args.source)
        raw_path, saved_count = save_to_raw(signals)
        print(f"Saved raw news to: {raw_path}")
        print(f"Source mode: {args.source}")
        print(f"Company: {company['id']} ({company['symbol']})")
        print(f"Fetched: {len(signals)}, Saved(after dedup): {saved_count}")
        print(json.dumps(signals, ensure_ascii=False))
    except Exception as exc:
        print(f"Error: {exc}")
        sys.exit(1)
