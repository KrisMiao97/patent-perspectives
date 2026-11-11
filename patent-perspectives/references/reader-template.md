# 阅读模板的使用与数据契约

输出方向以 [DESIGN.md](../DESIGN.md) 为准；此处规定可运行资源怎样接入。模板是事实呈现层，不替代检索、阅读和研究质量门禁。

## 运行
在技能目录执行：

```text
python scripts/render_reader.py --input assets/reader/example.json --demo --output /任务输出/模板预览.html
python scripts/render_reader.py --input /任务数据/reader.json --db /任务数据/run.sqlite --output /任务输出/报告.html
```

第一条只接受 synthetic=true，页面明确标识合成示例；不得用于真实研究。第二条要求原数据引擎 validate 完成，核对企业、截止日、材料/检索模式和完整目录 ID 集合；引用的原文、短引文和公开号与数据库一致。界面生成成功只说明呈现通过，不增加研究结论的确定性。

## reader.json
以 example.json 为可运行结构样本，清空合成事实后按真实记录填写，不沿用案例数量或产品名。

- company、business：真实公司名及有来源的业务背景，避免只写“目标公司”。
- scope：mode=search/materials、label、as_of、status_observed_at、disclosure_date、partial_years。材料范围写明清单边界。
- records：每项 id（独立申请ID）、title、publication、type、filing_date、product、status、read_complete、evidence_ids。导入前字符串化ID；未知日期可用null；外观设计以design单列，无技术正文时evidence_ids可为空，页面明确提示没有可展示的原文。
- sources：id使用数据库 evidence.id，title、publication、version、locator、quote、text及可选url。quote必须匹配text；真实运行从数据库重新绑定版本、位置和状态，不能伪造原文。
- roles：management/rd/ip 各有 title、answer、scope_label、reasons（每项title、text、evidence_ids）。答案由研究者按证据撰写；不能用标题问句加数值代替答案。
- chapters：id、title、kind（trend/directory/comparison或普通文字）、conclusion、scope_label、body、evidence_ids。每章必须有结论；可依据研究任务增加章节，不能用缺证的空图填数。
- orders：三个角色各自的章节顺序，必须包含同一套共享章节ID。角色切换保留当前章；概览按钮明确回到该角色首章。

模板已提供：同页三角色概览、三种版式、章节导航、固定结论与筛选范围区分、年度柱图、全历史数量展开、搜索/产品筛选、外观目录、20件分页、证据弹窗和原位返回。目录结论按当前集合计算；其他章节的文字结论是注明范围的固定研究发现，不能随筛选冒充重算结果。

## 与既有复杂报告连接
复杂技术时间图、同族关系图和逐格权利要求矩阵继续复用 assets/panorama 的组件及数据契约。不要把它们删掉，也不要声称阅读模板已经实现这些功能。按具体研究需要在相应章节挂载；使用相同申请ID、证据ID和筛选集合，按首次进入、空数据、直达和原文返回验收。正式交付不可只做模板预览就标研究已完成。

若一次交付需要复杂组件而尚未完成迁移，用既有 render 引擎生成完整资料页，并按设计规范改造真实页面；说明实际交付的界面，不暗中退回旧的零值大表与角色空壳。先保留真实基线，再修改与验证。

## 性能与可读性验收
分别实测三个角色首次打开、三种版式、1440/1100/390及320窄屏。检查每章答案、图例、所有数字的名词绑定与原文入口，不只检查标题存在。大数据用真实规模或明确合成压测；目录仅挂载当页，搜索防抖，复杂图谱按需展开。用减少、持平、零分母、空筛选、外观设计、不同ID类型覆盖高风险逻辑。

自包含阅读页可断网、移动目录后打开。外链不是离线原文；PDF、图像或复杂组件另有资产时一起打包并实测迁移。打印只含当前渲染章节及分页，不冒称完整档案打印。需要全文打印时另做专门导出并验证实际分页。
