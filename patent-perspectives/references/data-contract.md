# 数据、证据与 CLI 契约

首次导入和校验前读取。实际参数以 scripts/patent_perspectives.py --help 及子命令帮助为准。调用形式为：

    python scripts/patent_perspectives.py --db RUN.sqlite COMMAND

导入命令使用 --input 读取 JSON 文件。JSON 中保留来源原值；脚本生成的稳定标识、规范值和推导结果另存，不能覆盖原始事实。正式数据与合成测试数据分别建库。所有输入写盘前先移除或脱敏 API key、authorization、token、password、secret 等凭证字段及带密钥的URL；来源原值的保留不包括秘密。导入器还会二次脱敏，不把它当作主动暴露凭证的理由。

交付时同时保留可复用数据，按[数据复用契约](data-reuse.md)使用独立的 `scripts/export_reuse.py`，不把 `package` 技能打包命令误当作企业数据导出。快照和变化采用[增量契约](incremental-analysis.md)的 `scripts/compare_snapshots.py`；它们不改原库完成状态，结果用于独立说明和续跑。专利工程师要素对照输入在 `report-context.json.claim_comparisons`，见[逐格证据契约](claim-comparison.md)。

## 核心对象

| 对象 | 必须表达的内容 |
|---|---|
| 运行 | company、截止日、数据源、范围、主体与查询确认、能力预检结果 |
| 主体 | 稳定ID、官方名称、别名、历史/当前关系、适用时间、证据、纳入理由 |
| 查询与页 | ID、主体、original/current、原始请求、预期总量、页位置、原始响应、已接收记录 |
| 申请与文献 | 国家、申请号、公开号和kind、类型、日期、申请人/权利人原值、来源、metadata_original |
| 文本版本 | 文献号、申请号、description/claims、语言、版本、完整性与身份核验、原文、来源及获取时间 |
| 逐件分析 | 对应申请和文本、分析者、主模块、多标签、总结、技术字段、证据、整篇阅读与尾文记录、旧覆盖兼容编号及限制 |
| 单件理解复核 | 独立审查者、当前分析与来源指纹、机制/条件/实施例/图文/来源检查、证据与结果 |
| 专题研究 | 明确问题、申请选择依据、比较与反例检查、适用条件、答案及独立复核结果 |
| 角色结论 | management/rd/ip、结论、证据、涉及申请、适用范围、推断性质及限制 |
| 图谱关系 | 源节点、目标节点、关系类型、事实或推断、证据与标签 |
| 冻结选择 | 仅用户指定最近N件时建立：完整候选排名、日期证据及快照哈希、稳定排序、所选ID、父子运行身份和边界取舍；私有清单不可修改，详见[最近N件范围](latest-selection.md) |

事实字段允许未知。不能用空值假装“无转让”“无争议”或“没有同族”。名称归一化、类型归类、状态归纳、模块标签和技术解释各自留下处理依据。metadata_original 用于保留原始供应商字段和后续重查。

## 导入顺序与输入

先 init --company，设置 --as-of 和需要的 --scope；随后导入主体、搜索与文档；材料模式用 materials-import 代替搜索导入，再导出语义工作。已有运行不重复初始化。范围变化应保存变更并重新对账；更换已冻结范围时建立新运行快照。

