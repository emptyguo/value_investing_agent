#!/usr/bin/env python3
"""上传一个本地文件到飞书云盘文件夹。

用法:
  python3 lark_upload.py <本地文件> [--folder <token>] [--name <飞书侧文件名>] [--dry-run]

依赖: lark-cli 已安装并完成认证 (lark-cli auth login)。

默认 folder token 是 mifeng_corporate_hub 的统一上传目录。
"""

import argparse
import subprocess
import sys
from pathlib import Path

DEFAULT_FOLDER_TOKEN = "Aw6JfcD3jlHmV3dNJIucD6dSnLg"
MAX_SIZE_BYTES = 20 * 1024 * 1024  # lark-cli drive +upload 上限


def main() -> int:
    p = argparse.ArgumentParser(description="上传单个本地文件到飞书云盘")
    p.add_argument("file", help="本地文件路径")
    p.add_argument("--folder", default=DEFAULT_FOLDER_TOKEN,
                   help=f"目标文件夹 token (默认 {DEFAULT_FOLDER_TOKEN})")
    p.add_argument("--name", default=None,
                   help="飞书侧文件名 (默认沿用本地文件名)")
    p.add_argument("--dry-run", action="store_true",
                   help="只打印命令,不实际上传")
    args = p.parse_args()

    src = Path(args.file).expanduser().resolve()
    if not src.is_file():
        print(f"错误: 文件不存在或不是普通文件: {src}", file=sys.stderr)
        return 2
    if src.stat().st_size > MAX_SIZE_BYTES:
        print(f"错误: 文件超过 20MB 上限 ({src.stat().st_size} bytes)", file=sys.stderr)
        return 2

    # lark-cli 要求 --file 是相对 cwd 的路径,所以 cd 到文件所在目录
    cmd = [
        "lark-cli", "drive", "+upload",
        "--file", src.name,
        "--folder-token", args.folder,
    ]
    if args.name:
        cmd += ["--name", args.name]
    if args.dry_run:
        cmd += ["--dry-run"]

    print(f"执行: (cwd={src.parent}) {' '.join(cmd)}", file=sys.stderr)
    result = subprocess.run(cmd, capture_output=True, text=True, cwd=str(src.parent))
    if result.stdout:
        print(result.stdout)
    if result.returncode != 0:
        print(f"上传失败: {result.stderr.strip()}", file=sys.stderr)
        return result.returncode
    return 0


if __name__ == "__main__":
    sys.exit(main())
