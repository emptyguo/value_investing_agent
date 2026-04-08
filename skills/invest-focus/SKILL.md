---
name: invest-focus
description: 管理 Active Subject（活跃公司主题）切换，确保上下文隔离和状态持久化
---

# Invest Focus Skill

## 核心职责

管理对话中的公司主题切换，防止不同公司的分析判断互相污染。
AGENTS.md 已包含 2 条核心规则，本文档提供完整执行协议。

## 触发条件

用户话题从公司 A 切换到公司 B 时触发。

## 执行步骤

### Step 1：持久化当前主题

将当前关于公司 A 的未保存结论写入 views/{company_a}.md。确认无遗漏后进入下一步。

### Step 2：记录切换日志

在 memory/YYYY-MM-DD.md 中写入：

## [HH:MM] 主题切换: {company_a} → {company_b}
- 原因: {用户为什么切换}
- company_a 状态: {切换时的结论/待验证事项}

### Step 3：上下文隔离

- 读取 `{OPENCLAW_DATA_DIR}/references/companies.json`，查找公司 B 的 `industry_id` 字段
- 加载 `domains/{industry_id}.md`（如 `domains/music.md`）和 `views/{company_b}.md`
- 向用户声明："当前聚焦：{company_b}({symbol})"
- 切换后不引用公司 A 的数据/判断，除非用户明确要求跨公司比较

## 输出校验

产出任何分析前自查：
1. 本段内容涉及的公司是否是当前 Active Subject？
2. 引用的数据是否属于当前公司？
3. 竞品对比时，主视角是否锁定在 Active Subject？

校验失败 → 停止输出并修正。

## 日记隔离

memory/YYYY-MM-DD.md 中同一天讨论多个公司时，必须用标题分隔：

## [09:30] tme — QQ音乐付费率分析
（tme 相关内容）

## [14:00] 主题切换: tme → midea
（切换记录）

## [14:05] midea — 2025年报阅读笔记
（midea 相关内容）