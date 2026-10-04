# 测试和复现

在项目根目录运行：

```powershell
.\assistant-env\Scripts\python.exe -m unittest discover -s companion -p "test_*.py" -v
node --check companion/web/main.js
node companion/test_score_units.cjs
```

核心测试覆盖合法走棋、将帅照面、开局两层合法局面计数 1920、模拟与悔棋、过期代次、同步开关、整数评分视角／损失、将杀表示和本机 API 的来源／令牌校验。

缺少以下可选本机数据时，对应测试会明确跳过，而不是把跳过当作验证通过：

- `engine/Pikafish-Windows-x86-64-universal.exe` 和 `engine/pikafish.nnue`：真实引擎集成搜索。
- `companion/reference-board.png`、`regression-board.png`、`templates.npz`：原始私人截图回归。它们不随仓库分发；已有素材的本机可运行历史回归，新使用者应根据自己的合法素材编写匹配的测试。

无模板启动和控制器稳定帧／轮次逻辑有不依赖个人图片的测试。真实皮肤识别的准确率不能由这些核心测试代替。

GitHub Actions 配置在 Windows 上运行 Python 3.12／3.14 的核心检查与 Node.js 语法／评分检查，不自动下载引擎，也不含私人截图。工作流是否实际运行成功应以仓库 Actions 结果为准。
