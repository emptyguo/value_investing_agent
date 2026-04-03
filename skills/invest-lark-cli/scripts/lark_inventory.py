#!/usr/bin/env python3
"""Stage 1: Inventory — 遍历飞书文件夹/知识库，生成 manifest.jsonl

用法：
  python3 lark_inventory.py --workspace /path/to/workspace --source <folder_token_or_url> [--batch-id 20260401-154600]

依赖：lark-cli 已安装并完成认证（lark-cli auth login --recommend）
"""

import argparse
import hashlib
import json
import re
import subprocess
import sys
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Dict, List


# ---------------------------------------------------------------------------
# lark-cli 封装
# ---------------------------------------------------------------------------

def run_lark_cli(args: list, timeout: int = 120) -> dict:
    """调用 lark-cli 并返回 JSON。"""
    cmd = ["lark-cli"] + args
    # 确保 json 输出
    if "--format" not in args:
        cmd += ["--format", "json"]

    result = subprocess.run(cmd, capture_output=True, text=True, timeout=timeout)
    if result.returncode != 0:
        raise RuntimeError(
            f"lark-cli failed (exit {result.returncode}):\n"
            f"  cmd: {' '.join(cmd)}\n"
            f"  stderr: {result.stderr.strip()}"
        )
    try:
        raw = json.loads(result.stdout)
    except json.JSONDecodeError:
        raise RuntimeError(
            f"lark-cli returned non-JSON:\n  stdout: {result.stdout[:500]}"
        )
    # lark-cli api 返回原始 Lark 响应，可能含 code/msg/data 包装
    if isinstance(raw, dict) and "code" in raw and "data" in raw:
        if raw["code"] != 0:
            raise RuntimeError(f"Lark API error: code={raw['code']} msg={raw.get('msg')}")
        return raw["data"]
    return raw


def list_drive_folder(folder_token: str, page_token: str = "", depth: int = 0) -> dict:
    """列出云盘文件夹内容（单页）。"""
    if depth == 0:
        url = f"/open-apis/drive/v1/files?folder_token={folder_token}&page_size=50"
    else:
        url = f"/open-apis/drive/explorer/v2/folder/{folder_token}/children?page_size=50"
        
    if page_token:
        url += f"&page_token={page_token}"
    return run_lark_cli(["api", "GET", url])

# ---------------------------------------------------------------------------
# 遍历逻辑
# ---------------------------------------------------------------------------

def walk_drive_folder(folder_token: str, parent_path: str = "", depth: int = 0) -> List[Dict[str, Any]]:
    """递归遍历云盘文件夹，返回文件列表。

    飞书文件夹结构（非均匀，不能只靠倒数第 N 层判断语义）：

    价值投资/                              ← depth 0: 根入口
    └── 业务组/                            ← depth 1: 业务/投资标的组
        ├── 公司A/                         ← depth 2: 公司
        │   ├── 简报/                      ← depth 3: doc_type 目录
        │   │   └── file.pdf               ← depth 4: 文件
        │   └── 招股书&年报&业绩公告/       ← depth 3: 混合 doc_type 目录
        │       └── file.pdf
        ├── 竞品B/                         ← depth 2: 公司
        │   └── ...
        └── 纪要合集/                      ← depth 2: 特殊（反转结构）
            ├── 公司A/                     ← depth 3: 公司（反转）
            │   ├── 纪要文件               ← depth 4: 文件（直接）
            │   └── 业绩会/                ← depth 4: 子分类目录
            │       └── file.pdf           ← depth 5: 文件

    因此 Stage 1 不做语义判断，只记录完整路径段，由 Stage 4 根据
    路径段 + companies.json + doc_types.json 做分类。
    """
    all_files: List[Dict[str, Any]] = []
    page_token = ""

    while True:
        data = list_drive_folder(folder_token, page_token, depth)
        
        if depth == 0:
            items = data.get("files", [])
        else:
            children_dict = data.get("children", {})
            items = list(children_dict.values()) if isinstance(children_dict, dict) else data.get("files", [])

        for item in items:
            item_type = item.get("type", "")
            name = item.get("name", "")

            if item_type == "folder":
                sub_token = item.get("token", "")
                if sub_token:
                    sub_path = f"{parent_path}{name}/"
                    all_files.extend(walk_drive_folder(sub_token, sub_path, depth + 1))
            else:
                # 记录完整路径段，不预判语义
                path_segments = [s for s in parent_path.split("/") if s]
                item["_feishu_path"] = parent_path
                item["_feishu_path_segments"] = path_segments
                item["_depth"] = depth
                all_files.append(item)

        if depth == 0:
            has_more = data.get("has_more", False)
            page_token = data.get("page_token", "")
        else:
            has_more = data.get("hasMore", data.get("has_more", False))
            page_token = data.get("nextPageToken", data.get("page_token", ""))
            
        if not has_more:
            break

    return all_files


