# 备份、重试与恢复

每次安装在 `/var/backups/thinksmart-muse-music-时间戳/` 创建 root 专用备份，保存**本次会修改的文件**及原权限/属主。备份包含原 Hub 配置，可能含 API Key；权限 0700，不能上传。

在最后开始写入前，下载失败不会改变正在运行的服务。进入安装后出现可捕获错误，会恢复备份、重启原 Hub/屏幕和蓝牙，并停止此次新装的 Muse 服务。意外断电或直接强杀进程不保证自动回退，重新连上 SSH 后手动恢复。

## 手动恢复

把安装结束打印的真实备份目录放在命令末尾，不要照抄示例时间：

```bash
cd ~/thinksmart-muse-music
sudo bash install.sh --rollback /var/backups/thinksmart-muse-music-实际时间戳
```

找不到原记录时，在本机列目录：

```bash
sudo find /var/backups -maxdepth 1 -type d -name 'thinksmart-muse-music-*'
```

恢复的是**那次安装之前的状态**。多次更新后选择哪一个备份很重要。不要手工改 manifest 或从他人机器复制备份。

## 哪些会保留

- 网易云 Cookie 和登录状态；Muse Token、设备身份、配对文件及专用会话 ID。
- 下载到本机的官方 SDK、缓存、已安装的系统依赖及专用普通账号。
- 可选的 Mihomo 代理是独立步骤，不会因撤回 Muse/音乐界面而删除。

这是配置恢复，不是整机卸载。这样能避免一次安装失败把账号配对或现有数据一起删除。本项目不提供“一键删光”，也不处理原厂 eMMC 恢复；原厂恢复请用自己的整盘备份和上游流程。

首次失败后可以重新运行相同安装命令。本项目创建的管理标记允许识别自己留下的 SDK；如果是手动安装的 SDK，会明确停止而不会合并未知权限。
