#!/usr/bin/env python3
"""Stage 2: Download — 根据 manifest 批量下载飞书文件到 staging

用法：
  python3 lark_download.py --workspace /path/to/workspace --batch-id 20260401-154600

依赖：lark-cli 已安装并完成认证（lark-cli auth login --recommend）
"""

import argparse
import json
import subprocess
import sys
from datetime import datetime, timezone
from pathlib import Path
from typing import List


# ---------------------------------------------------------------------------
# lark-cli 封装
# ---------------------------------------------------------------------------

def download_drive_file(file_token: str, output_path: str, timeout: int = 300) -> dict:
    """下载云盘文件（PDF/Word/Excel 等二进制文件）。"""
    out_p = Path(output_path)
    cmd = [
        "lark-cli", "drive", "+download",
        "--file-token", file_token,
        "--output", out_p.name,
        "--overwrite"
    ]
    result = subprocess.run(cmd, capture_output=True, text=True, timeout=timeout, cwd=str(out_p.parent))
    if result.returncode != 0:
        raise RuntimeError(f"drive download failed: {result.stderr.strip()}")
    try:
        return json.loads(result.stdout)
    except json.JSONDecodeError:
        # 有些命令成功但不输出 JSON
        return {"saved_path": output_path}


def fetch_doc_as_markdown(doc_ref: str, timeout: int = 60) -> str:
    """读取飞书文档并返回 Markdown 内容。"""
    cmd = ["lark-cli", "docs", "+fetch", "--doc", doc_ref]
    result = subprocess.run(cmd, capture_output=True, text=True, timeout=timeout)
    if result.returncode != 0:
        raise RuntimeError(f"docs fetch failed: {result.stderr.strip()}")
    return result.stdout


def export_wiki_node(node_token: str, timeout: int = 120) -> str:
    """导出知识库节点为 Markdown。先获取节点信息，再按类型处理。"""
    # wiki 节点可以直接用 docs +fetch
    return fetch_doc_as_markdown(node_token, timeout)


# ---------------------------------------------------------------------------
# 主流程
# ---------------------------------------------------------------------------

def load_manifest(path: Path) -> List[dict]:
    rows: List[dict] = []
    with path.open("r", encoding="utf-8") as f:
        for line in f:
            line = line.strip()
            if line:
                rows.append(json.loads(line))
    return rows


def save_manifest(path: Path, rows: List[dict]) -> None:
    with path.open("w", encoding="utf-8") as f:
        for row in rows:
            f.write(json.dumps(row, ensure_ascii=False) + "\n")


def parse_args() -> argparse.Namespace:
    p = argparse.ArgumentParser(description="Stage 2: Download — 批量下载飞书文件")
    p.add_argument("--workspace", required=True, help="Agent workspace 绝对路径")
    p.add_argument("--batch-id", required=True, help="批次 ID")
    return p.parse_args()


def is_text_doc(file_type: str) -> bool:
    """判断是否为飞书原生文档（可直接导出为 Markdown）。"""
    return file_type in ("doc", "docx", "wiki")


def main() -> int:
    args = parse_args()
    workspace = Path(args.workspace).expanduser().resolve()
    batch_id = args.batch_id

    manifest_path = workspace / "lark_sync" / "staging" / f"{batch_id}_manifest.jsonl"
    if not manifest_path.exists():
        print(f"错误：manifest 不存在: {manifest_path}", file=sys.stderr)
        return 1

    rows = load_manifest(manifest_path)
    download_dir = workspace / "lark_sync" / "staging" / "downloads" / batch_id
    download_dir.mkdir(parents=True, exist_ok=True)

    now = datetime.now(timezone.utc).isoformat()
    stats = {"downloaded": 0, "skipped_unchanged": 0, "failed_download": 0}

    for row in rows:
        stage = row.get("stage", "")

        # 只处理 inventoried 记录
        if stage != "inventoried":
            if stage in stats:
                stats[stage] = stats.get(stage, 0) + 1
            continue

        token = row.get("doc_token") or row.get("obj_token", "")
        filename = row.get("file", "unknown")
        file_type = row.get("file_type", "")
        source_type = row.get("source_type", "drive")

        if not token:
            row["stage"] = "failed_download"
            row["error"] = "missing doc_token/obj_token"
            stats["failed_download"] += 1
            continue

        try:
            print(f"Downloading: {filename} ({file_type}) ...", flush=True)
            if is_text_doc(file_type):
                # 飞书原生文档 → 直接导出 Markdown
                md_filename = Path(filename).stem + ".md"
                output_path = download_dir / md_filename

                if source_type == "wiki":
                    content = export_wiki_node(token)
                else:
                    content = fetch_doc_as_markdown(token)

                output_path.write_text(content, encoding="utf-8")

                row["download_path"] = f"downloads/{batch_id}/{md_filename}"
                row["abs_download_path"] = str(output_path)
                row["download_format"] = "markdown"
            else:
                # 二进制文件（PDF/Word/Excel 等） → 下载原文件
                output_path = download_dir / filename
                download_drive_file(token, str(output_path))

                row["download_path"] = f"downloads/{batch_id}/{filename}"
                row["abs_download_path"] = str(output_path)
                row["download_format"] = "binary"

            row["stage"] = "downloaded"
            row["downloaded_at"] = now
            stats["downloaded"] += 1

        except Exception as e:
            row["stage"] = "failed_download"
            row["error"] = str(e)
            stats["failed_download"] += 1
            print(f"  Error: {e}")

        # 增量保存 manifest，防止中途崩溃丢失状态
        save_manifest(manifest_path, rows)

    # 回写 manifest (最后兜底)
    save_manifest(manifest_path, rows)

    receipt = {
        "stage": "stage2_download",
        "ok": True,
        "batch_id": batch_id,
        "downloaded": stats["downloaded"],
        "skipped_unchanged": stats["skipped_unchanged"],
        "failed_download": stats["failed_download"],
        "next_stage_allowed": stats["downloaded"] > 0 or stats["skipped_unchanged"] > 0,
    }

    if stats["failed_download"] > 0 and stats["downloaded"] == 0:
        receipt["ok"] = False
        receipt["next_stage_allowed"] = stats["skipped_unchanged"] > 0

    print(json.dumps(receipt, ensure_ascii=False, indent=2))
    return 0 if receipt["ok"] else 2


if __name__ == "__main__":
    sys.exit(main())
