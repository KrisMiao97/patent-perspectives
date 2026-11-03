# 宿主全文审阅的紧凑输入

`scripts/materialize_review.py` 只将宿主已经选好的原文位置转换为精确证据。宿主仍需按[整篇分析](whole-patent-research.md)读完 `export-work` 提供的主文献及实际尾文，亲自填写主模块、标签、总结、八个技术字段及限制。默认主文献为完整 claims；技术术语、结构、步骤或机制有具体疑问时，才局部补读同 PN description。完整 claims 不可得时用完整 description 回退。工具不生成摘要、归类、技术问题或功效，不调用模型或网络。

此格式减少重复抄录，主文献仍须完整阅读。辅助说明书只记录实际补读的相关区间，不声称全书已读；问题和功效未披露时留空，不为填空额外阅读。`whole_document_review` 和 `tail_check` 是宿主对主文献的明确阅读声明；机械校验可以发现身份、范围和字符串错误，不能证明宿主真正理解了全文，也不能代替独立语义复核。

## 输入

输入可以是一个 JSON 对象、对象数组或 UTF-8 JSONL。每条保留导出的 `application_id`、`document_id`，提供实际 `analysis_author` 和绑定所选原文哈希的 `whole_document_review`。不要自行编造 ID 或将片段阅读记为完整阅读。真实运行不能只提交旧 `read_chunk_ids` 声明；原库旧分段保持不变，工具依据已验证的整篇记录派生兼容完成编号。旧合成测试输入仍可使用原分段格式，不得将真实资料改标测试来跳过要求。

```json
{
  "application_id": "从 export-work 保留原值",
  "document_id": "从 export-work 保留原值",
  "analysis_author": "实际完成整篇分析的负责者标识",
  "whole_document_review": {
    "document_id": "从 export-work 保留原值",
    "source_text_hash": "所选原文的实际哈希",
    "reading_mode": "whole",
    "complete": true,
    "capacity_basis": "说明本件完整材料、必要图片、补查及分析输出可放入当前上下文的实际判断依据"
  },
  "tail_check": {
    "complete": true,
    "quote": "亲自读过并确认完整的原文结尾连续片段，至少十二字符",
    "claim_number": 10
  },
  "primary_module": "宿主根据全文归纳的主模块",
  "tags": ["宿主归纳的标签"],
  "summary": {"text": "宿主撰写的技术总结", "evidence": ["c1"], "kind": "disclosed"},
  "fields": {
    "application_field": [{"text": "原文支持的应用领域", "evidence": ["c1"]}],
    "technical_problem": [],
    "technical_means": [{"text": "宿主理解的技术手段", "evidence": ["c1"]}],
    "components": [{"text": "原文披露的要素", "evidence": ["c1"]}],
    "relationships": [{"text": "原文披露的要素关系", "evidence": ["c1"]}],
    "steps": [],
    "conditions": [{"text": "原文披露的限制条件", "evidence": ["c1"]}],
    "claimed_effects": []
  },
  "evidence": [{"key": "c1", "claim_number": 1}],
  "limitations": ["仅为输入结构示意，须据实际原文填写；未披露的问题、步骤和功效保留为空。"]
}
```

上例是结构示意，不是真实专利分析。说明书的尾段编号使用 `paragraph_number`；权利要求使用 `claim_number`。这些可选尾段编号必须等于所选文本的最后编号。`complete` 没有默认值，必须由宿主确认；若尾句断裂、关键公式或必要图表丢失，不得为通过校验而填 true。实际尾文字符串匹配也不能代替完整性判断，此时按下节提交拒绝记录并补证。

超过本次可可靠处理容量时，仍由同一负责者连续阅读同一任务，`reading_mode` 改为 `continuous`，另填非空 `reason` 和 `read_regions:[{"start":0,"end":实际终点},...]`。区间采用原文 Python Unicode 字符索引，按阅读顺序从0完整覆盖到全文长度；允许相接或必要重叠，不允许缺口、重复或越界。`whole` 模式不填写非空 `read_regions`。两种模式都需要真实尾文检查；同时填写旧 `read_chunk_ids` 时，必须与数据库兼容编号完全一致。

八个字段必须全部出现且值都是数组。原文未披露者填 `[]` 并在 `limitations` 解释，不以 `null`、`{}`、`"unknown"` 或占位发现替代。一个字段可以有多条有证据的发现。总结及每条发现使用 `evidence` 引用本条所选的紧凑 key；禁止预造 `evidence_ids`。`kind` 默认 disclosed；宿主提出 inference 时，另写非空 `basis` 和 `conditions`，工具不会代写推断。

## 选取精确证据

每条证据的 key 是本条唯一的 ASCII 字母、数字、下划线或短横线组合。下列三种位置选择方式只能选一种：

- 说明书段号：`{"key":"p7","paragraph_number":7}`。脚本取该段的完整连续原文并去除首尾空白。
- 权利要求编号：`{"key":"c2","claim_number":2}`。脚本只取已核验原始编号区间中的这一项，不借用其它项的相同文字。
- 明确连续区间：`{"key":"s1","start":100,"end":150,"locator":{"paragraph":"0007"}}`。索引必须是原文的 Python Unicode 字符索引；该段号或 claim_number 必须真实容纳整个区间。没有采用编号定位的说明书区间可用 `{"source_span":true}`，不能随意填未经验证的页码或段号。

选取段或项后，可以加 `quote` 缩短为其中唯一出现的连续原文；空引文、重复引文和来自其它段或项的引文会被拒绝。需要区分重复文字时，使用明确 start/end。自动生成的证据 ID 绑定公开号和所选文本版本，不改变人工结论。

