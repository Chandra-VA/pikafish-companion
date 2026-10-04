# 第三方软件、素材与致谢

| 项目 | 用途 | 上游与许可 |
| --- | --- | --- |
| Pikafish | 独立运行的 UCI 象棋引擎 | [官方仓库](https://github.com/official-pikafish/Pikafish)，[GPL v3](https://github.com/official-pikafish/Pikafish/blob/master/Copying.txt) |
| NumPy | 棋子掩模与模板匹配 | [项目](https://numpy.org/)，[许可](https://github.com/numpy/numpy/blob/main/LICENSE.txt) |
| Pillow | 本机图片解码、裁剪和缩放 | [项目](https://python-pillow.github.io/)，[许可](https://github.com/python-pillow/Pillow/blob/main/LICENSE) |
| Python | 运行时和标准库 | [项目与许可](https://docs.python.org/3/license.html) |
| Windows / Edge / .NET Framework | 屏幕捕获、浏览器界面及可选启动器编译 | 用户自行安装的系统组件，其许可独立适用 |

本仓库的 GPL-3.0-only 适用于原创助手源码，不声称拥有上游 Pikafish 引擎或第三方图像的权利，也不覆盖第三方软件自身许可证。

引擎通过独立子进程和 UCI 标准输入／输出调用，本仓库不提供其二进制、NNUE 或完整源码镜像。请从官方上游获取、保留其作者声明和许可证。若另行打包分发引擎，须根据其许可证履行对应源码、声明等义务，不能以本仓库的声明代替。

本机棋盘识别模板由使用者自己的截图生成。游戏界面、商标及皮肤不因校准而改变权利归属；这些图片和模板不纳入本仓库许可证或分发范围。

界面布局参考象棋分析工具的常见交互，网页、棋盘 SVG 和业务代码为本项目实现，不复制第三方网页源码或图片资源。感谢 Pikafish 及其上游贡献者、NumPy 和 Pillow 社区。
