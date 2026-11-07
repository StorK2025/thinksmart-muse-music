# 组件与维护边界

## 声音怎样流转

1. `thinksmart-client.service` 提供“小麦小麦”本地唤醒、麦克风采集和音频输出。
2. 小智 Hub 使用 SherpaXASR 把声音变成文字。
3. 本包 `hub/muse_llm.py` 只提取本轮用户问句，不转发旧模型的提示词或历史记录。
4. 音乐和结束对话指令由有限的本机规则处理；其他问题经 Unix socket 交给官方 Gadget SDK。
5. SDK 使用自己的设备凭据连接该用户的 Muse，维护一个专用侧聊。本包用受限权限的 UUID 文件复用这个会话。
6. 回答经本机流式通道回 Hub，由现有 EdgeTTS 转语音播放。

本机没有加载 Muse 大模型，也没有常驻 Muse 浏览器。语音仍是现有小麦音色，并不是 Muse 原生实时音频接口。暂停本机播报/等待不代表取消已经送到 Muse 的云端任务。

## 网易云怎样播放

`play_music` 工具写入用户运行目录里的原子命令文件。单个 WebKitGTK 页面打开网易云官方网页，`kiosk-tools.js` 在页面上添加适合触屏的播放器，通过官网已有控件播放，读取官网音频状态、歌词和歌单。

不使用非官方音乐 API、不导出 Cookie、不破解会员、不下载歌曲。官网 DOM 改动可能影响控制功能；“网易云登录 / 原页”用于正常登录和判断官网本身是否能播放。

切换页面时终止旧的 WebKit 页面进程，Cookie/站点存储保留。音乐页就是播放器，不额外开第二个浏览器。页面麦克风无需授权；录音来自语音客户端。

## 固定版本

| 组件 | 参考版本 |
| --- | --- |
| 基础镜像 | justhalfbit/thinksmart-ubuntu-image，20261101 |
| 语音客户端 | 0.1.3 |
| Hub | 验收环境 9bfa987；打包只读核对为 38b5daaf |
| Muse SDK | 0.1.0，463bd2a05380fea4211b0099ad0f70933c108b20 |
| 可选 Mihomo / MetaCubeXD | 1.19.33 / 1.274.4 |

基础镜像和客户端由上游部署，本包不捆绑或自动升级它们。SDK 首次下载固定提交，并校验三个原文件的 SHA-256；`sdk/upstream-lock.json` 记录这些值。

## SDK 的三个本地修改

| 文件 | 原因与改动 |
| --- | --- |
| `muse-network.py` | 配对时原网络检查直接连 API，忽略代理，导致手机先超时。现在使用带证书校验的代理 HTTPS 检查，3 秒有界等待，不发送账号凭据、不跳过认证 |
| `muse-service.py` | 实机用户回显事件可能比状态事件序号小；单一序号水位丢失当前问句。改为单独追踪用户回显，保留会话/请求绑定与防重放；增加可选流式本地回复、断开等待和清理 |
| `muse-link-client.py` | 显式创建系统可信 TLS 上下文，继续校验证书和主机名 |

三个文件是 Apache-2.0 衍生文件，保留 Meta 原版权头。上游相关问题：[327](https://github.com/facebookincubator/muse-gadget-sdk/issues/327)、[330](https://github.com/facebookincubator/muse-gadget-sdk/issues/330)。更新 SDK 时要重新评估改动，不能将补丁盲目覆盖到新版本。

## 本机文件与权限

| 位置 | 用途 |
| --- | --- |
| `/var/lib/musegadget/` | 官方身份、Token、配对凭据；root 专用 |
| `/run/musegadget/musegadget.sock` | root 与运行 Hub 的组可访问的本地连接 |
| `/var/lib/thinksmart-muse/session-id` | 专用会话 ID；运行 Hub 的账号持有，0600 |
| `/etc/thinksmart-muse/proxy.env` | 验证过的无账号密码代理地址；root 0600 |
| `~/.local/share/thinksmart-kiosk/` | 本机网易云登录数据 |
| `/var/lib/thinksmart-muse-music/` | 本安装器的固定源码缓存和安装元数据；root 专用 |
| `/var/backups/thinksmart-muse-music-*` | 配置备份；可能含凭据，不公开 |

官方 SDK 服务因蓝牙及凭据管理以 root 运行；Muse 发来的设备命令使用 **musebridge** 普通账号执行，没有登录 shell、没有 sudo。它的主组与 Hub 用户相同，以便访问 socket；这不是文件系统沙箱，仍可读取该组/全局允许读取的文件。请只配对自己的 Muse 账号。本项目没有增加设备控制命令。

## 开发与验证

离线 Python 检查不需要账号：

```bash
python3 tests/verify_muse_direct.py
python3 tests/verify_muse_network.py
python3 -m unittest discover -s tests -p 'test_*.py'
node --check app/kiosk-tools.js
```

SDK 事件测试需该固定版本的官方 `musegadget` 依赖：已安装设备上用 `sudo /opt/musegadget/venv/bin/python tests/verify_muse_service.py`。CI 使用同一提交。没有把真实录音、Token、账户事件或其他人的聊天作为测试数据。