def batch_fetch_metadata(items: List[dict]) -> None:
    """使用 batch_query API 获取文件元数据（创建时间、修改时间等），补充到 item 中。"""
    # 过滤出需要获取元数据的文件（排除 depth=0 时已有的文件）
    files_to_query = [it for it in items if "modified_time" not in it and "edit_time" not in it and it.get("type") != "folder"]
    if not files_to_query:
        return

    # batch_query 每次最多支持 200 个，这里保守用 50 个分批
    chunk_size = 50
    for i in range(0, len(files_to_query), chunk_size):
        chunk = files_to_query[i:i+chunk_size]
        request_docs = []
        for it in chunk:
            request_docs.append({
                "doc_token": it.get("token", ""),
                "doc_type": it.get("type", "")
            })
        
        payload = {"request_docs": request_docs}
        cmd = ["api", "POST", "/open-apis/drive/v1/metas/batch_query", "--data", json.dumps(payload)]
        try:
            res = run_lark_cli(cmd)
            metas = res.get("metas", [])
            meta_map = {m.get("doc_token"): m for m in metas}
            
            for it in chunk:
                token = it.get("token", "")
                if token in meta_map:
                    it["modified_time"] = meta_map[token].get("latest_modify_time", "")
                    it["created_time"] = meta_map[token].get("create_time", "")
        except Exception as e:
            print(f"Warning: batch_query metadata failed for chunk starting at {i}: {e}", file=sys.stderr)

# ---------------------------------------------------------------------------
# Manifest 生成
# ---------------------------------------------------------------------------

def load_state(state_path: Path) -> Dict[str, dict]:
    """加载 doc_states.jsonl，返回 {doc_token: record} 字典。"""
    states: Dict[str, dict] = {}
    if state_path.exists():
        with state_path.open("r", encoding="utf-8") as f:
            for line in f:
                line = line.strip()
                if line:
                    record = json.loads(line)
                    key = record.get("doc_token") or record.get("token") or record.get("file_token", "")
                    if key:
                        states[key] = record
    return states


def normalize_drive_item(item: dict, batch_id: str, existing_states: Dict[str, dict]) -> dict:
    """将 drive API 返回的文件条目转为 manifest 记录。"""
    token = item.get("token", "")
    name = item.get("name", "")
    file_type = item.get("type", "")
    modified = item.get("modified_time", "") or item.get("edit_time", "")
    created = item.get("created_time", "") or item.get("create_time", "")

    # 增量判断
    prev = existing_states.get(token, {})
    prev_modified = prev.get("updated_at", "")
    if prev_modified and prev_modified == modified and prev.get("stage") == "archived":
        stage = "skipped_unchanged"
    else:
        stage = "inventoried"

    return {
        "batch_id": batch_id,
        "file": f"{token}_{sanitize_filename(name)}",
        "original_name": name,
        "doc_token": token,
        "file_type": map_file_type(file_type, name),
        "created_at": created,
        "updated_at": modified,
        "feishu_path": item.get("_feishu_path", ""),
        "feishu_path_segments": item.get("_feishu_path_segments", []),
        "depth": item.get("_depth", 0),
        "source_type": "drive",
        "stage": stage,
    }

# ---------------------------------------------------------------------------
# 工具函数
# ---------------------------------------------------------------------------

