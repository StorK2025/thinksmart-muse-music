# 按现象排错

先运行 `sudo bash install.sh --doctor`。提交 Issue 时只写设备型号、基础镜像版本、步骤、现象及脱敏后的错误类型。不要上传 Token、订阅链接、完整 `.config.yaml`、Cookie、整盘备份或整段私人聊天日志。

| 现象 | 检查与处理 |
| --- | --- |
| PowerShell 提示命令不存在 | 先 `ssh ubuntu@音箱IP`；Linux 命令要在 `ubuntu@thinksmarter:~$` 后执行 |
| 提示“不支持此环境” | 核对 CD-18781Y / ARM64 / Ubuntu 24.04 集成镜像；不是 postmarketOS 中间系统或电脑 |
| 提示缺少 SherpaXASR / EdgeTTS | 在小智后台先完成本地识别模型下载及播报设置 |
| 找不到 Muse Developer mode / Token 页面 | 当前账号未具备所需入口，本包不能替你获得账号资格；先确认官方账号可用 |
| `/dev/tty` / `PTY allocation request failed` | 按 [配对文档](PAIRING.md) 使用普通 SSH 或 Windows 隐藏输入助手 |
| 找得到设备但配对超时 | 确认音箱能通过所选代理访问 Muse，手机蓝牙关开，再 `--resume`；已包含代理检查超时适配 |
| Wi-Fi 步骤后失败 | 确认没有换过 SDK/BlueZ 配置；安装器按官方 SDK 设置 MTU 256，再检查网络与账号认证 |
| 只说“转交给 Muse”，没有答案 | 当前可能仍使用旧的转交插件。小智后台默认模型应为 Muse；本包 provider 直接等待回答，补丁也处理了乱序用户事件 |
| 第一句能回答，第二句没声音 | 不要单独升级 SDK 覆盖三个适配文件；本包锁定 SDK 版本并包含连续回复回归测试 |
| 提示 Muse 还在处理 | 可能是云端长任务或网络延迟，等待上限 120 秒；不会自动重复提交。可去 Muse App 查看，不等同于任务已经取消 |
| 重启后没声音 | `--doctor` 看蓝牙、Muse、客户端、屏幕、Hub 状态；确认麦克风物理开关、音量和网络。播报还依赖 EdgeTTS 网络 |
| 网易云显示空歌单 | 点“网易云登录 / 原页”，确认已登录；回播放器 → 播放列表 → 我的歌单 → 刷新 |
| 有歌名但不播放或只试听 | 在网易云原页直接测试该歌；检查会员、单曲购买权限、地区及官网提示 |
| 没歌词 | 先确认官网该歌曲有歌词；播放器会打开官网歌词面板读取当前行，不是本地下载歌词 |
| 暂停按钮变回播放状态 | 当前实现把点击发回官网播放器并读取真实状态；若官网改版，先在原页测试再报版本及现象 |
| 面板返回 405 | 该接口只允许 GET，不用 `curl -I` 判断面板是否正常 |
| `path is not subpath of home directory` | Mihomo 测试命令需要 `-d /var/lib/mihomo`，与服务启动保持一致 |
| 能连代理但 GitHub TLS 失败 | 选到不可用节点；“Connection established”不是源站 TLS 成功，按 [网络说明](NETWORK.md) 换节点 |

## 只在本机看日志

```bash
sudo journalctl -u musegadget -n 50 --no-pager
sudo journalctl -u thinksmart-kiosk -n 30 --no-pager
systemctl --user status xiaozhi-hub --no-pager
```

SDK 日志主要是连接状态。Hub 自己可能记录问句和回复；完整业务日志不要公开提交。需要帮助时优先复制**错误类型和发生阶段**，删掉设备 ID、URL 查询参数、账号和聊天内容。

## 更新注意

本包替换屏幕启动代码、添加 Hub provider 和音乐插件，并安装 SDK 的三个适配文件。基础镜像在线更新可能覆盖屏幕文件，Hub 的更新也可能更改插件接口。不要一边对话一边升级；先留备份、阅读版本说明，再重新运行本包检查。不要用 `pip install -U musegadget` 覆盖受验证的 SDK。
