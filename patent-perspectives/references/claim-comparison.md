# 权利要求要素对照与文献版本

需要比较技术要素或同一申请的不同公开号时读取。宿主先阅读、选择可比对象并写解释，`scripts/claim_comparison.py` 校验原文身份、引文和权项，页面不自动推导侵权、有效性或保护范围扩张/缩小。

## 使用位置与资料边界

权利要求要素对照在专利工程师视角前置，其他角色可按需查看。三个角色的导航、直达、首次渲染和原文操作保持一致；保留同件、同版本、权项及引文定位，未披露与未取得分别表达。

每列使用同一申请的一份明确公开号、版本的完整合格权利要求。跨申请比较用 `mode:applications`；同一申请的不同公开号比较用 `mode:versions`。同族关系不能替代同一申请身份。原文尚未取得的版本只能说明缺失，不生成版本变化结论。已取得但不完整或被拒绝的正文不能作为可比较的完整文本。

`not_disclosed` 是宿主实际读完整份所选权利要求后的有限陈述，不能解释成说明书、全部实施方式或其他专利中不存在。语义判断由宿主负责；字符串校验仅证明引文与文献相符。

## report-context.json 输入

在已有报告上下文中增加可选的 `claim_comparisons` 数组；省略或填空数组时，页面不出现对照入口。每组结构如下：

| 字段 | 要求 |
|---|---|
| `id, title, scope, selection_reason` | 非空字符串；组 ID 在本次报告唯一；范围和选案理由使用有依据的完整句子 |
| `mode` | `applications`（默认）或 `versions` |
| `summary` | 可选的技术说明文字，不以简单文本差异直接推断法律效果 |
| `cases` | 至少两列；每项 `id, label, application_id, document_id`，ID 在组内唯一，来自实际报告数据 |
| 缺失正文的列 | 不提供 `document_id`，改填已在该申请著录记录中的 `publication_number`；该公开号不能已有可用完整权利要求 |
| `rows` | 非空要素数组；每项 `id, label, category, question, cells`；行 ID 在组内唯一 |
| `category` | 阅读筛选标签，可用 `components, position, connection, process, conditions, claim_scope, other`，或本次实际技术分类文字 |
| `cells` | 每行恰好覆盖每一列；每项 `case_id, state, text, evidence_ids` |
| `state:disclosed` | 必须有同列、同文献版本的现有 `evidence_ids`；不是在对照输入里新编引文 |
| `state:not_disclosed` | 仅限有完整正文的列；增加 `reviewed_claim_numbers`，完整列出实际已读的全部权项号；可附相关上下文证据 |
| `state:not_acquired` | 仅用于缺正文的列；`evidence_ids` 留空；解释资料缺口，不作技术否定 |

所引 evidence 必须绑定该申请的 `document_id`、准确公开号、版本、权项号及 Python Unicode 字符区间；`quote` 必须与原文片段完全一致。程序重新解析原始权项编号并校验区间，不能用其他权项中的相同文字顶替。请先按既有数据契约导入文献、阅读和证据，再编写对照。

以下为**合成结构示例**，不是实际专利或可直接替换 ID 的企业数据：

```json
{
  "claim_comparisons": [{
    "id": "synthetic-optical-comparison",
    "mode": "applications",
    "title": "合成光学样例：镜片的支撑部件",
    "scope": "仅比较两份合成完整权利要求，不表示真实专利结论。",
    "selection_reason": "两份文本都描述镜片安装，适合演示同类要素的对照。",
    "cases": [
      {"id": "column-a", "label": "合成方案甲", "application_id": "synthetic-app-a", "document_id": "synthetic-doc-a"},
      {"id": "column-b", "label": "合成方案乙", "application_id": "synthetic-app-b", "document_id": "synthetic-doc-b"}
    ],
    "rows": [{
      "id": "lens-support", "category": "components", "label": "镜片支撑部件",
      "question": "镜片安装在哪个部件上？",
      "cells": [
        {"case_id": "column-a", "state": "disclosed", "text": "合成方案甲的镜片安装在壳体内的支架上。", "evidence_ids": ["synthetic-evidence-a"]},
        {"case_id": "column-b", "state": "disclosed", "text": "合成方案乙的镜片由安装座承托。", "evidence_ids": ["synthetic-evidence-b"]}
      ]
    }]
  }]
}
```

## 生成和验收

仍通过 `render --report-context FILE` 生成报告。数据准备层验证对照后输出 `data/claim-comparisons.js`；模板加载 `ip-comparison.js/.css`。同件文献文字和引文随离线报告保存，原文弹窗显示完整权利要求、公开号、版本与高亮位置。数据复用包同时保留报告上下文和证据 ID，不能只留下表格截图。

检查每格的技术说明与所引权项相符，明确必要部件、连接、动作和条件，保留从属限定。分别验证不同申请比较、同申请版本比较、缺正文、已读未披露、角色切换、直接链接、窄屏与离线引文定位。对照主题保留自己的固定范围，不因页面其他筛选悄悄改写要素结论。
