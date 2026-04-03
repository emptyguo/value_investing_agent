import akshare as ak
import argparse
import sys
import json
import os
import uuid
from datetime import datetime

try:
    from zoneinfo import ZoneInfo
except ImportError:
    from backports.zoneinfo import ZoneInfo

# Add repo root to path to allow importing from skills
sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), "../../../")))
from skills.common.scripts.utils import normalize_fingerprint, atomic_append_jsonl

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
    local_shared_candidate = os.path.abspath(os.path.join(script_dir, "../../../../workspace_data/news"))
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
    local = os.path.abspath(os.path.join(script_dir, "../../../../workspace_data/references/companies.json"))
    if os.path.exists(local):
        return local
    return runtime

COMPANY_DICT_PATH = os.environ.get("OPENCLAW_COMPANY_DICT", resolve_company_dict_path())


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
                fp = normalize_fingerprint(item.get("title", ""), item.get("url", ""))
                fingerprints.add(fp)
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
        fp = normalize_fingerprint(item.get("title", ""), item.get("url", ""))
        item["fingerprint"] = fp
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


def parse_args(argv):
    parser = argparse.ArgumentParser(description="Fetch raw news based on v3 contract.")
    
    group = parser.add_mutually_exclusive_group(required=True)
    group.add_argument("--all", action="store_true", help="Scan all companies")
    group.add_argument("--subject", help="Scan specific company ID")
    
    parser.add_argument("--mode", choices=["native", "akshare", "all"], default="all")
    
    # Default to Asia/Shanghai current date
    tz_sh = ZoneInfo("Asia/Shanghai")
    default_date = datetime.now(tz_sh).strftime("%Y-%m-%d")
    parser.add_argument("--date", default=default_date, help="Format YYYY-MM-DD")
    
    return parser.parse_args(argv)

def log_run_metadata(data_root, run_id, date_str, scope, mode, success_count):
    ts = datetime.now(ZoneInfo("Asia/Shanghai")).strftime("%Y%m%d_%H%M%S")
    # If data_root already ends in 'news', we just append 'raw' and 'metadata'.
    # For safety, let's just make it work whether data_root has 'news' or not.
    # By specification from instructions:
    # meta_path = os.path.join(data_root, "news", "raw", "metadata", f"run_{ts}_{run_id}.json")
    # But since DATA_ROOT might already be .../news, we'll strip trailing 'news' if needed.
    if data_root.endswith("news"):
        data_root = os.path.dirname(data_root)
    
    meta_path = os.path.join(data_root, "news", "raw", "metadata", f"run_{ts}_{run_id}.json")
    os.makedirs(os.path.dirname(meta_path), exist_ok=True)
    
    payload = {
        "run_id": run_id,
        "timestamp": ts,
        "target_date": date_str,
        "scope": scope,
        "mode": mode,
        "success_count": success_count
    }
    with open(meta_path, "w", encoding="utf-8") as f:
        json.dump(payload, f, ensure_ascii=False, indent=2)


def save_to_raw(news_list, date_str):
    raw_path = os.path.join(DATA_ROOT, f"raw/{date_str}.jsonl")
    if not news_list:
        return raw_path, 0

    existing_fingerprints = load_existing_fingerprints(raw_path)
    unique_news = deduplicate_news(news_list, existing_fingerprints)

    if not unique_news:
        return raw_path, 0

    atomic_append_jsonl(raw_path, unique_news)
    return raw_path, len(unique_news)


if __name__ == "__main__":
    try:
        args = parse_args(sys.argv[1:])
        run_id = str(uuid.uuid4())
        
        signals = []
        if args.all:
            companies = load_company_dict(COMPANY_DICT_PATH)
            for company in companies:
                if args.mode in ["all", "akshare"]:
                    signals.extend(fetch_em_news(company))
            scope = "all"
        else:
            company = resolve_company(args.subject)
            if args.mode in ["all", "akshare"]:
                signals.extend(fetch_em_news(company))
            scope = args.subject
            
        raw_path, saved_count = save_to_raw(signals, args.date)
        
        log_run_metadata(DATA_ROOT, run_id, args.date, scope, args.mode, saved_count)
        
        print(f"Saved raw news to: {raw_path}")
        print(f"Run ID: {run_id}")
        print(f"Fetched: {len(signals)}, Saved(after dedup): {saved_count}")
    except Exception as exc:
        print(f"Error: {exc}")
        sys.exit(1)
