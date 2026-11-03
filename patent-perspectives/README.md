# 专利棱镜｜可安装技能

当前版本：`2026.11.02-unified1-pub1`。研究流程基线为2026.11.02统一版，公开修订增加许可、说明与发行打包。

将本文件夹整体放入宿主的技能目录，确保[SKILL.md](SKILL.md)位于文件夹第一层。向支持技能的AI助手提出需求，例如：

```text
使用 $patent-perspectives 研究【公司】的【技术方向】。
先核验主体和资料，再确认范围；逐件完整理解并独立复核，
围绕具体问题比较真实方案，将有证据的答案写入三视角报告。
```

核心脚本需Python3.10+标准库。真实研究另需能调用工具、阅读原文的AI宿主和已授权的专利数据来源；安装技能不会自动授予账号或数据权限。

```bash
python scripts/patent_perspectives.py --version
python scripts/patent_perspectives.py --help
```

资料与数据库放在本技能目录之外。技术申请采用[整篇阅读与独立复核](references/whole-patent-research.md)，并按[问题与比较契约](references/research-workflow.md)形成研究发现。

完整介绍、标准库合成演示、截图、更新记录及发行下载见[GitHub仓库](https://github.com/KrisMiao97/patent-perspectives)。本技能按[MIT许可](LICENSE)分发；[原创及第三方资料边界](ORIGINALITY.md)另行说明，不改变来源资料自身的权利。
