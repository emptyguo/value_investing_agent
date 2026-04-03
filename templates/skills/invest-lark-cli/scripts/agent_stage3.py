#!/usr/bin/env python3
"""Stage 3: Parse — 对已下载文件做内容转换

用法：
  python3 agent_stage3.py --workspace /path/to/workspace --batch-id 20260401-154600

修复记录（2026-04-02）：
  - 解析后主动扫描 output-dir 查找实际生成的 .md 文件，不再假设文件名
  - 超时从 300s 提升到 600s，大型财报 PDF 需要更多时间
  - 每处理一个文件就增量保存 manifest，防止中途崩溃丢失进度
"""

import argparse
import json
import subprocess
import sys
from datetime import datetime, timezone
from pathlib import Path


def load_manifest(path: Path) -> list:
    rows = []
    with path.open("r", encoding="utf-8") as f:
        for line in f:
            if line.strip():
                rows.append(json.loads(line))
    return rows


def save_manifest(path: Path, rows: list) -> None:
    with path.open("w", encoding="utf-8") as f:
        for row in rows:
            f.write(json.dumps(row, ensure_ascii=False) + "\n")


def find_parsed_md(parsed_dir: Path, stem: str) -> Path | None:
    """在 parsed_dir 中查找解析产出的 .md 文件。

    优先精确匹配 {stem}.md，否则模糊匹配包含 stem 前缀的 .md 文件。
    """
    exact = parsed_dir / f"{stem}.md"
    if exact.exists():
        return exact

    # opendataloader_pdf 可能截断或修改文件名，用前缀匹配
    # stem 可能很长（{token}_{sanitized_name}），取前 20 字符做前缀
    prefix = stem[:20]
    candidates = sorted(parsed_dir.glob(f"{prefix}*.md"), key=lambda p: p.stat().st_mtime, reverse=True)
    if candidates:
        return candidates[0]

    return None


def parse_args() -> argparse.Namespace:
    p = argparse.ArgumentParser(description="Stage 3: Parse — 内容转换")
    p.add_argument("--workspace", required=True, help="Agent workspace 绝对路径")
    p.add_argument("--batch-id", required=True, help="批次 ID")
    return p.parse_args()


def main() -> int:
    args = parse_args()
    workspace = Path(args.workspace).expanduser().resolve()
    batch_id = args.batch_id

    manifest_path = workspace / "lark_sync" / "staging" / f"{batch_id}_manifest.jsonl"
    if not manifest_path.exists():
        print(f"错误：manifest 不存在: {manifest_path}", file=sys.stderr)
        return 1

    parsed_dir = workspace / "lark_sync" / "staging" / "parsed" / batch_id
    parsed_dir.mkdir(parents=True, exist_ok=True)

    rows = load_manifest(manifest_path)
    now = datetime.now(timezone.utc).isoformat()
    stats = {"parsed": 0, "failed_parse": 0, "failed_download": 0, "skipped_unchanged": 0}

    for idx, row in enumerate(rows):
        stage = row.get("stage", "")
        if stage != "downloaded":
            stats[stage] = stats.get(stage, 0) + 1
            continue

        file_type = row.get("file_type", "")
        dl_format = row.get("download_format", "")
        abs_download_path = row.get("abs_download_path", "")

        if dl_format == "markdown":
            # 飞书原生文档已在 Stage 2 导出为 Markdown
            row["stage"] = "parsed"
            row["parse_method"] = "pre_converted"
            row["parsed_path"] = row.get("download_path")
            row["abs_parsed_path"] = abs_download_path
            row["parsed_at"] = now
            stats["parsed"] += 1

        elif dl_format == "binary" and file_type == "pdf":
            try:
                # 优先从当前 workspace 的相对路径寻找解析脚本
                pdf_script = workspace / "skills/invest-pdf-parser/scripts/parse_pdf.py"
                if not pdf_script.exists():
                    # 兜底：线上标准的全局路径
                    pdf_script = Path("/root/.openclaw/workspace/skills/invest-pdf-parser/scripts/parse_pdf.py")
                
                if not Path(abs_download_path).exists():
                    raise FileNotFoundError(f"源文件不存在: {abs_download_path}")

                cmd = ["python3", str(pdf_script), "--input", abs_download_path, "--output-dir", str(parsed_dir)]
                base_name = Path(abs_download_path).stem
                print(f"[{idx+1}/{len(rows)}] Parsing PDF: {row.get('original_name', base_name)}", flush=True)

                result = subprocess.run(cmd, capture_output=True, text=True, timeout=600)
                if result.returncode != 0:
                    raise RuntimeError(f"PDF parse exit={result.returncode}: {result.stderr.strip() or result.stdout.strip()}")

                # 主动查找实际生成的 .md 文件，不假设文件名
                md_path = find_parsed_md(parsed_dir, base_name)
                if md_path is None:
                    raise RuntimeError(f"parse_pdf.py 返回成功但未找到 .md 文件 (stem={base_name})")

                row["stage"] = "parsed"
                row["parse_method"] = "pdf_parser"
                row["parsed_path"] = f"parsed/{batch_id}/{md_path.name}"
                row["abs_parsed_path"] = str(md_path)
                row["parsed_at"] = now
                stats["parsed"] += 1

            except subprocess.TimeoutExpired:
                row["stage"] = "failed_parse"
                row["error"] = f"PDF 解析超时 (>600s): {abs_download_path}"
                stats["failed_parse"] += 1
            except Exception as e:
                row["stage"] = "failed_parse"
                row["error"] = str(e)
                stats["failed_parse"] += 1

        else:
            # 其他二进制文件，无解析器
            row["stage"] = "parsed"
            row["parse_method"] = "copy"
            row["parsed_path"] = ""
            row["abs_parsed_path"] = ""
            row["parsed_at"] = now
            stats["parsed"] += 1

        # 增量保存：每处理一个文件就写盘，防止中途崩溃丢失进度
        save_manifest(manifest_path, rows)

    receipt = {
        "stage": "stage3_parse",
        "ok": stats["failed_parse"] == 0,
        "batch_id": batch_id,
        "parsed": stats["parsed"],
        "failed_parse": stats["failed_parse"],
        "failed_download": stats.get("failed_download", 0),
        "skipped_unchanged": stats.get("skipped_unchanged", 0),
        "next_stage_allowed": stats["parsed"] > 0,
    }

    print(json.dumps(receipt, indent=2, ensure_ascii=False))
    return 0 if receipt["ok"] else 2


if __name__ == "__main__":
    sys.exit(main())
