---
name: invest-pdf-parser
description: 将复杂的投资研报、招股书、财报 PDF 解析为 Agent 可精确处理的高质量 Markdown，支持复杂表格和图片。
---

# Invest PDF Parser Skill

## 核心职责

解决大模型无法直接精准阅读复杂 PDF 的问题。通过高保真版面还原生成机器可读 Markdown。
**只做**：PDF 转 Markdown。**绝不做**：内容总结、提炼、评价或归档。

## 执行步骤

### 1. 选择解析模式

| 文档类型 | 模式 | 命令 |
|---|---|---|
| 纯文字研报、新闻稿 | 基础模式（快） | `python3 {baseDir}/scripts/parse_pdf.py --input "路径.pdf"` |
| 含复杂表格的财报、年报、招股书 | 混合 AI 模式（慢） | `python3 {baseDir}/scripts/parse_pdf.py --input "路径.pdf" --hybrid` |

### 2. 输出路径

**由 invest-doc-router 触发**：源 PDF 在 `source/`，输出 `.md` 到父目录：
```bash
python3 {baseDir}/scripts/parse_pdf.py \
  --input "data/companies/tme/sellside/briefings/source/tme_4q25.pdf" \
  --output-dir "data/companies/tme/sellside/briefings/"
```

**由用户直接触发**：在原 PDF 同目录生成同名 `.md`。

### 3. 后续

Agent 将深度阅读和分析施加在生成的 `.md` 文件上，不再读原始 PDF。

## 硬约束

1. 页数 > 5 的 PDF 必须先解析为 `.md`，严禁直接投喂原始 PDF
2. 纯粹转换定位，不做任何内容判断
3. 幂等执行：`.md` 已存在且 PDF 未变化时跳过
4. 错误不阻塞：解析失败记录错误并返回

## 依赖

- Python 包：`opendataloader-pdf`
- 混合模式需后端 hybrid 服务可用
