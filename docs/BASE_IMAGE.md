# 从原厂设备到可安装状态

## 你现在在哪一步

| 屏幕状态 | 下一步 |
| --- | --- |
| 原来的 Teams / Android 系统 | 先完整备份 eMMC，再照上游刷机教程操作 |
| postmarketOS 登录提示 | 这通常是刷机用的中间系统；先完成 Ubuntu 镜像步骤 |
| ThinkSmart 欢迎页、能连接 Wi-Fi | 连接网络，确认语音客户端和小智 Hub 可用 |
| 已有“小麦小麦”的语音界面 | SSH 登录后运行本项目环境检查 |

## 原厂机器先刷基础镜像

使用 [20261101 发行版](https://github.com/justhalfbit/thinksmart-ubuntu-image/releases/tag/20261101) 和 [对应官方仓库刷机教程](https://github.com/justhalfbit/thinksmart-ubuntu-image/blob/804e83f7b5aeaa8b63d92d413372d732839e1fb8/README.md)。型号必须是 **CD-18781Y**。教程包括驱动、EDL、原厂备份、bootstrap、分区和最终镜像步骤。

1. 准备电源、可靠的 USB 数据线、电脑和足够大的备份磁盘。
2. 按教程进入 EDL，识别设备，先做**整盘 eMMC 备份**，确认备份完整。原厂备份不能公开上传。
3. 严格按“首次刷机”或“已经刷过 Ubuntu”的对应路线完成，不混用分区命令。
4. 最终启动 Ubuntu，连接 Wi-Fi。看到 postmarketOS 的 `thinksmarter login:` 不能直接运行本项目安装器。

本仓库不再次封装 EDL 写盘，避免把不同设备状态混在“一条命令”中。刷机是唯一涉及系统和分区覆盖的环节；请对照上游每一步的预期输出。

## 建立 SSH 连接

1. 从设备欢迎页或路由器管理页面找到音箱的 IP，电脑与音箱接入同一局域网。
2. Windows 打开 PowerShell；macOS/Linux 打开终端。
3. 输入 `ssh ubuntu@音箱IP`，把“音箱IP”替换成实际地址。
4. 首次连接核对设备后接受主机指纹，输入镜像文档提供的初始密码。输入密码时不显示字符。
5. 出现 `ubuntu@thinksmarter:~$`，说明接下来的命令是在音箱里执行。`PS C:\...>` 仍是电脑窗口。

Windows Terminal 可以使用 **Ctrl+Shift+V**；普通 PowerShell 可尝试右键粘贴。一次粘贴一块命令，等它结束再贴下一块。

首次使用请运行 `passwd` 更改 `ubuntu` 密码。若按上游建议锁定 root 密码，使用 `sudo passwd --lock root`；`--lock` 是完整单词，避免把字母 l 误写成数字 1。

## 确认基础组件

电脑浏览器打开 `http://音箱IP:16688/admin/`，按页面提示设置自己的后台密码。

- “语音识别”选 **SherpaXASR**，模型下载完成。
- “语音合成”选 **EdgeTTS**。
- 设备的语音客户端连接本机 Hub。使用上述集成镜像时已预配置；若缺失请照 [客户端部署说明](https://github.com/justhalfbit/xiaozhi-thinksmart-client) 恢复。
- 本项目安装后默认模型会改成 Muse，因此不必为了本项目购买或填写 DeepSeek API Key。
- 参考环境：客户端 **0.1.3**；Hub 曾在 `9bfa9871d0f8beeb84764392b42dab2ef9507b28` 上配置，打包时实机为 `38b5daaf021ae071aa2b7589da6af08387c55673`。安装器不自动升级或回退已有 Hub。

然后回到 [README 的快速安装](../README.md#快速安装已经刷好-ubuntu-的设备)。普通 x86 电脑、其他型号、未经配置的纯 Ubuntu 不在本版自动安装支持范围内。