## 按需补读同件说明书

主完整 claims 中的技术术语、组成、关系、步骤或机制不能充分理解时，可选择同一申请、同一公开号、同一原文语言且合格未拒绝的 description。公开与授权文献分别是不同公开号；不能以“同申请”或“同族”为由混用。已完成有效的旧完整 description 分析继续兼容，无需重做。

紧凑输入在主字段外增加：

```json
{
  "support_documents": [
    {"document_id": "实际同 PN 说明书 docid", "read_regions": [{"paragraph_number": 7, "reviewed": true}]}
  ],
  "evidence": [
    {"key": "c1", "claim_number": 1},
    {"key": "p7", "document_id": "实际同 PN 说明书 docid", "paragraph_number": 7, "quote": "实际在该段中唯一出现的连续短引文"}
  ]
}
```

此例只是新增字段示意，需与完整主输入合用。主 `whole_document_review/tail_check` 仍覆盖所有 claims；辅助 `support_documents/read_regions` 只覆盖实际补读的说明书。辅助段落必须真实已读，不能仅因脚本能定位就填 reviewed=true；无段号时用 `start`、`end`、`locator:{"source_span":true}`。辅助读区间不接受 claim_number，不要把说明书段号当成权利要求编号；其重叠或重复区间会被拒绝。源区间按 Python Unicode 字符索引计算。

脚本把上述读段解析成该 description 自身的精确 start/end/locator，记录原文哈希及 reading_scope=selected_regions。每条辅助 evidence 保留独立 document_id、版本、语言和来源，且必须落在某个实际已读区间。省略 evidence.document_id 的旧输入仍指向主文献；无辅助源时不需新增字段。补读文献被拒绝或变更后，分析失效，不能仅靠主 claims 仍完整而继续宣称原混合分析有效。

## 运行及验证

```text
python scripts/materialize_review.py --db RUN.sqlite --input host-review.json --outdir batch-materialized --validate-import
```

源数据库始终只读。`--validate-import` 将数据库备份到内存，在其中调用真实 `import_analysis`；候选范围审核、完整文本资格和所有核心门禁仍然生效。省略该参数时仅完成输入和证据校验，输出 review 明确为待正式导入。校验失败不会创建本次输出。

成功后输出逐件 `公开号-analysis.json`、`公开号-review.json` 及累计 `analyses-ready.json`，保留整篇阅读、尾文、分析者及兼容覆盖记录。后者是正常 `analysis-import --input` 的输入；内存通过不表示已经写入正式库，更不表示完成独立语义审查或全量研究验收。同一输入批次每个申请只允许一个版本，避免覆盖同名 checkpoint。正式导入后另按[研究质量契约](whole-patent-research.md#研究质量记录)提交真实独立复核。

## 发现正文缺陷时

结构解析完整不等于技术内容完整。正文半句结束、关键公式成为未取得的图片或段落遗漏时，宿主提交可审计的拒绝：

```json
{
  "document_id": "实际文献 ID",
  "decision": "reject",
  "reason_code": "missing_formula",
  "reason": "宿主说明具体缺口及其影响，例如条件冒号后应有公式但正文未包含公式。",
  "reviewer": "实际宿主审阅者",
  "evidence": [{"quote": "对应原文中的精确连续文字", "locator": {"claim_number": 5}}]
}
```

```text
python scripts/patent_perspectives.py --db RUN.sqlite document-review-import --input source-rejections.json
```

支持 `truncated_tail`、`missing_formula`、`missing_text`、`parse_failure` 和 `wrong_document_content`。可加 application_id、publication_number、source_text_hash 严格核对。引用必须能回到对应原文；缺失内容本身不能被补造为 quote，应引用缺口附近的实际文字并解释问题。

拒绝记录是追加的审计事实，保留原文及原结构 qualified 值。该申请、文本类型、文本哈希相同的内容都不再有技术完成资格，不能仅换 version 标签绕过。原分析保留为 invalidated_source_review，并在 analysis_invalidations 保存失效前快照；覆盖率、export-work、证据复用、校验、正式页面和本工具共同遵守该门禁。没有 accept/override 命令。补齐完整同件新文本或取得完整同件权利要求后，重新导入、全文阅读、分析及复核；原拒绝仍保留。仅写备注、复制尾段或改成“未知功效”不能补救关键正文缺失。

## 空地址正文图片的补充访问证明

人工转写前，图片清单必须覆盖原 HTML 的每张图片，宿主逐张实际查看下载文件。原 `src` 非空时沿用该标签的精确 path；只有原标签显式 `src=""` 才使用以下 manifest 图片结构：

```json
{
  "image_id": "原HTML中的精确img-id",
  "source_image_path": "/同件PDF图片路径/原HTML中的精确img-id.png",
  "file": "evidence-images/同件公开号/已查看图片.png",
  "status": "retrieved",
  "bytes": 1234,
  "sha256": "实际下载文件SHA256",
  "supplemental_image_access": {
    "source_raw_artifact": "collector/raw/实际intelligent_image缓存.json",
    "source_sha256": "该原始缓存SHA256",
    "record_index": 2
  }
}
```

示例索引仅表示真实 `data.pdf_images[2]` 的位置，不表示可以按第3张猜图。脚本核对缓存中的工具、精确单公开号、各层成功状态、该项与原正文一致的 `patent_id`、可信图片域名及完全一致的文件名。此证明不能替代主图片 manifest 哈希、visual-review 的相同 path/hash、逐图 `visually_verified=true` 和人工转写。不能把 `patent_images` 附图或近似图片标识换入。保存完整原始响应于私有缓存；输出证据只留去签名 path 和可审计文件定位。
