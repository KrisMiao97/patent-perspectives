# 已审阅例外的可复现交付

只有用户已明确要求按现有可核验成果交付，并且存在可逐项解释的资料缺口时使用。本方式保留完整数据库及全范围验证的真实状态，未读技术申请不产生技术结论，主体待核候选不并入公司统计。

## 准备与运行

运行数据在技能文件夹外。相对原件路径以数据库所在目录为根；移动数据库时须一起移动所引用的原件、图像和获取回执。核心引擎要求 Python 3.10+。德国 Patentblatt PDF 与 WO 扫描权利要求适配器另需 pypdf、Pillow 和 PATH 中的 Poppler pdftoppm；CN 公式图转写校验需 Pillow。奥地利 seeip JSON 与原有 DPMA HTML 适配器不需要 PDF 依赖。依赖缺失或官方取证格式不符须停止核验，不能据此豁免身份或正文错误。

1. 用 `validate` 保留全范围错误；先修复完整性、引用、范围、映射或失效分析错误。
2. 维护一份 Markdown《分析记录与后续补充说明》，每个缺口写稳定问题编号、application_id、原因、对报告影响和补充方法。
3. 生成草稿：
   `python scripts/patent_perspectives.py --db RUN.sqlite delivery-draft --report-context CONTEXT.json --analysis-records NOTES.md --output CONTRACT.json`
4. 宿主逐项核对草稿；填写实际用户指示 `user_direction`、真实展示范围 `report_scope_statement`，以及每项 `issue_id/reason/effect_on_report/next_step`，完成后才将 `reviewed_by_host` 设为 true。该字段记录宿主审阅，不代表作者本人签字。
5. 用同一数据库、上下文和说明生成：
   `python scripts/patent_perspectives.py --db RUN.sqlite render --report-context CONTEXT.json --delivery-contract CONTRACT.json --analysis-records NOTES.md --output REPORT_DIR`

不用删除记录，不改 synthetic，不替换完整验证函数，不调用只用于合成数据的 preview。草稿与渲染从只读数据库事务读取。完整无缺口的案例继续使用普通 render。

## 不变量

仅可列入两种错误：`population_review_pending` 与 `technical_analysis_missing`，且必须精确到每个申请。查询不完整、身份映射失败、引文不符、角色结论过期等错误不能豁免。

契约绑定全部业务表内容（事件日志除外）、完整验证结果、展示申请清单、报告上下文及说明文本。新增、删除、变更数据或说明后须重新核验，不能自动重签旧契约。技术分母必须与已读数和精确缺口对账。

输出仍保留 `validation.json` 的 incomplete；`delivery-validation.json` 只确认这次列明例外的交付通过。正文显示实际研究范围、目录/已读分母与结论限制，过程事项集中到独立说明。报告数据脱敏不得改变原始正文、引文及其位置；若发生冲突，停止生成并单独处理来源。

## 验收

验证普通 render 仍会拒绝未完成母库；列明例外交付成功后，母库验证状态、全部候选记录和未读标记保持不变。修改来源、上下文、说明、例外清单或加入新错误都须阻止生成，失败不留下半成品报告。

另用真实数据验证页面离线打开、三角色切换、目录移动和原文定位。保存正式技能文件清单、输入指纹、运行结果与输出清单，避免把独立页面改版当作正式 Skill 的运行成果。
