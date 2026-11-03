# 问题驱动研究工作流

在技术申请需要形成可追溯的研究问题、术语表、逐项比较、路线关系及关键发现时读取。它与[整篇分析与专题研究](whole-patent-research.md)共用逐件分析、证据和研究问题，不建立第二套原文事实或复核体系。简单概览不必启用；外部产品、行业矩阵或决定书仍按各自来源与研究契约处理，不能伪装成技术申请。

## 从问题到发现

1. 复用已确认的用途、读者、范围与工作场景，明确主问题、必要子问题、选案理由及所需证据。`origin=researcher` 的研究者问题与逐件 `fields.technical_problem` 分开；后者只有专利原文明示才填写。
2. 按问题定义比较维度，以同件原文保存原词、规范概念和等价成立范围。功能相近不代表机制相同；每个申请×维度明确已披露、未披露、未取得或不适用，不能用空白或否定推断代替。
3. 解释两端方案的共同点、差异、条件和证据。结构变化与历史继承分别判断；日期、同申请人或名称相似不能单独支持改进、继承、替代或性能排序。证据不足时并列展示或保留关系未知。
4. 关键发现回答具体问题，关联比较或关系，说明用途、成立范围、其他解释及待查事项。不可比原因、被否定假设和未发现优势也可有价值，不设正面发现配额。

## 与独立质量审阅共用问题

入口均为 `scripts/patent_perspectives.py --db RUN.sqlite`，使用前读对应 `--help`：

```text
research-import --input research-input.json
research-export --output research-export.json
```

推荐先以 `partial` 或 `pending` 保存问题与底稿，再按既有流程导出复核包、完成单件独立复核和专题复核，最后重导 `answered` 并运行 `validate`、`status`、`render`。这些命令不调用模型或自动产生审查记录。

- `questions[].id` 就是质量计划的问题ID，`text` 对应计划的 `question`。问题可显式给出 `application_ids`、`selection_reason`；省略时沿用问题集的申请范围与选案理由。
- 首次 `research-import` 没有计划时，按这些问题建立计划；已有计划只核对并复用问题身份、题意和申请范围。冲突先用 `research-plan-import` 显式修改并记录 `revision_reason`，不能导入时静默覆盖或在交付前删除难题。
- `answered` 必须已有当前有效、`resolved` 且独立复核 `pass` 的专题记录，`answer` 与通过复核的限定答案一致。`partial/pending` 可以保存，不计研究完成；填入回答文字、匹配引文或三角色都有发现均不代替审阅。
- 发现的 `question_ids` 与正文 `research_question_ids` 必须相同；旧扩展输入只有前者时程序补入同名关联。正式报告仍遵守[正文映射验收](reporting.md)，不以增强页面另列答案绕过原门禁。

## 输入契约

`research-input.json` 是兼容扩展，不替换 `analysis-import`、普通 `comparisons` 或IP专属 `claim_comparisons`。导入在一个SQLite事务内完成；结构或关联错误全部回滚。

| 字段 | 要求 |
|---|---|
| `schema_version,id` | `1`；稳定的问题集ID |
| `purpose,audience,work_context,scope,selection_reason` | 研究用途、读者、场景、范围与选案理由；不是专利原文技术问题 |
| `application_ids` | 当前已纳入的技术申请ID，不改变母库 |
| `questions` | `{id,level:main/sub,origin:researcher,text,required_evidence,status:answered/partial/pending,answer,remaining:[]}`；一个主问题；未完成时写明剩余事项。可补问题自身的 `application_ids,selection_reason` |
| `dimensions` | `{id,label,definition,question_ids:[]}`；来自本次问题，不套用固定产品表头 |
| `terminology` | `{id,concept,scope,equivalence:contextual/distinct,entries:[]}`；每项原词 `original_term` 与来源。`contextual` 仅在限定条件内归并；`distinct` 保留机制差异 |
| `comparisons` | `{id,title,body,scope,question_ids,units:[]}`；增加逐单元来源和问题关联，不取代连贯比较说明 |
| `relations` | 原关系字段，加下述技术关系扩展；进入既有关系表 |
| `insights` | 原角色结论字段，加下述发现扩展；进入既有结论表 |

