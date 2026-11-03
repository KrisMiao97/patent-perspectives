# 公司产业研究数据契约

当报告需要五类产业研究任务、公司×技术方向矩阵或主要路线研究时读取。新增字段是原有 `report-context.json` 的可选部分；不提供时旧报告行为保持不变。研究方法见 [公司产业研究](company-research-tasks.md)。这里定义程序实际接受的字段，不代替研究和独立复核。

## 接入与边界

`industry_research` 由 `scripts/industry_research.py` 校验，经过 `scripts/report_data.py` 组装为 `data/industry-research.js` 中的 `window.PP_INDUSTRY`。没有该字段时值为 `null`。原有范围、完整阅读、原文引用和正式交付检查继续生效。

`scope.as_of` 必须等于当前运行的 `as_of_date`；目标公司名称必须等于当前运行的 `company`。矩阵、路线和任务使用这份明确的研究范围，不会跟随主报告的年度/类型筛选自动改变。允许少量对照企业，但不得把对照企业申请混入目标公司的统计分母。

本模块不检索资料、不生成评分、不推断技术趋势，也不因为记录通过校验就宣布研究理解正确。原文理解、来源类别、企业归属、预测逻辑和比较条件须由研究者复核。

## 根对象

```json
{
  "industry_research": {
    "schema_version": 1,
    "target_company_id": "target",
    "scope": {
      "topic": "本次要研究的技术问题",
      "as_of": "运行截止日 YYYY-MM-DD",
      "selection_basis": "纳入的公司、产品、路线、专利范围及其选择理由"
    },
    "companies": [],
    "sources": [],
    "tasks": [],
    "routes": [],
    "matrix": [],
    "jurisdiction_cases": []
  }
}
```

这段是字段示意，日期说明文字不能直接作为真实输入。所有 `id` 使用稳定ASCII标识；同类标识唯一。对象的文字字段为纯文本，由页面转义展示，不接受通过文字嵌入可执行HTML的用法。

- `companies`：至少包含目标公司，每项为 `{id,name,role}`。`role` 说明品牌、制造、研发、供应商等本次已核实身份；不自动把品牌、集团和法律主体合并。
- `tasks`：至少一个任务；按实际请求纳入，不要求每次把五类都填满。
- `routes`：本次纳入的技术路线；没有取得足够资料时可以为空，并由任务说明缺口。
- `matrix`、`jurisdiction_cases` 可为空；缺失矩阵格自动补为“本次尚未取得可用于判断的材料”，不补成否定结论。

## 来源与时间

每个来源至少含 `{id,kind,title,locator,observed_at,url}`，也可以用 `local_path` 代替 `url`，或者同时提供两者。`locator` 指向具体原文段落、权利要求、页码或表格。`observed_at` 是真实取得/观察日期；`publication_date` 是资料发布日期，不能确定时省略或为 `null`，不补造日期精度。

| kind | 含义 | 可以说明到哪里 |
|---|---|---|
| F | 已完整阅读同件、同版本权利要求 | 原文披露的要素、关系、步骤和条件 |
| D | 已完整阅读同件、同版本说明书作为主文本 | 已读说明书披露的机制；不能伪称权利要求已读完整 |
| P | 官方产品页面或手册 | 该产品公开描述的功能、结构或参数；专利采用关系另行核验 |
| R | 论文或可定位研究资料 | 对应试验、条件和研究结论 |
| O | 公司业务自述 | 该公司公开声称的业务或能力，保留其自述属性 |
| L | 目录、著录或检索线索 | 仅确认相应线索；不能替代技术全文理解 |

`U` 仅用于矩阵未知格，不是来源类别。颜色区分来源类型，不表示价值、成熟度、强弱或优先级。

观察时间可以晚于研究截止日：程序增加 `observed_after_cutoff`，保存实际日期，不把当前观察伪装成历史状态。已知发布日期晚于研究截止日的资料，必须在来源上标记 `temporal_use:"retrospective"`；引用它的具体任务、路线、模块、子项或矩阵主张也须同样标记。程序增加 `publication_after_cutoff`；页面提示后验资料，它不能被用来声称截止时点已经知道或具备某项能力。

