# 安装、校准与启动

## 环境

Windows 10/11 64 位，Python 3.12 或更高。已验证的本机环境为 Python 3.14.6、NumPy 2.5.3、Pillow 12.3.0；依赖范围见 `requirements.txt`，不保证范围内每个组合都经过测试。

Edge 推荐用于独立应用窗口；若未找到 Edge，助手尝试使用系统默认浏览器。Python 必须能执行 `venv` 和 `pip`。

```powershell
.\scripts\setup.ps1
```

此脚本只在项目目录创建 `assistant-env` 并安装依赖，不下载引擎、不生成模板、不修改系统权限或执行策略。若 PowerShell 策略阻止脚本，可直接执行以下命令：

```powershell
python -m venv assistant-env
.\assistant-env\Scripts\python.exe -m pip install -r requirements.txt
```

## 官方引擎

从 [Pikafish 官方 Releases](https://github.com/official-pikafish/Pikafish/releases) 获取适合 CPU 的 Windows 引擎和同一发布版本对应的 NNUE。选择通用指令版本可减少指令集兼容问题。将文件放置或重命名为：

```text
engine/Pikafish-Windows-x86-64-universal.exe
engine/pikafish.nnue
```

引擎及网络模型不随本仓库分发。先核对官方文件摘要和许可证，保留来源信息。不要将其他来源程序仅重命名为官方文件名。

可运行 `.\assistant-env\Scripts\python.exe .\check_engine.py` 验证 UCI 握手、NNUE 加载和搜索。它会在本机生成忽略的日志及验证记录。

## 本机模板

在与准备研究的棋盘相同皮肤和缩放下，取得自己有权使用的完整开局截图。双方应各有 16 个棋子，未走任何一步；文字清晰，不能有鼠标、选中光圈、动画或窗口遮挡。

```powershell
.\assistant-env\Scripts\python.exe .\companion\calibrate.py "开局截图.png"
# 红方在上：
.\assistant-env\Scripts\python.exe .\companion\calibrate.py "开局截图.png" --red-top
```

自动定位失败时，测量截图内左上、右下棋盘交点的中心坐标，依次指定 `LEFT TOP RIGHT BOTTOM`。下面的数字仅为格式示例，需要换成你自己的坐标：

```powershell
.\assistant-env\Scripts\python.exe .\companion\calibrate.py "开局截图.png" --corners 80 90 640 720
```

成功后生成 `companion/templates.npz`，只有掩模和标签，不复制整张截图。模板仍应留在本机。换皮肤或识别不稳定时重新校准，并重启助手。新模板通过开局自检不等于对所有中残局都能准确识别。

## 启动

双击 `start_companion.cmd`，或在终端运行 `.\assistant-env\Scripts\python.exe .\companion\web_app.py`。服务默认位于 `http://127.0.0.1:18765/`，网页窗口与助手棋盘应并排且完整可见。

可选：运行 `.\scripts\build-launcher.ps1`，使用系统 .NET Framework 的 C# 编译器生成 `PikafishAssistant.exe`。编译器不存在时继续使用命令脚本即可。

源码路径按项目目录定位，不依赖某个桌面目录。移动项目后，建议重新创建 Python 虚拟环境，并更新自己创建的快捷方式；不要上传环境或快捷方式。

## 常见问题

- “请先用开局棋盘校准”：缺少模板，或校准后尚未重启。
- 找不到引擎／NNUE：检查上面的两个文件名和位置。
- 无窗口／棋盘被遮挡：切换到棋盘标签页，取消最小化并移开覆盖棋盘的窗口。
- 橙色格子：移开鼠标和选中效果，等待动画结束；仍有误差则校正或重新校准。
- 端口冲突：关闭旧助手，等待服务退出；不要通过公网代理解决。
- 启动后立即关闭：用终端启动 `web_app.py` 查看错误，不要上传未脱敏的完整日志。
