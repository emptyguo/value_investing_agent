---
name: invest-doc-router
description: 当用户上传公司相关文件或链接时，按公司、文档类型和可信度归档到公司资料库
---

# Invest Doc Router Skill

## 核心职责

归档技能——将用户上传的外部文件/链接统一归档到公司资料库。
**只做**：归档、分类、标记可信度、记录时间线。**绝不做**：分析、评价、产出投资结论。

## 关键路径

| 用途 | 路径 |
|---|---|
| 公司配置 | `{OPENCLAW_DATA_DIR}/references/companies.json` |
| 分类配置 | `{OPENCLAW_DATA_DIR}/references/doc_types.json` |
| 公司资料库 | `{OPENCLAW_DATA_DIR}/companies/{company}/` |
| 目录结构与可信度 | 读取 `references/archive-structure.md` |

## 路径构造规则（强制）

```
源文件: {OPENCLAW_DATA_DIR}/companies/{company}/{doc_types.json 的 dir 字段}/source/{filename}
解析后: {OPENCLAW_DATA_DIR}/companies/{company}/{doc_types.json 的 dir 字段}/{filename}.md
```

- `{company}` = `companies.json` 中的 `id`（英文小写）
- `{dir}` = `doc_types.json` 中匹配条目的 `dir` 字段
- **严禁使用中文目录名**，目录名全部由 `doc_types.json` 的 `dir` 字段决定

## 输入

- `company`: 公司标识（必须在 `companies.json` 中存在）
- `type`: `file` / `link` / `text`
- `doc_type`: 分类标识或 `auto`（自动识别）
- `title`: 文档标题
- `file-path`（type=file 时）/ `url`（type=link 时）

## 自动分类（doc_type=auto）

读取 `doc_types.json`，遍历每条规则的 `keywords` 匹配文档标题和内容，命中则归入该 `dir`。无法匹配时使用 `default_doc_type`。

## 归档流程（type=file）

1. 读取 `references/archive-structure.md` 确认目录结构和可信度等级
2. 确定 `doc_type`，从 `doc_types.json` 获取 `dir` 字段
3. 复制源文件到 `{dir}/source/{原始文件名}`
4. 如果是 PDF → 调用 `invest-pdf-parser`，输出 `.md` 到 `{dir}/{文件名}.md`
5. 追加 `timeline.md`（含可信度等级、源文件路径、解析文件路径）
6. 追加 `intake_log.jsonl`

## 归档流程（type=link/text）

1. 确定 `doc_type`
2. 写结构化 `.json` 到 `{dir}/`
3. 更新 `timeline.md` 和 `intake_log.jsonl`

## 碎片化/非公开情报

无法验证来源或属于市场传闻的情报：降权归档到 `unofficial/`，标记 L5 可信度。
归档后提示用户："该情报可信度为 L5，建议交叉验证。是否要用 invest-analysis 评估？"

## 归档完成后

单文件归档：提示用户"已归档到 {path}。是否要用 invest-analysis 碰撞现有判断？"
批量归档：所有文件归档完成后**统一汇总提示一次**，列出归档清单，再问是否分析。禁止每个文件弹一次。
用户确认 → 引导触发 `invest-analysis`。用户拒绝 → 结束。

## 硬约束

1. 路径必须由 `doc_types.json` 的 `dir` 字段决定，严禁中文目录名
2. 源文件必须保留在 `source/` 子目录
3. 只归档，不分析；只记录，不写投资结论
4. 保留原始格式，不篡改源文件
5. PDF 归档后自动触发解析
6. 非公开信息必须标记来源和可信度说明