F/D 还必须含：

```json
{
  "application_id": "主库中的真实独立申请ID",
  "document_id": "本次已读主文本ID",
  "evidence_ids": ["同件、同版本证据ID"]
}
```

程序检查申请在当前报告集合中、分析已完成、主文本匹配、文献完整且未拒绝、公开/授权版本明确，以及引文和字符区间精确相符。F 进一步检查完整连续的权利要求编号和引文所在权项；D 使用说明书段落或页码位置，不套用权利要求编号。程序输出实际 `publication_number`、`version` 和 `evidence`，用于页面追溯。

竞争者全文尚未绑定原文记录时，不能仅靠自称“已读”标成F/D。不得为满足这一条件，把竞争者文献塞进目标公司的统计分母。

外部已导出研究记录使用 `report-context.json` 顶层的可选 `industry_reference_corpora`：

```json
{
  "industry_reference_corpora": [
    {"id": "peer-run", "payload": {"run": {}, "patents": []}, "details": {}}
  ]
}
```

以上只是结构示意，实际须填入已有研究运行导出的完整数据。`payload` 与 `details` 沿用现有渲染器输入结构；run 至少有 company、as_of_date、scope、status。来源通过 `corpus_id:"peer-run"` 选择该语料，省略时为 main。每件来源仍执行上述完整主文本与同件同版本引文核验；同一申请的同一文献ID，或同一公开号/版本/文本类型，若在多个语料中出现不同原文、完整性或拒绝状态，程序拒绝生成。

参考语料不加入主报告 patents、统计分母或产品分类。程序在来源旁保留 corpus_company、corpus_as_of、corpus_scope 和 corpus_review_note，并输出 reference_corpora 元数据。通过这些引用检查不表示原运行的独立审阅门禁已经重新通过；原始导出运行的状态只能按其自述保留。正式研究仍需复核被引用的技术判断。

参考语料原文和必要材料应随数据复用交付保留；前端来源只输出实际引用及语料说明，外部来源不能借同ID跳到主库另一件申请。该能力处理显式提供的导出对象，不自动连接其它数据库或自行搜集整个工作区。

## 五类任务

每项包含：

`{id,kind,status,question,answer,conditions,source_ids}`

- `kind`：`project`（立项）、`competition`（竞争格局）、`profile`（公司画像）、`selection`（路线选择）、`forecast`（技术预测）。
- `status`：`supported` 或 `unknown`。supported 的回答至少关联一个具有实质内容的来源，不能只依赖L目录。
- `question`：限定问题；`answer`：本次能够成立的回答；`conditions`：成立条件与范围。
- unknown 必须有 `reason`；可以没有来源，但必须解释缺什么资料及其影响。

任务文字可以包含有证据的推断；应在正文写明推理和条件。该状态不表示推断已经获得实验验证。

## 路线及四个研究模块

每条路线包含：

`{id,name,problem,mechanism,major,selection_reason,source_ids}`

`major` 是明确布尔值；主要路线的选择要基于所研究的使用问题、技术作用及证据，不能只按申请量挑选。`mechanism` 解释部件位置、连接、动作或过程及条件。主要路线不得只依赖L来源。

每条 `major:true` 路线必须提供 `transfer`、`forecast`、`maturity`、`selection`。四者均有公共字段：

`{status,summary,conditions,unknowns,source_ids}`

status 为 supported 时有实质内容来源，并提供下列对应结构；status 为 unknown 时可以没有子项，但 `summary`、`conditions`、`unknowns` 须具体说明现有认识、边界和证据缺口。非主要路线可以省略模块；如果提供，仍执行同样检查。

### 跨行业借鉴 transfer

`candidates` 数组，每项：

`{domain,shared_function,mechanism,differences,adaptation,test,source_ids}`

分别解释来源行业、共同功能、来源方案如何工作、关键工况差异、迁移需要改动什么、怎样验证。候选借鉴不是已经验证的可用方案。

