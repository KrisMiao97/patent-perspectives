# 国家登记成员与独立申请单位

国家登记记录不自动等于另一次独立申请，也不能仅凭同族、标题相似、同一申请人或缺全文而合并。`registration-member-import` 追加经官方证据核验的身份映射；原 application、publication、查询页、原计数、著录、权属和法律观察均保留。

数据模型允许不同国家来源的登记成员，实际取证须有该官方格式的专用适配器。首版仅实现 `dpma_eakz_epn_v1`：同一 DPMA 个案主数据表中的 DAKZ、EAKZ、EPN，分别对应德国案号、欧洲申请号和欧洲公开文献号。EAKZ 含校验位须与同件 EPO XML 的 B210 完全相等；EPN 须与该 XML 的实际公开号及库内 EP publication 相等。现有申请号码规范仅接受本项目已支持的2000年后 EP 格式；不猜更早号码或其他国家程序。没有已实现且通过验证的官方适配器时继续保留独立记录，并标识程序身份待查。

## 可审阅输入

```json
{
  "adapter": "dpma_eakz_epn_v1",
  "relation_type": "national_register_member_of_european_application",
  "member_application_id": "库内DE申请记录ID",
  "canonical_filing_application_id": "库内EP独立申请ID",
  "member_publication_ids": ["保留的供应商DE文献标识"],
  "official_register": {
    "source_class": "official",
    "source_url": "实际DPMA个案最终URL，AKZ须匹配EAKZ",
    "artifact": "相对于运行数据库目录的原始HTML路径",
    "sha256": "原始字节SHA256",
    "acquired_at": "实际获取时间",
    "receipt": {
      "artifact": "运行目录内原始获取记录JSON路径",
      "sha256": "该JSON原始字节SHA256",
      "record_path": [0]
    },
    "fields": {"DAKZ": "原始值", "EAKZ": "原始值", "EPN": "原始值"}
  },
  "canonical_filing_evidence": {
    "source_class": "official",
    "source_url": "实际EPO同件publication-server XML URL",
    "artifact": "运行目录内原始XML路径",
    "sha256": "原始字节SHA256",
    "acquired_at": "实际获取时间",
    "receipt": {"artifact": "获取记录JSON路径", "sha256": "原始字节SHA256", "record_path": [0]},
    "publication_number": "库内同件EP公开号"
  },
  "reviewer": "实际身份审阅者",
  "basis": "说明为什么官方登记证明同一申请单位；不能使用缺全文或相似度作理由"
}
```

这是结构示意，不是真实输入。receipt 指向真实保存的获取条目，包含 `final_url/acquired_at/local_file/bytes/sha256/content_type`；有状态码时须为200，错误条目被拒绝。所有文件只能在运行目录内，映射保存原文件哈希、获取条目路径、实际字段值、表格行定位、EPO根属性及B210定位。默认不允许外部XML实体；仅容许已知EPO外部DOCTYPE声明，解析不访问网络。

导入要求成员及规范申请都已经在本运行范围审核和日期窗口中纳入，且技术类型已确认、无未解决的类型冲突。未知申请、错文献、不同官方记录拼接、缺字段、多义字段、文件或receipt篡改、未经支持的来源、重复冲突以及映射链/循环均拒绝。映射不可静默改写；完全相同输入重放幂等。后续范围变化使两端不一致，或来源失效时，不悄悄减少分母，保留原记录并阻止正式验收。

```text
python scripts/patent_perspectives.py --db RUN/recent5y.sqlite registration-member-import --input RUN/registration-member-proposed.json
python scripts/patent_perspectives.py --db RUN/recent5y.sqlite validate
```

导入映射不会创建正文、证据或技术分析。成员不再增加独立技术任务，规范 EP 申请仍须以自身完整文本完成分析。不能用 EP 分析为 DE `analysis-import`，也不能把 EP 原文复制、重命名成德国全文。

## 统一计数与详情

- `included_source_records` 保留范围内原始申请/登记记录；`included_applications` 返回独立申请单位，只有经证据核验且两端均在范围中的成员才从额外单位中扣除。
- `coverage.registration_count_bridge` 同时给出 `raw_included_application_records`、`raw_technical_application_records`、独立申请及技术单位，以及逐条负一调整、原成员和规范申请ID。查询页总数、候选对账和原记录不变。外观不因该发明登记关系改变。
- 既有 `candidate/included/excluded/pending_applications` 为原身份审核记录数，不冒充期间内规范单位数；期间汇总保留 `selected_source_application_records` 及原类型分布，独立单位数用于完成率、正式技术任务、申请年/类型/权威机构统计及角色指标。地域另给 `by_jurisdiction_records`，不能因规范申请为EP而隐藏DE记录。
- payload 的正式 `patents` 仅列独立单位。`registration_members` 以及规范申请详情中的同名字段保留成员原申请、文献标识、原著录来源、自己取得的正文及其缺件状态、自己权属、自己法律和辅助观察。`registration_relations` 保存独立的官方事实边，不与一般同族边混合。
- 成员的 `canonical_evidence_link` 始终显示真实 EP PN/authority；`own_fulltext_available` 只检查成员本件正文，绝不因有EP证据变为true。成员的owner、status或地域争议不复制到EP。官方登记获取时间不自动成为冻结截止日的法律状态。
- `population_hash` 绑定映射完整记录，映射新增或变化后原角色结论须重审。成员不允许作为额外独立技术任务导入分析；旧有源资料不删除，旧分析不被自动迁移或冒称为EP分析。

公开映射采用显式字段白名单：只交付官方URL、获取时间、原件哈希、实际字段值、精确定位、身份快照和审阅依据；原始缓存路径及receipt定位只留在数据库内，不随页面导出。详情将国家登记成员单列为卡片，保留成员自己的主体及状态，并将EP原文链接明确标为EP。地域筛选使用 `jurisdictions` 并集，结果仍计独立申请单位，关联登记成员另计；机构统计 `by_authority` 与地域记录统计 `by_jurisdiction_records` 分开展示。

成员自己的普通完整文本可以保留。若成员正文含 `embedded_image_review`，而成员原图尚未纳入页面的原图核验交付流程，则仅展示版本及来源信息，`text_withheld=true`、`complete=false`、`required_embedded_images_delivered=false`，并明确说明未交付原图。`source_qualified` 仅记录数据库来源资格，不等同于已展示完整正文；该成员不能借规范EP申请的原图或分析绕过所需图片门禁。规范申请的必需原图仍在正式render创建文件夹前逐一核验。

测试使用明确标识的synthetic官方格式夹具，覆盖来源、身份、映射图、作用域变化、原记录保留、计数桥接、真实内存备份、导出与页面集合、独立法律与权属、日期统计、角色失效，以及规范单位仍需完整全文的门禁。真实映射必须另外提供可核验原始官方文件及临时库验证记录。