- entities-import：导入主体数组。每条含 id、name、relation，relation 为 root、subsidiary、historical、alias、related 或 excluded。confirmed:true 时必须有 source_url 和 source_locator；补充关系时间和纳入理由。仅有名字不能代表已核验边界；重新导入主体会撤销范围确认。
- scope-confirm：输入对象为 confirmed:true、basis（核验依据）、reviewed_through（必须与运行 as_of_date 一致）。先导入完整的已核验主体种子及来源；该命令记录边界确认，不能替代企业核查。
- capability-import：输入数组，每条含 id、status、checked_at、evidence 及必要说明。id 例如 search、description、claims；status 为 verified、unavailable、failed 或 unverified。verified 必须有非空 checked_at 和 evidence；evidence 应保留可复查的请求、响应或文档身份与完整性依据。能力名表示映射标识，具体工具绑定在记录内保存。
- search-import：对象字段为 query、offset，以及 result（保留完整原始工具响应），或 records（已取出的记录）配合 raw（完整原始响应）。query 含 id、entity_id、kind（original 或 current）、request、expected_count。支持原响应的 structuredContent、data 和 content 文本包装；保留包装层的错误状态，不剥掉错误再导入内部数组。query.expected_count 必须与原响应实际 total_search_result_count 一致；页 result_count 也必须与实际记录数一致。
- query-complete --query-id：仅在服务总量已观察到、连续分页、累计原始记录量和唯一文献量均与预期一致后关闭查询。仅有人工给定 expected_count、没有原响应 total_search_result_count 的归一化输入可以暂存，但不能完成查询。外层或内层的 isError、success:false、非零 error_code 均按供应商错误拒绝，不能冒充零结果。
- query-set-import：把完整源查询组成独立的逻辑查询集。真实运行用 query-plan-confirm 冻结完整计划；源页和控制查询仍保留真实提供者总数，结构见下节。
- population-review-import：检索命中先视为候选，不因供应商标准化名称或集团扩展而直接纳入。每件申请保存独立的 included / excluded / pending 审核，结构见下一节。所有原始页、候选申请和 query_results 继续保留并按供应商返回总量对账；排除不是删除检索记录。
- document-import：字段为 publication_number、application_number、document_type（description 或 claims）、language、version、source_url、source_provider、acquired_at、text、complete、truncated、replace_by_related、completeness_basis、identity_verified、returned_publication_number；可补充 source_class 和 source_request。通常source_class为patsnap、official或仅合成测试允许的synthetic；无source_url时必须有准确的source_request，official补证必须是脚本认可的专利局域名。另有仅用于完整权利要求的original_patent_document_mirror，须按[原始公报补证规则](original-document-claims.md)提供original_document_proof及source_label，通过原PDF、获取回执、全文页提取、实际视觉审核和原文区间哈希核验；不扩展official域名白名单。claims文本还需原来源声明的claim_count。全文必须保留原始权利要求编号行；脚本按实际编号解析每项的真实start/end区间。可提供claims数组，每项含number和text，但必须与原文解析的逐项编号和完整区间文本一致，不能由外部数组补造正文中不存在的编号。
- document-review-import：宿主发现原文截断、关键公式或正文丢失后提交 decision=reject、document_id、reason_code、reason、reviewer 及精确原文 evidence。记录追加保存，不覆盖原文或原结构 qualified；已依赖该文本的分析失效并保留审计快照。相同申请、类型及文本哈希即使更换版本标签也继续拒绝；没有手动接受或解除门禁的接口。详见 [host-review.md](host-review.md)。
- auxiliary-import：已保存的 legal_status、family、abstract_image 缓存按真实批请求、同件PN、record_index、原响应、哈希和取得时点核验后进入独立辅助表。法律状态保留逐文献观察、冲突汇总unknown，三种同族分别保留；签名图URL只存私有原始记录，导出仅使用核验本地图片及公共来源摘要。详情和使用见 [auxiliary-data.md](auxiliary-data.md)。
- export-work --output：按申请导出完整任务包，包含脚本分配的 application_id、document_id、primary_document 全文、来源与定位信息；coverage 中保留旧分段编号用于兼容，不再以固定字数片段组织阅读。默认完整 claims 优先，完整 claims 不可得时使用完整 description；同 PN 同语言合格 description 可列入 support_document_candidates，只有实际需要时才局部阅读。已有效完成的旧 description 分析不重复排队；是否还需新质量复核另见 status。
- export-work 可选 --max-primary-characters N：将超过该主文献字符数的整篇任务延后，写入 `OUTPUT.deferred.json`，不切割文本或缩小覆盖分母。该上限不是 token 安全阈值；后续须处理延后清单，不能将未导出解释为已完成。
- analysis-import：逐件分析 JSON，结构见下。insights-import 和 relations-import 分别导入角色结论和关系数组。
- semantic-review-import、research-plan-import、research-review-import：分别保存独立单件复核、研究问题及专题复核；字段和有效性要求见[研究质量契约](whole-patent-research.md#研究质量记录)。来源与分析更新后重审受影响记录，不能复用旧通过标签。
- research-import、research-export：保存及导出[问题驱动研究底稿](research-workflow.md)，复用现有分析、证据、关系、结论与质量计划。questions[].id 就是计划的问题ID；首次没有计划时据底稿建立，已有计划只核对复用，冲突须显式 research-plan-import 并提供 revision_reason。先保存 partial/pending，独立审阅后才能提交与通过答案一致的 answered；命令不自动生成审查记录。
- export-quality-work --output FILE：在复核者开始阅读时导出并保存实际待审版本清单。semantic-review-import 必填清单中的 analysis_fingerprint；research-review-import 必填 plan_hash 和 population_hash，缺失或与当前版本不同均拒绝。计划创建时的哈希仍由 research-plan-import 计算。资料变更后需重新导出及审阅，不得给旧结论换新哈希。
- 最新N子运行的insights-import另须显式selection_scope，逐项匹配当前选择的kind、manifest_id、manifest_sha256、count、date_field、date_order、tie_break；保留自然语言适用范围，不能把母库结论换hash后继续使用。旧insights原行保留为历史，不计当前三角色完成，也不进入子范围页面。
- status、validate：输出真实完成与失败情况。render --output 仅在正式门禁通过后生成页面；package --output 只打包通用技能，不含企业运行资料，企业数据另按 export_reuse.py 的帮助导出。

## 实际调用示例

以下命令从技能根目录执行；TARGET_COMPANY及YYYY-MM-DD须替换为本次实际目标与截止日；JSON文件先按上述契约准备，运行数据库与输入放在技能包外。目标企业的 scope-confirm 必须等官方主体核验完成，capability 的 verified 必须等真实调用验证完成。

    python scripts/patent_perspectives.py --db ../../work/target.sqlite init --company TARGET_COMPANY --as-of YYYY-MM-DD
    python scripts/patent_perspectives.py --db ../../work/target.sqlite entities-import --input ../../work/entities.json
    python scripts/patent_perspectives.py --db ../../work/target.sqlite scope-confirm --input ../../work/scope-confirmation.json
    python scripts/patent_perspectives.py --db ../../work/target.sqlite capability-import --input ../../work/capabilities.json
    python scripts/patent_perspectives.py --db ../../work/target.sqlite search-import --input ../../work/search-page.json
    python scripts/patent_perspectives.py --db ../../work/target.sqlite query-complete --query-id target-root-current
    python scripts/patent_perspectives.py --db ../../work/target.sqlite population-review-import --input ../../work/population-reviews.json
    python scripts/patent_perspectives.py --db ../../work/target.sqlite document-import --input ../../work/document.json
    python scripts/patent_perspectives.py --db ../../work/target.sqlite export-work --output ../../work/semantic-work.jsonl
    python scripts/patent_perspectives.py --db ../../work/target.sqlite analysis-import --input ../../work/analysis.json
    python scripts/patent_perspectives.py --db ../../work/target.sqlite research-plan-import --input ../../work/research-plan.json
    python scripts/patent_perspectives.py --db ../../work/target.sqlite export-quality-work --output ../../work/quality-work.json
    python scripts/patent_perspectives.py --db ../../work/target.sqlite semantic-review-import --input ../../work/semantic-reviews.json
    python scripts/patent_perspectives.py --db ../../work/target.sqlite research-review-import --input ../../work/research-reviews.json
    python scripts/patent_perspectives.py --db ../../work/target.sqlite insights-import --input ../../work/insights.json
    python scripts/patent_perspectives.py --db ../../work/target.sqlite relations-import --input ../../work/relations.json
    python scripts/patent_perspectives.py --db ../../work/target.sqlite validate
    python scripts/patent_perspectives.py --db ../../work/target.sqlite status

query-id 使用实际导入的 query.id；逐页获取、逐件全文导入与逐件分析均需循环至范围内全部完成，不能只运行一次样例。验证通过后才执行 render --output，并通过 package --output 打包技能。其他企业只替换主体输入及运行边界，核心代码不改。

## 候选范围审核

真实运行默认 `scope.require_population_review=true`。每个候选申请必须有有效的纳入或排除决定；未审核、pending、或因主体/候选著录变化而过期的决定均阻止正式验收。旧合成测试默认保持自动纳入兼容；正式运行不能借此省略范围审核。

导入数组中每条包含：

- `application_id`、`status`（included / excluded / pending）、`reason`；已决定的记录还必须有 `reason_code` 和非空 `assignee_evidence`。
- `assignee_evidence` 每条为 `publication_number`、`field`、`value`、`matched_name`。field 仅接受原始 `original_assignee`、`original_assignees`、`applicant`、`current_assignee`、`current_assignees`；value 必须与该文献 `metadata_original` 中的原值完全相等，包括数组结构。matched_name 必须是该原值中的一个精确名称，不能填写标准化名称或猜测的别名。
- `matched_entity_ids` 是已核验主体ID数组；每个ID必须能通过其法定名称或已有证据的 aliases 精确匹配上述原始名称。included 使用 `reason_code=target_entity`，匹配已核验 root/subsidiary/historical 主体。不同主体的同名或近似名仍需身份核验。
- 不能精确匹配已核验主体时，可用 `identity_source` 补充官方身份来源：`source_url`、`source_locator`、`quote`、`subject_name`、`determination`。官方来源限专利局、政府登记及认可证券披露域名。subject_name 必须与著录证据一致。纳入使用 determination=target_entity 并指定 `target_entity_id`；排除使用 determination=different_entity。

不同主体排除使用 `reason_code=different_entity`，必须匹配已核验 excluded/related 主体或有明确的官方身份依据；仅“没有匹配上”不成立。候选任何文献已有核验目标主体的原始申请人/权利人名称时，不得以 different_entity 排除。`outside_control_period` 另需官方 `control_period_evidence`，含上述官方来源字段、determination=outside_control_period、relevant_date、control_from/或control_to，相关日期必须等于申请日且确实在已证控制期间外；当前已确认由目标持有的申请不能仅因历史申请日而排除。正文缺失、截断、额度或解析失败绝不是排除依据，纳入申请仍须通过全文和语义分析门禁。

经保存的 Patsnap 原始著录数据也可支持明确的非目标身份判断。`identity_source.source_class=patsnap` 时必须提供：

- `source_artifact`：相对于运行数据库目录的已保存原始 JSON 文件；解析后的绝对路径必须仍在运行目录内。
- `source_request` 及 `request_path`：请求为 bibliography，arguments.patent_number 保留实际单件或逗号分隔批量请求，目标公开号必须在逐项规范化后的请求集合内，不能把整串号码拼接规范化。缓存请求位置默认 `["source_request"]`；若Collector缓存以顶层tool/arguments保存，可改用 `request_tool_path:["tool"]` 和 `request_arguments_path:["arguments"]` 两条路径共同核验。source_request 必须与缓存实际请求完全一致，不能为批量响应伪造单件请求。
- `response_path`：指向缓存内含 `success:true`、`error_code:0`、data 数组的原始业务响应对象，不接受错误响应。
- `returned_publication_number`、`publication_path`：必须指向同一条 data 记录的 pn 并与请求及候选文献一致。
- `name_path`、`name_value` 和 `address_path`、`address_value`：两条路径必须指向该记录 bibliographic_data.parties.applicants 或 assignees 中同一个主体的 name 与非空 address/country 原值。不能用发明人或搜索标准化标签代替申请人身份。另保留 subject_name、source_locator 和 determination。

例如保存的原文为 `{source_request:{tool:"bibliography",arguments:{patent_number:"..."}},response:{success:true,data:[{pn:"...",bibliographic_data:{parties:{applicants:[{name:"...",address:"..."}]}}}],error_code:0}}`，则 response_path 为 `["response"]`，name_path 为 `["response","data",0,"bibliographic_data","parties","applicants",0,"name"]`，address_path 仅将末尾改为 address；publication_path 为 `["response","data",0,"pn"]`。脚本核验原值并记录源文件SHA256；该证据支持代理的明确身份判断，不自动以名称差异推断排除。

审核绑定该申请全部候选文献及主体快照。新增关联版本或修改核验主体后，该申请恢复 pending，须重审。`coverage` 中 candidate_applications / candidate_publications 保留检索候选规模，included_applications / excluded_applications / pending_applications 单列；applications、publications、技术全文分母、export-work、角色引用和正式页面列表均只使用有效纳入集合。审核或候选集合改变会使既有角色结论 population_hash 过期。正式包的 sources-and-coverage.json 保存审核决定和候选状态，以供回算。

## 源查询、逻辑查询集与空结果证明

`queries/pages/query_results` 保存提供者真实返回。`query_sets` 独立表达某一主体、某一申请人角色的逻辑检索是否完整。正常请求中 `verification_only` 默认 false；空结果验证用控制查询必须在 `query.request.verification_only=true` 标明，并以真实 `expected_count=1` 分页导入及完成。此类查询不能直接满足常规主体检索覆盖，单独由控制查询引入的文献仅作为来源留存，不进入候选、技术分母或正式列表。

`query-set-import --input FILE` 接受数组，每条共同字段是 `id`、`entity_id`、`kind`（original/current）、`query_text`、`type`：

- `type=direct`：另给 `leaf_query_id` 和整数 `source_total_count`。绑定查询必须为普通查询、同主体同角色、查询文本相同并已完成。引擎重新检查原始页中的服务总数、连续页位置、页内/跨页唯一文献及 query_results；逻辑数量不能覆盖源数量。
- `type=empty_by_disjoint_anchors`：必须明确 `source_total_count:null`、`derived_count:0`，并给 `controls` 数组两条 `{query_id,anchor_publication_number}`。两个控制查询各自完整、源总数1、只返回相应单件且两锚点互异，原请求须分别精确为 `(Q) OR PN:锚点`，其中Q等于本逻辑 query_text。结论由集合关系推导，不把未知服务总数改为0。
- `type=date_partition`：另给整数 `source_total_count`、`date_start/date_end`、`parent_source:{request,raw_response,...}` 和 `children:[{query_set_id,date_from,date_to}]`。父原始响应的真实总数必须相符，原始请求须按公开日期升序，保留最早记录证据。子逻辑集先导入，查询须精确为 `(父Q) AND PBD:[起日 TO 迄日]`；区间必须覆盖父区间、连续且无交叉，每条公开日期在对应区间内，子数量和与唯一文献数须等于父原始总数。输入日期可用YYYYMMDD或YYYY-MM-DD。

日期分片的父响应只作为计数证据，不将其前1000条预览伪装成已经完成的2万条以上查询；只导入可完整取回的叶查询。逻辑集来源与控制记录会进入 sources-and-coverage.json，原始JSONRPC响应可以在保留 `transport` 的包装中连同 `{pagination:{offset,limit},source_artifact,source_artifact_sha256}` 保存，原响应内的数量不变。冻结的查询请求本身不含offset和limit。

`query-plan-confirm --input FILE` 输入 `plan_hash`（完整检索计划的SHA256）和 `required_query_sets` 数组；每项含 id、entity_id、kind、query_text，可保留category。也可仅给 `required_query_set_ids`，此时各逻辑集必须已经存在。显式完整计划允许尚未导入的逻辑集，以便分批续跑，但正式验收会逐项报告缺失；不能因为本次只导入main就忽略计划里的补充检索。确认后计划及要求不可缩减或更换；变更需新运行快照。同一缓存检索若对应多个经核验主体，每个主体有独立的源查询ID和逻辑集ID，原始来源可复用。

真实检索运行默认要求已冻结逻辑计划；materials 模式改用已确认的材料清单，见[材料研究](material-research.md)。每个确认纳入的root/subsidiary/historical主体必须同时有该计划要求的original与current逻辑集全部通过；alias可以作为检索上下文，但不额外当作独立法人强加覆盖。合成测试未开启逻辑计划时兼容旧普通查询规则。`coverage` 分别显示源queries、verification_queries、logical_query_sets、required_query_sets、候选公开记录以及全部存储的source公开记录；控制记录不会冒充企业拥有专利。逻辑计划和逻辑集变化也会使既有角色结论指纹过期。

## 同件著录补证

`bibliography-import --input FILE` 将原始著录响应保存到独立的 `bibliographies` 表。不能替换 `metadata_original`、原始检索页、源计数或查询对账。输入为单条对象或数组，每条包含：

- `publication_number`：已经保留的搜索文献号；可给 `application_number` 作额外核对。
- `source_artifact`：相对于数据库目录的原始缓存JSON路径，文件必须在运行目录内。
- `source_request:{tool:"bibliography",arguments:{patent_number:"实际完整批量号码串"}}`：与缓存实际请求完全一致；逐项规范化逗号分隔的请求号码，目标文献号必须在其中。
- `request_tool_path:["tool"]`、`request_arguments_path:["arguments"]`：适配Collector顶层保存的实际请求。旧缓存可用 `request_path:["source_request"]`；两种方式不能同时指定。
- `response_path:["response","result","structuredContent"]`：指向原始 `success:true`、data数组的业务响应。所有外层传输、工具和业务错误均拒绝。
- `record_index`：原始data数组中的精确索引；可附 `record_path`，其值必须等于response_path加 `["data",record_index]`。该条记录pn必须完全匹配，不可跨同族替换。

`application_reference` 的country与doc_number规范化结果必须与搜索保留的同件申请号相等。doc_number已含国别时不重复添加；PCT/CN等国际申请标识保留原标识，不能生成CNPCT。publication_reference有完整国别、文献号和kind时，也须重新组成并核对公开号。

每条导入记录保留原始record、parties（原名及地址）、classification_data及可确认IPC、原始patent_type枚举、原始申请及公开日期、source_request、record_path、原始缓存SHA256与采集时间。`APPLICATION`、`PATENT`、`UTILITY`、`DESIGN`依照[智慧芽P012官方定义](https://open.zhihuiya.com/devportal/api-reference/basic-patent-data/bibliography)分别映射发明申请、授权发明、实用新型及外观设计；前两项归入invention。未知枚举继续unknown，不按标题、国别号尾或词面猜测。只对同件application/publication的unknown类型补值；已知类型冲突保留双方，不覆盖。影响技术/外观统计分母的未解决类型冲突阻止正式验收。仅受类型补值影响的范围审核因其候选快照变化须重审；中性辅助字段的导入不会使全部身份审核失效。

日期冲突统一包括搜索不同公开版本之间的差异，以及搜索与著录之间的差异；保存双方原值和公开版本来源，正式页面对应日期及日期统计使用unknown。该冲突不影响已经具备完整同件技术文本和逐段分析的技术理解完成；角色日期结论需基于处理后的口径重审。若申请日被用于outside_control_period排除，日期冲突使该排除恢复pending，必须核查后再用于控制期判断。原名变化本身不构成转让证据；不从著录补证推断权属变更或法律有效性。

著录是辅助证据；不要求为每件无限补齐地址、IPC或日期等字段来满足技术全文验收。技术文本仍独立经过下述全文门禁。运行目录中的缓存导入器以ledger中每件的精确缓存索引选择一个现存版本，其余原始缓存不删除。`--unknown-only --dry-run`只读列出可补记录及缺失/错误，`--unknown-only --apply`才导入；不发起网络请求。缺失或错误缓存单列报告，退出码3表示本次选择仍有未解决来源，绝不把缺失标为完成。

## 文本门禁

独立申请单位与国家登记成员分开保存。只有通过 [national-registration.md](national-registration.md) 中严格官方适配器的同记录身份映射，才可用 `registration-member-import` 追加成员→规范独立申请关系；不按同族相似或缺全文合并。原申请、文献、检索、权属及法律来源均保留。覆盖率保留原记录与规范单位桥接，技术任务和角色计数使用规范单位；EP证据仍为EP，不能据成员关系复制成德国正文或移用状态。

仅在可检查的完整性依据存在、同件同版本身份核验通过、文本未截断且未被相关文献替换时，才将 complete 置为 true。returned_publication_number 应与实际源文献匹配，不能靠请求参数代替检查返回内容。

document_type 只接受技术依据 description 或 claims。公开、授权及修改版本分别保存。技术全文分母仅含发明和实用新型。选定主文本未完整阅读时，该申请分析不能完成；独立语义复核及专题完成另行验收。

claims 原始编号的格式若不能被当前解析器识别，应保留原始资料并修正、验证适配器；不能手工给无编号正文添加编号来满足门禁。

主文本作为完整任务提供。新文献的兼容覆盖区间覆盖全文；旧库已有分段和证据位置保持不变，不重新切割或删除。宿主读完所选文献后填写绑定 document_id/source_text_hash 的 whole_document_review 及 tail_check，脚本校验后生成兼容 completed_chunk_ids。不能以勾选编号或阅读摘要代替正文。连续阅读的完整覆盖、容量依据及字段见 [host-review.md](host-review.md)。完整 claims 为默认主文献；按需补读说明书只在 support_documents 记录实际 read_regions，不加入主完成编号，也不宣称读完说明书全文。

宿主发现语义层面的正文残缺时，必须保存 document-review-import 拒绝，不能只在分析备注中承认残缺却仍计为完成。被拒绝文本不能用于 analysis-import、export-work、有效证据复用、技术全文或分析完成统计；完整同件替代文本可重新导入并全文分析。旧正文、旧分析及拒绝前快照分别保留。

## 逐件分析与原文证据

真实运行的 analysis-import 每条包含 application_id、document_id、analysis_author、whole_document_review、tail_check、primary_module、tags、summary、fields、evidence 和 limitations；兼容完成编号由核验后的整篇记录产生，显式提交时也须匹配原库。application_id、document_id 必须使用导出值。申请ID规范为 authority 加冒号、再加去标点后的含国别申请号，例如 CN:CN2015201595349；公开号与公开文献记录ID为大写去标点号，document_id 则使用脚本导出的哈希标识。不要根据显示标题自行生成ID。旧分析保留复用；重新导入真实分析时须补足实际阅读记录，不能伪造。

summary 为含 text 和 evidence_ids 的对象；fields 须包含 application_field、technical_problem、technical_means、components、relationships、steps、conditions、claimed_effects 八项，每项是含 text、evidence_ids 和 kind 的对象数组。未披露者填空数组并解释限制。kind 使用 disclosed 或 inference；推断须有非空 basis 和 conditions。直接导入与紧凑审阅工具采用一致的真实运行要求。

evidence 每条含 id、quote、locator，并可含 document_id、start/end。省略 document_id 时使用主文献，兼容旧单源分析；给定时必须为主文献或已声明的辅助文献，不能被脚本悄悄改归属。quote 必须是该 evidence.document_id 中可以精确验证的连续原文，不接受译文冒充原文、拼接引文或省略号。locator 保存段落、页码、权利要求编号等定位；claims 证据须使用含 claim_number 整数的对象，或字符串“权利要求N”，并核对引文的真实 start/end 完全位于该项权利要求的原始编号区间。另一条权利要求出现相同文字也不能据此借用其位置。字符offset若不确定则省略，由脚本定位核对。重复引文必须提供准确 start/end；位置按Python Unicode字符索引计算，不能直接使用JavaScript UTF-16索引。

主文献为完整 claims 时，允许 `support_documents:[{document_id,read_regions:[{start,end,locator:{paragraph:"0007"},reviewed:true}]}]`，无真实段号用 `locator:{source_span:true}`。辅助源须是同一申请、同一 PN、同一原文语言的合格完整 description，且未被拒绝；不跨公开/授权版本、国家或同族。每区间由宿主明确已读，边界按该 description 原文计算，段号与区间相符、不重复或交叠。可额外传 source_text_hash 核对版本；入库固定保存实际哈希、版本和 reading_scope=selected_regions。辅助引文须完全落在该文献的一个实际已读区间，主 claims 也须有证据。辅助源之后被拒绝时，依赖它的整条分析失效并留审计，覆盖率和正式交付均遵守。没有辅助读段时不填写 support_documents。

每条总结和技术字段必须有可解析的 evidence_ids，且引用属于该申请选定版本及已声明的同 PN 辅助来源。字段未披露时使用空数组并写 limitations，不得填造技术问题、性能或数值，不为填空强读说明书。claims-only 应显式记录文本依据受限；摘要中出现但 claims 未披露的内容不能当作该 claims 的证据。

为减少重复抄录，可使用 [host-review.md](host-review.md) 中的紧凑宿主输入及 materialize_review.py，以段号、权利要求编号或精确区间生成 quote/start/end/evidence_ids。全部阅读、八字段解释、总结、主模块及限制仍由宿主完成；机械尾段匹配不证明语义完整。工具只读运行库，正式导入验证可在内存备份中进行。

主模块是分析归纳，单件只设置一个用于互斥占比；tags 是多标签，统计需说明可重复。图谱中的推断关系与官方记录的同族、分案、引用关系分开标记。

## 角色结论与关系

insights-import 的每条记录包含 id、role、title、body、evidence_ids、patent_ids、scope、limitations、kind。role 使用 management、rd 或 ip；kind 使用 observation、hypothesis 或 research_action。scope 描述原始适用范围，至少明确本运行及相关申请；已有全组合结论在筛选后仍保留该范围，不自动视为子集结论。承接已完成专题的正文结论另填 research_question_ids，并按[报告组织](reporting.md)携带专题的完整证据关联；正式 render 检查是否漏题或缺证。

relations-import 的每条记录包含 id、source、target、type、kind、evidence_ids、label。kind 为 fact 或 inference。事实边需 evidence_ids，或 source_url 加 source_locator；推断边需 evidence_ids 和非空 basis，说明归纳依据。技术相似、问题—手段归纳和模块聚合属于分析边。引用方向按原始数据保存，不能反转被引与引用。

导入角色结论时，脚本绑定当前申请集合、主体边界、截止日和逐件分析的 population_hash。集合或分析变化后，旧结论视为过期，必须基于更新后的证据重审并重新导入三个角色的结论，不能手工沿用旧指纹。

跨专利结论只引用已导入且可追溯的证据。统计先由脚本计算，再由宿主解释；模型不得补写数量、状态、期限或同族成员。

可选问题驱动扩展将术语、维度和结构化比较保存在 meta.research_workflow；增强关系与发现进入既有表，并按[完整契约](research-workflow.md#输入契约)核对同件同版本来源、比较状态、主从权项、两端技术证据、历史证据及角色事实一致。发现的 question_ids 与 research_question_ids 必须一致，旧扩展输入省略后者时补同名关联。单事务导入失败全部回滚；来源、分析、范围或关联内容变化使工作流绑定失效，须重审后重新导入，不手工换哈希。质量计划与复核记录本身不加入此绑定，补做真实复核不构成内容变化。

## 完成与失败处理

完整案例需要集团边界确认、全部计划查询对账、所有技术申请的合格文本与逐件分析，以及通过引用和关系校验。真实运行另需有效的单件独立语义复核、研究计划及全部问题的有效专题复核；缺少或过期的记录、待修订或证据不足结果不计研究完成。法律状态、同族、附图和图片分别报告覆盖；未知不能代替完成，也不能因辅助字段未知而混淆技术阅读分母。程序验证可检查记录和来源关系，不给出语义准确率。

服务错误保留响应和尝试记录，超限后待外部条件变化再继续。重复导入、重试或中断续跑不得重复计数；更换证据版本或修正分析后需重新验证受影响结论。不得手工修改 SQLite 来绕过门禁。

测试预览仅允许 scope.synthetic=true 的独立测试运行；真实企业数据即便使用 --preview 也不能绕过正式全量验收。命令行 JSON 输出使用 UTF-8，以保留中文主体及技术文本。

## 材料来源

materials-import 的冻结文件与目录契约见[材料研究](material-research.md)。uploaded_patent_document 仅用于已登记材料的 claims/description，须有实际页码、身份与结尾复核，以及源文件和文本哈希；不允许摘要或节选变成完成正文。该入口不伪造 search-import 结果或 query-complete。
