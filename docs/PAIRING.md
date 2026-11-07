# Muse 配对：一次完成，之后开机自动连接

## 正常 SSH 方式

1. 手机登录你希望音箱使用的 Muse 账号，开启手机蓝牙，把手机放到音箱附近。
2. 在同一账号的 [Muse Gadgets](https://gadgets.muse.ai/settings/sdk-tokens) 创建 SDK Token。
3. 在音箱的 SSH 窗口运行 `sudo thinksmart-muse-pair`。
4. 看到专用 Token 提示再粘贴。输入完全不显示；按 Enter 后会保存到音箱 root 专用文件，权限 0600。
5. 手机 Muse：Settings → Devices，开启 Developer mode，再 Add Device。
6. 选择终端实际显示的 `MuseGadgetXXXXXX`。每台设备后六位不同，不要照抄别人的设备名。
7. 按 App 提示确认。进入 Wi-Fi 步骤时，Linux SDK 在已联网状态下可能只提供“当前连接”；选择它继续。它会复用已连接的网络。
8. 终端出现 `auth_ok`、`setup complete`、**`Paired.`**，配对完成。
9. 说“小麦小麦，你好，请用一句话介绍自己”，等到完整回答。

配对窗口约 10 分钟。手机不在身边或超时后：

```bash
sudo thinksmart-muse-pair --resume
```

不必重新生成 Token。只有泄露或撤销旧 Token 才重新创建，再运行不带 `--resume` 的配对命令。

## 没有蓝牙选项，不等于没有蓝牙硬件

这款设备有蓝牙硬件。Ubuntu 没有桌面蓝牙菜单也可以通过 BlueZ 完成 BLE 配对。若手机搜不到，检查：

```bash
systemctl is-active bluetooth
bluetoothctl list
rfkill list bluetooth
```

被软件屏蔽时可运行 `sudo rfkill unblock bluetooth` 后重新打开配对。手机找到设备但连接超时，先看 [网络说明](NETWORK.md)，然后切换手机蓝牙再试。本包已包含此前实机遇到的代理网络检查超时修复。

## SSH 提示 PTY allocation request failed

通常是使用了一把禁止交互终端的 SSH 密钥。可以换普通 `ssh ubuntu@音箱IP` 的密码登录；不要修改授权密钥的安全限制来解决输入问题。

已有可用 SSH 密钥且 `sudo -n` 可用时，可以用附带的 Windows 隐藏输入助手。先把本仓库下载到电脑，在该目录 PowerShell 运行：

```powershell
powershell.exe -NoProfile -ExecutionPolicy Bypass -File .\scripts\pair-windows.ps1 -Target ubuntu@音箱IP -Key "你的SSH私钥完整路径"
```

这两个参数都要替换成自己的值。助手先检查连接，成功才显示 `Paste Muse SDK Token (hidden)`；它用标准输入发送 Token，不把 Token 写入命令参数、文件或 PowerShell 命令历史。重开配对时在命令末尾加 `-Resume`。

此助手不会创建密钥或赋予免密 sudo 权限；普通用户推荐前面的正常 SSH 方式。看到 PowerShell 的 `PS ...>` 时**不要直接粘贴 Token**。

## Token 不小心发出去了

立即在 Muse Gadgets 撤销该 Token，创建新的，再用专用提示输入。不要把旧值复制到 Issue。配对文件、Token、浏览器 Cookie、原厂 eMMC 备份都不属于公开代码的一部分。
