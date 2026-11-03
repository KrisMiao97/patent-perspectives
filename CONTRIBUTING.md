# 参与改进

可通过[Issues](https://github.com/KrisMiao97/patent-perspectives/issues)提交问题，或通过Pull Request提出修改。

反馈时说明技能版本、Python版本、操作系统、最小复现步骤、预期与实际行为。优先提供合成材料；删除密钥、签名链接、企业私有资料和个人路径。

研究方法改动应保留同件来源、版本、独立复核及未知状态边界。不要用测试通过替代专利原文判断，也不要把具体企业事实写死在通用代码中。

提交前在仓库根目录运行：

```bash
python -B -m unittest discover -s patent-perspectives/tests
python patent-perspectives/scripts/check_package.py
python examples/synthetic-optics/generate_demo.py --output work/contribution-demo
```

页面改动还需在浏览器检查角色切换、原文入口、键盘、窄屏和移动目录。贡献受仓库[MIT许可](LICENSE)约束；请保留第三方材料自身的来源与许可。