**来源对象**为 `{application_id,document_id,publication_number,version,evidence_ids:[]}`。ID、版本和引文使用现有库；证据须属于声明的同申请、同版本，并已由逐件分析引用，不能用标题或同族材料替代。

**比较单元**为来源对象加 `dimension_id,state,text,conditions,kind,field_refs,term_ids,claim_levels`。`state` 为 `disclosed/not_disclosed/not_obtained/not_applicable`；`kind` 为 `disclosed/inference/unknown`。`disclosed` 可以是原文披露或有 `basis` 的分析推断；其余状态必须 `kind=unknown` 并写 `reason`。`not_disclosed` 另需 `reviewed_claim_numbers` 记录实际读完的权项范围，不把权项未写扩大为说明书也未写。`field_refs` 仅引用原八字段，`term_ids` 引用术语ID。

`claim_levels` 为 `[{number,level:independent/dependent,depends_on:[]}]`，与证据定位对应；主从关系、条件和术语等价仍须原文语义复核。整份版本未取得时使用 `document_id:null`、已知同件公开号、拟核查版本，`evidence_ids/claim_levels` 为空；程序核对既存目录中的身份。若只缺测试资料而已有权项，保留当前文本来源，在 `text/reason` 说明具体缺什么。

**技术关系**的 `type` 为 `parallel/different_conditions/structural_change/improvement/inheritance/replacement/unknown`，`kind=inference`。增加 `question_ids,comparison_ids,endpoints,similarities,differences,basis,limitations,historical_status`。`endpoints` 恰好两端来源，两端技术证据均必需，其并集与关系 `evidence_ids` 一致。非历史判断用 `historical_status=unproven`；`improvement/inheritance/replacement` 须为 `supported`，且有 `history_evidence` 的额外来源，不得仅重用结构比较引文或日期。程序不判断历史证据的因果支持力或性能可比性，审查者需回到原文核验。

**发现扩展**为 `question_ids,research_question_ids,comparison_ids/relation_ids,use,alternatives,next_checks,finding_id`。`finding_id` 是三角色共用身份；本扩展同一发现须有三个不同 `role`，核心 `title/body`、范围、证据、问题、比较/关系和限制保持一致，仅 `role_note` 改变解读重点。这是增强发现的共用事实约束；普通角色结论仍可只由最适合的一个角色承接专题答案。

## 存储、更新与交付

问题、维度、术语及结构化比较保存在 `meta.research_workflow`，关系与发现复用原表。绑定当前申请与分析集合、范围、来源版本、证据及关联记录的实际内容；质量计划与复核记录本身不加入这项内容绑定，正常补做复核不使底稿循环过期。

资料、分析、范围或关联内容变化后，`validate` 报告 `research_workflow_invalid`，正式生成须先重审并重新 `research-import`；不得手改绑定。替换问题集时，扩展专属旧关系和发现保留原行，并由 `meta.research_retired` 标为历史，不混入当前结果；普通旧记录不受影响。未启用本扩展的旧运行不自动产生新问题、发现或通过记录。

`research-export` 返回机器可读输入及已存绑定，用于[数据复用](data-reuse.md)，不是重新审阅的授权或证明。页面从数据库生成，`data/research.js` 只是离线展示副本，不允许手改网页补入新结论。

按[报告规范](reporting.md)提供问题、术语、技术比较、关系与发现的阅读入口。问题筛选只影响已说明的固定案例集，目录筛选不重写研究范围。过程问题、审阅进度和恢复事项仍统一进入独立《分析记录与后续补充说明》。另验离线、移动目录、角色隔离、问题筛选、原文跳转及窄屏；静态检查不能代替真实浏览器或语义审查。
