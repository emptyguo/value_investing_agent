---
name: invest-pdf-parser
description: 将复杂的投资研报、招股书、财报 PDF 解析为 Agent 可精确处理的高质量 Markdown，支持复杂表格和图片。
---

# Invest PDF Parser Skill

## 核心职责

`invest-pdf-parser` 解决**大模型无法直接精准阅读复杂 PDF** 的问题。财报中密集的财务表格、断行和多栏排版会导致纯文本提取出现大量幻觉，通过本技能实现"高保真版面还原 → 机器可读 Markdown"。

**只做**：PDF 转 Markdown（包含结构化 bbox 提取）
**绝不做**：内容总结、提炼、评价或归档

## 触发方式

| 场景 | 触发方 |
|---|---|
| invest-doc-router 归档了 PDF 文件 | doc-router 自动调用 |
| 用户直接发送 PDF 要求阅读 | Agent 主动调用 |
| invest-analysis 需要读取未解析的 PDF | analysis 调用 |

## 执行步骤

### 1. 调用解析命令

- **基础解析模式（极速、适合文字为主的文件）：**

  ```bash
  python3 {baseDir}/scripts/parse_pdf.py --input "/路径/2024年报.pdf"
  ```

- **混合 AI 解析模式（慢、专克复杂财务表格和公式）：**

  ```bash
  python3 {baseDir}/scripts/parse_pdf.py --input "/路径/券商研报.pdf" --hybrid
  ```

### 2. 读取结构化结果

脚本执行完成后，在原 PDF 同目录下生成同名 `.md` 文件：

```
/路径/2024年报.pdf  →  /路径/2024年报.md
```

Agent 应将后续的深度阅读和分析施加在生成的 `.md` 文件上。

## 模式选择建议

| 文档类型 | 建议模式 | 原因 |
|---|---|---|
| 纯文字研报、新闻稿 | 基础模式 | 速度快，文字提取准确 |
| 含复杂表格的财报、年报 | 混合模式 | 表格结构需要 AI 辅助还原 |
| 招股书 | 混合模式 | 多栏排版 + 大量表格 |

## 执行规则

- **强制先解后读**：页数 > 5 的 PDF 必须先解析为 `.md`，严禁直接投喂原始 PDF
- **纯粹转换定位**：本技能只是"高科技 OCR 眼镜"，不做任何内容判断
- **幂等执行**：如果 `.md` 已存在且 PDF 未变化，跳过重复解析
- **错误不阻塞**：解析失败时记录错误并返回，不影响归档流程

## 依赖

- Python 包：`opendataloader-pdf`（需在服务器上预装）
- 混合模式需要后端 hybrid 服务可用
