# 上游来源与许可证

| 内容 | 来源 | 许可证与处理 |
| --- | --- | --- |
| 屏幕程序基础代码 `app/thinksmart-kiosk.py` | [HalfBit ThinkSmart image](https://github.com/justhalfbit/thinksmart-ubuntu-image)，参考提交 804e83f7b5aeaa8b63d92d413372d732839e1fb8 | MIT；保留 HalfBit 署名，全文在 `licenses/thinksmart-image-MIT.txt` |
| `sdk/muse-network.py`、`sdk/muse-service.py`、`sdk/muse-link-client.py` | [Meta Muse Gadget SDK](https://github.com/facebookincubator/muse-gadget-sdk)，固定提交 463bd2a05380fea4211b0099ad0f70933c108b20 | Apache-2.0；保留 Meta 文件版权头，全文在 `licenses/muse-sdk-Apache-2.0.txt`；本地变更见架构文档和各文件修改标注 |
| 安装时下载的完整 SDK | 同上 | 直接从官方仓库拉取固定提交；其许可证、声明随源文件保留 |
| 基础 Ubuntu 镜像、小智 Hub、语音客户端 | [image](https://github.com/justhalfbit/thinksmart-ubuntu-image)、[Hub](https://github.com/justhalfbit/xiaozhi-hub-server)、[client](https://github.com/justhalfbit/xiaozhi-thinksmart-client) | 外部依赖，遵循各自许可证；本仓库不再分发镜像/完整 Hub/客户端 |
| 可选 Mihomo、MetaCubeXD | [Mihomo](https://github.com/MetaCubeX/mihomo)、[MetaCubeXD](https://github.com/MetaCubeX/metacubexd) | 安装时从官方 Release 获取，仓库不分发二进制或面板源码；使用及再分发须遵守各自许可证 |

本项目新增的安装工具、Muse provider、网易云界面与文档采用根目录 MIT 许可证，不能据此把 Apache 衍生文件重新声明为仅 MIT。

网易云音乐页面、歌词、封面、音频以及 Meta/Muse 品牌不在本项目授权范围内。本仓库只包含连接和界面代码，没有附带账号、会员权益、第三方媒体或服务承诺。
