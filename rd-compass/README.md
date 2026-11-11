# 研发罗盘 · R&D Compass

简体中文 · [English](README.en.md)

**从产品、公司或已有技术路线出发，把专利和技术资料整理成下一代产品的候选机会，并说明什么条件会改变取舍。**

[下载免账号互动演示](docs/rd-compass-synthetic-demo.zip?raw=1) · [查看合成输入](rd-compass/references/synthetic-demo.json) · [下载 WorkBuddy 更新包](workbuddy/rd-compass-workbuddy-0.3.1.zip?raw=1)

## 无需账号的合成演示

桌面加湿器有两种清洗设计。一种扩大固定水槽开口，让手和清洁布更容易够到内壁。另一种让水槽和短导水件一起取出，把倒水、冲洗和晾干移到水池边。报告解释了为什么残水和复装会改变两条路线的取舍。

[![研发罗盘合成演示。首屏展示研究发现、产品机会和当前判断，随后比较两条清洗路线。](docs/preview.png)](docs/rd-compass-synthetic-demo.zip?raw=1)

演示材料和日期均为虚构。下载并解压演示包，用浏览器打开 `index.html`，即可离线比较方向、点击证据编号、筛选资料和下载样例数据。浏览演示无需账号、API 密钥、Python 或安装技能。

## 什么时候用

| 你已有的起点 | 研发罗盘回答什么 |
| --- | --- |
| 只有产品，还没决定改哪里 | 哪些技术差异可能改变使用方式，形成什么产品机会？ |
| 选好了公司、专题或技术路线 | 同一任务有哪些可比的做法，哪些条件限制借鉴？ |
| 已经有改进问题或几个方案 | 每条路线适用于什么条件，哪些新证据会改变选择？ |

可以独立使用，也可以接续[专利棱镜](https://github.com/KrisMiao97/patent-perspectives)或批量专利阅读的结果。分析会在影响判断时回查原文、找简单基线和相似实现，然后按“材料披露 → 方案差异 → 可能能力 → 成立条件 → 尚存假设”说明依据。报告分别说明方向是否值得研究，以及进入立项讨论还缺什么。

## 如何开始

- **支持 Agent Skills 的工具**：安装本仓库的 [rd-compass](rd-compass/) 目录，再指定一个产品、技术路线或一组材料。例如：“使用研发罗盘研究桌面加湿器。比较原位擦拭和把部件拿到水池冲洗的方案，说明已有证据、改进机会和成立条件。”
- **WorkBuddy**：在技能页面选择「添加技能 → 上传技能」，导入 [WorkBuddy ZIP](workbuddy/rd-compass-workbuddy-0.3.1.zip?raw=1)。[官方上传说明](https://www.workbuddy.cn/docs/workbuddy/From-Beginner-to-Expert-Guide/Function-Description/Skills-Market)
- **本地复现演示**：从仓库根目录运行下列命令。需要 Python 3.10 或更新版本，脚本使用标准库。

```sh
python rd-compass/scripts/render_report.py rd-compass/references/synthetic-demo.json --output synthetic-report.html
```

真实任务使用你提供的资料和已授权的数据源。查看[研究工作流](rd-compass/references/research-workflow.md)、[报告设计规范](rd-compass/DESIGN.md)和[数据格式](rd-compass/references/output-format.md)。

[版本记录](CHANGELOG.md) · [WorkBuddy 上架文案](workbuddy/marketplace-copy.md)