def sanitize_filename(name: str) -> str:
    """将中文/特殊字符文件名转为安全 ASCII 形式。"""
    # 去掉扩展名后做转换，再加回
    stem, _, ext = name.rpartition(".")
    if not stem:
        stem = name
        ext = ""

    # 简单转换：保留字母数字下划线，其余用下划线替代
    safe = re.sub(r"[^\w\-.]", "_", stem).strip("_")
    if not safe:
        safe = hashlib.md5(name.encode()).hexdigest()[:12]

    return f"{safe}.{ext}" if ext else safe


def map_file_type(drive_type: str, filename: str) -> str:
    """根据 drive API 的 type 字段和文件名推断文件类型。"""
    type_map = {
        "doc": "doc",
        "docx": "docx",
        "sheet": "sheet",
        "bitable": "bitable",
        "mindnote": "mindnote",
        "slides": "slides",
        "file": filename.rsplit(".", 1)[-1].lower() if "." in filename else "unknown",
    }
    return type_map.get(drive_type, drive_type or "unknown")


def extract_folder_token(source: str) -> str:
    """从 URL 或纯 token 中提取 folder_token。"""
    # URL 形式：https://xxx.feishu.cn/drive/folder/xxxToken
    m = re.search(r"folder/([A-Za-z0-9]+)", source)
    if m:
        return m.group(1)
    # 纯 token
    return source


# ---------------------------------------------------------------------------
# 主流程
# ---------------------------------------------------------------------------

def parse_args() -> argparse.Namespace:
    p = argparse.ArgumentParser(description="Stage 1: Inventory — 遍历飞书并生成 manifest")
    p.add_argument("--workspace", required=True, help="Agent workspace 绝对路径")
    p.add_argument("--source", help="云盘文件夹 token 或 URL")
    p.add_argument("--batch-id", help="批次 ID（默认自动生成 YYYYMMDD-HHmmss）")
    return p.parse_args()


def main() -> int:
    args = parse_args()
    workspace = Path(args.workspace).expanduser().resolve()
    batch_id = args.batch_id or datetime.now(timezone.utc).strftime("%Y%m%d-%H%M%S")

    if not args.source:
        print("错误：必须指定 --source（云盘文件夹）", file=sys.stderr)
        return 1

    # 确保目录
    staging_dir = workspace / "lark_sync" / "staging"
    staging_dir.mkdir(parents=True, exist_ok=True)
    (workspace / "lark_sync" / "state").mkdir(parents=True, exist_ok=True)
    (workspace / "lark_sync" / "logs").mkdir(parents=True, exist_ok=True)

    # 加载历史状态
    state_path = workspace / "lark_sync" / "state" / "doc_states.jsonl"
    existing_states = load_state(state_path)

    # 遍历
    records: List[dict] = []
    try:
        if args.source:
            folder_token = extract_folder_token(args.source)
            print(f"遍历云盘文件夹: {folder_token}", file=sys.stderr)
            items = walk_drive_folder(folder_token)
            batch_fetch_metadata(items)
            records = [normalize_drive_item(it, batch_id, existing_states) for it in items]
    except Exception as e:
        # 遍历失败，生成失败 manifest
        error_record = {
            "batch_id": batch_id,
            "stage": "failed_inventory",
            "error": str(e),
        }
        records = [error_record]

    # 写入 manifest
    manifest_path = staging_dir / f"{batch_id}_manifest.jsonl"
    with manifest_path.open("w", encoding="utf-8") as f:
        for r in records:
            f.write(json.dumps(r, ensure_ascii=False) + "\n")

    # 统计
    from collections import Counter
    counts = Counter(r.get("stage", "") for r in records)

    receipt = {
        "stage": "stage1_inventory",
        "ok": "failed_inventory" not in counts or counts["failed_inventory"] < len(records),
        "batch_id": batch_id,
        "total": len(records),
        "inventoried": counts.get("inventoried", 0),
        "skipped_unchanged": counts.get("skipped_unchanged", 0),
        "failed_inventory": counts.get("failed_inventory", 0),
        "manifest_path": str(manifest_path),
        "next_stage_allowed": counts.get("failed_inventory", 0) == 0 or counts.get("inventoried", 0) > 0,
    }

    print(json.dumps(receipt, ensure_ascii=False, indent=2))
    return 0 if receipt["ok"] else 2


if __name__ == "__main__":
    sys.exit(main())
