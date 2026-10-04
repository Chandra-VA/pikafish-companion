# Pikafish Companion · 皮卡鱼棋盘助手

Windows 本机象棋研究工具：识别可见棋盘，调用独立安装的 Pikafish 引擎，查看候选着法和后续变化，暂停同步后手动模拟走棋并比较局面分。

这是独立的助手项目，不是 [Pikafish 官方引擎](https://github.com/official-pikafish/Pikafish) 的源码镜像，也不是腾讯、天天象棋或 xiangqiai.com 的官方产品。使用前请阅读 [免责声明](DISCLAIMER.md)、[安全说明](SECURITY.md) 和 [第三方声明](THIRD_PARTY_NOTICES.md)。

## 功能

- 从选定的天天象棋窗口读取屏幕像素，定位棋盘并识别棋子；支持本机截图导入。
- 根据将帅位置判断方向；自动跟随方向或手动翻转助手棋盘。
- Pikafish UCI 分析，1～5 条候选，显示搜索深度和真实引擎输出的后续变化；可逐步回放。
- 整数局面分，例如 `红分 +1250`，黑方在下时切换为黑方视角；将杀单独显示。
- 开关实时同步。关闭后可点棋子和合法落点连续推演，自动换边、悔棋、返回模拟起点。
- 每步比较引擎首选与所走招法，显示局面分和损失分；评分排队完成，可以继续模拟。
- 校正识别错误、查看识别原图、历史局面、走势及 JSON 导出。

## 快速开始

需要 Windows 10/11 64 位、Python 3.12+，推荐使用 Edge。Node.js 仅用于前端测试。

```powershell
git clone https://github.com/Chandra-VA/pikafish-companion.git
cd pikafish-companion
.\scripts\setup.ps1
```

1. 从 [官方 Releases](https://github.com/official-pikafish/Pikafish/releases) 自行下载适合 CPU 的引擎和对应 NNUE，放置为：

   ```text
   engine/Pikafish-Windows-x86-64-universal.exe
   engine/pikafish.nnue
   ```

2. 准备一张完整、尚未走棋的开局棋盘截图，在本机生成识别模板：

   ```powershell
   .\assistant-env\Scripts\python.exe .\companion\calibrate.py "你的开局截图.png"
   ```

   红方在上时加 `--red-top`；自动定位失败时使用 `--corners`。详见 [安装指南](docs/INSTALL.md)。本仓库不分发游戏截图或识别模板。

3. 双击 `start_companion.cmd`，或运行：

   ```powershell
   .\assistant-env\Scripts\python.exe .\companion\web_app.py
   ```

4. 将网页棋盘与助手并排放置，完整显示棋盘。点击“模拟走棋”暂停同步，点棋子再点绿色落点即可推演。开启实时同步会结束推演并恢复网页局面。

详细说明：[安装](docs/INSTALL.md) · [操作与评分](docs/USAGE.md) · [架构](docs/ARCHITECTURE.md) · [隐私](docs/PRIVACY.md) · [测试](docs/TESTING.md) · [贡献](CONTRIBUTING.md)。

## 限制

- 识别是按具体皮肤校准的模板匹配，不是通用 OCR；皮肤、缩放、选中效果、动画和遮挡会影响结果。
- 静态棋盘无法确定行棋方。首次读取或漏过多步时分别显示红黑假设；识别一手完整落子后自动判断，也可手动指定。
- 引擎分值随版本、NNUE、搜索时间和深度变化。整数单位与常见网页引擎评估一致，不承诺同局面数值完全相同，也不是胜率。
- 合法走棋检查涵盖移动规则和王安全；不实现完整赛事的长将、长捉等重复局面裁定。
- 后续变化是假设最佳应对的搜索结果，不能保证实际对局按此发展。
- 本程序不自动点击游戏落子、不读取账号密码、不注入游戏进程；请仅在平台和赛事允许的场景使用。

## 源码范围

上传助手源代码、前端、测试、脚本与文档。引擎二进制、NNUE、第三方引擎源码副本、虚拟环境、个人图片、模板、运行状态、日志和本机快捷方式均被排除。

源码采用 [GPL-3.0-only](LICENSE)。第三方软件与素材的权利和许可证独立适用，详见 [THIRD_PARTY_NOTICES.md](THIRD_PARTY_NOTICES.md)。

English: a Windows-only local Xiangqi board recognition and analysis companion. Install the official Pikafish engine separately and calibrate with your own initial-position screenshot. This repository contains source code only, not game artwork, personal screenshots or engine binaries.
