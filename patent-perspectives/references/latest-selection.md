# 最近N件技术申请的冻结范围

仅在用户指定最近N件时使用此模式，不把抽样测试自动称为企业全量。用户所称“最近”在本模式固定指申请日，不能改为公开日、优先权日、国家阶段日、全文取得时间或分析完成时间。

先完成母库的主体核验、查询对账及可选申请日期间，再从全部合格规范独立技术申请中排名：`filing_date desc, application_id asc`。仅发明、实用新型占名额；同一申请的A/B版本不重复，外观设计不占名额。已通过同记录官方身份映射的国家登记成员随入选规范申请保留为独立地域记录，不额外占N，不借用规范申请的全文或法律状态。

完整候选的申请日缺失、非法或冲突，技术类型未决、影响候选的主体身份未决、查询未对账、登记映射无效，以及合格候选不足N时均拒绝冻结。不能因该件无全文、正文长、尚未分析而跳到下一件。已知外观和已确定在母期间外的记录保留原行，不进入技术排名。

## 只读检查与派生

以下参数由用户确认的范围决定，将N替换为确认的正整数：

```text
python scripts/derive_latest.py --parent RUN/recent5y.sqlite --count N --report-dir RUN/latest-selection-review
```

默认只读检查，输出私有完整候选排名、日期观察及选择清单。明确创建时增加：

```text
--create --output RUN/latest-N.sqlite
```

目标须是同一运行目录的新文件名，不能覆盖母库或已有子库。脚本以SQLite backup保留全部母表、查询页、文献、正文、已有效分析及证据，继承原公开截止日和申请日期间，赋新run_id与parent_run_id；只追加不可变排名manifest及派生日志。续跑直接使用该子库，不重建同名文件。改变日期间时从未选择的母快照先用derive_scope.py创建期间，再用本命令选N；不能将旧清单悄悄带入新期间。

`application_selections`只允许追加，不允许更新、删除。清单冻结N、排序、候选快照及SHA256、有序所选ID、父子运行身份、实际最大/最小申请日和边界同日取舍。每次选集使用时重新核对完整候选排名；手填任意N个ID、改日期或改公开版本不会通过。正文、语义完成度和新辅助证据不作为排名依据；已有效完成的入选分析继续复用。

`selection-plan.private.json`及创建后保存的`selection-manifest.private.json`包含候选及所选ID，只保留在私有审计目录。若母库在预检后变化，创建报告以实际backup的清单为准。

## 统计、角色与展示

`run.scope.selection`公开以下字段：kind、count、date_field、date_order、tie_break、candidate_count、latest_filing_date、oldest_filing_date、boundary_tie、manifest_id及manifest_sha256。hero只需显示实际选择数和日期边界；完整私有ID清单不塞入页面。`coverage.selection`报告所选规范技术分母及排名已验证。母期间摘要标记before_latest_selection=true，与N分母分别显示。

技术完成及缺文献门禁覆盖全部所选N件。母库检索量、外观及范围外证据不会删除，也不能冒充本次N件的分析量。新选择加入population_hash，旧角色结论保留为不可用历史，不输出页面、不计当前三角色完成；必须依据新范围、统计和适用范围形成三个当前hash结论。逐件有效技术分析与原证据不因此重做。

选择子运行的每条 `insights-import` 输入必须明确提供 `selection_scope`：从当前 `run.scope.selection` 原样复制 kind、manifest_id、manifest_sha256、count、date_field、date_order、tie_break 七个字段，不能提交旧选择或只修改count。自然语言scope仍须明确本次实际范围，指标的application_ids只能来自所选集、value必须等于其实际数量；重新写当前hash不等于旧范围结论已适用。缺少或不匹配的selection_scope会拒绝导入。未使用选择模式的运行兼容原输入。