### 条件预测 forecast

`hypotheses` 数组，每项：

`{horizon,change,driver,blocker,trigger,falsifier,source_ids}`

分别记录预测时间条件、候选变化、推动原因、障碍、何种信号支持继续跟踪、何种观察会推翻或收窄预测。`horizon` 是带条件的文字；不自动生成3/5/10年结论或概率分数。

### 成熟度 maturity

`rubric` 说明本次分级方法及每级所需证据。`dimensions` 每项：

`{name,stage,basis,status,source_ids,reason?}`

研究方法应分别检查机理/组件、系统集成、制造和部署，不用一个数字遮盖局部缺口。status 默认为 supported；unknown 行必须含 `reason`，可以没有来源，不影响其它维度保留已有证据。数值TRL如确有需要，由研究者给出适用标准和证据，不由脚本按专利数量换算。

### 选型 selection

必须含 `scenario`、`recommendation`、`reversal`，分别交代应用场景、有限推荐及会改变推荐的条件。`criteria` 每项：

`{name,priority,measure,status,source_ids,reason?}`

分别写指标、必要约束或偏好、同条件测量方法。status 默认为 supported；有依据的指标关联来源，unknown 行提供具体 `reason`。这里是选型框架，不是自动加权评分器；没有明确用户偏好和可比数据时，不编造权重或强行给综合排名。

## 公司×技术方向矩阵

每格：

`{company_id,route_id,claims:[{kind,text,source_ids,state?}]}`

同格可以并列多个来源类别的主张；一条主张内的来源类别必须一致。正常主张 state 为 observed，引用必须存在且类别匹配；U 只能为 unknown 且 `source_ids:[]`。未知格不允许用 count/value=0 或 state=absent 代替。矩阵不接受 score/rank 字段。

来源支持什么公司的什么观察，仍需人工核对；ID匹配不能证明企业归属或文字理解正确。保留来源类别、限定解释和证据入口。矩阵结果按当前研究范围展示，不能扩展成整个行业的全量排名。

## 所选案例地域表

每个案例：

`{id,label,company_id,application_id,observed_at,source_ids,authorities}`

`authorities` 每格：

`{code,status,note,source_ids,member_publication_numbers}`

- code 为受理机构两字母代码，包括WO；WO是国际申请路径，不作国家销售市场。
- status 为 simple、extended 或 unknown。
- simple/extended 至少有一件具体 `member_publication_numbers` 和可定位的同族记录来源。
- unknown 不列确认成员，不转换成无布局；可以表示未查、未见或资料不足，具体原因写在note。
- 不接受 legal_status 或 company_coverage 字段。每个案例显示其独立观察时间，并明确这只是所选案例的同族记录。

成员与同族记录的真实对应、独立申请与国家登记成员关系，继续按既有取证流程核验；本表不证明权利有效，不代表公司整体地域布局，不自动增加技术申请计数。

## 本地材料、导出与安全

`url` 仅允许无嵌入凭证的HTTP(S)网址。`local_path` 为交付目录内的相对路径，使用 `/`；禁止绝对路径、回退目录和编码穿越。文件存在、复制和解析后路径仍在材料根目录内，由正式render检查。

需要随报告复制本地来源时，在 `report-context.json` 顶层提供 `industry_materials_root`，指向这些材料相对路径的源根目录；这个机器路径不进入前端研究数据。允许类型及复制规则以主渲染器实现为准；HTML来源按静态文字保存，不能把原网页脚本当研究内容执行。缺失必需来源时，不声称离线材料交付完整。

交付时保存本次行业研究JSON、文字报告和来源表，与已有专利库、来源材料及独立说明一起建立阅读入口。阶段进度、处理失败和跳过事项仍进入统一的《分析记录与后续补充说明》，不变成读者报告的运行看板。

`tests/test_industry_research.py` 的 `make_fixture()` 是明确标注的合成光学测试数据，可验证五类任务、来源区分、未知格、主库原文绑定和路线模块。它不是真实企业报告，不进入正式研究结果。
