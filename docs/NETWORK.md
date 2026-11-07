# 网络和代理

Muse 的 API、长连接和 GitHub 都要能从**音箱本身**访问。电脑浏览器能打开，不代表音箱已经走代理。

## 已有可用代理：最短路径

音箱已有 Mihomo / Clash，端口 7890：

```bash
curl --proxy http://127.0.0.1:7890 --max-time 20 -I https://github.com/
```

能收到源站 HTTP 响应而不是 TLS 错误后，安装时加：

```bash
sudo bash install.sh --proxy http://127.0.0.1:7890
```

这个选项用于下载 SDK，以及 Muse 服务和配对。网易云默认直连，避免境外节点改变音乐地区权限。它不修改全系统路由、不启用 TUN、不把代理开放到局域网。

## 只有电脑上的 Clash

在电脑 Clash 中确认 HTTP 或 mixed 端口，选择可用节点，并按该客户端说明开启“允许局域网”。只在自己信任的局域网使用，按需配置电脑防火墙。

音箱上测试 `http://电脑局域网IP:端口`，安装时将它作为 `--proxy` 参数。不要填 `127.0.0.1`：**音箱上的 127.0.0.1 指音箱自己**。电脑关闭后此方案不能继续代理 Muse；长期使用建议下一节的本机代理。

## 在音箱内安装 Mihomo（可选）

此步骤只适用于**尚未安装 Mihomo 的音箱**。脚本发现已有配置、程序、服务或数据目录会停止，不覆盖别人的节点和订阅。代理程序与面板从各自官方 Release 下载、按固定 SHA-256 验证；仓库不提供订阅或节点。

### 1. 从自己的 Clash 导出完整配置

在电脑 Clash 中先选择要使用的订阅并更新，确认已经出现可用节点，再把**完整 Clash YAML** 导出到仓库以外的位置，例如你的“下载”文件夹。不同客户端可能叫“查看配置”“打开配置目录”或“导出配置”。

文件应包含 `proxies:`（节点）或 `proxy-providers:`，以及 `proxy-groups:` / `rules:` 等。只有一行订阅链接、只有引导节点、或 base64 文本不能代替完整配置。文件含有你的节点凭据，**不要发到 Issue，也不要放进本仓库**。

电脑 PowerShell 把文件复制到音箱，路径和 IP 替换成自己的：

```powershell
scp "C:\Users\你的用户名\Downloads\clash.yaml" ubuntu@音箱IP:/tmp/thinksmart-clash.yaml
```

### 2. 音箱上运行安装

```bash
cd ~/thinksmart-muse-music
chmod 600 /tmp/thinksmart-clash.yaml
sudo apt-get install -y python3-yaml
sudo python3 scripts/install-proxy.py --config /tmp/thinksmart-clash.yaml
```

下载 GitHub 也需要代理时，在最后一条命令末尾加 `--bootstrap-proxy http://电脑局域网IP:端口`。这是下载时的临时借路，安装后的代理在音箱里运行。

安装后：HTTP/mixed **7890**；面板 **9090**；都仅监听本机。Mihomo 以独立普通账号运行，开机自动启动，节点选择会保存。验证时使用和服务相同的 `-d /var/lib/mihomo`，避免“path is not subpath of home directory”错误。

### 3. 电脑打开面板，选择节点

电脑**新开一个 PowerShell**，保持这个窗口开着：

```powershell
ssh -N -L 19090:127.0.0.1:9090 ubuntu@音箱IP
```

输入 SSH 密码后窗口没有输出、没有返回命令提示符是正常的；它在维持隧道。浏览器打开 **http://127.0.0.1:19090/ui/**。

面板需要后端地址时填 **http://127.0.0.1:19090**，Secret 留空（只在 SSH 隧道内访问）。在“代理”中打开实际使用的选择组，选择可用节点。如果配置使用代理提供者，可以在面板“代理提供者”刷新；若导出配置本身只有引导节点，需要在原 Clash 里切到完整订阅并重新导出。

选好后，在另一个音箱 SSH 窗口测试：

```bash
curl --proxy http://127.0.0.1:7890 --max-time 20 -I https://github.com/
```

**`200 Connection established` 只说明连上代理，不代表后面的 TLS 成功。** 后面仍有 `SSL_ERROR_SYSCALL` / `gnutls_handshake` 时换节点重试。能正常连接后再安装 Muse：

```bash
sudo bash install.sh --proxy http://127.0.0.1:7890
```

### 4. 之后更新订阅

本工具导入的是配置快照，不代管订阅。带 `proxy-providers` 的配置按它自己的更新机制工作；完整静态节点列表需从 Clash 重新导出。

不要直接覆盖正在运行的 `/etc/mihomo/config.yaml`。先备份，修改新文件时保留：`allow-lan: false`、控制端口 `127.0.0.1:9090`、`external-ui: /var/lib/mihomo/ui`、关闭 TUN，以及服务账号的读取权限。用下面的命令测试通过后才替换并重启：

```bash
sudo -u thinksmart-proxy /usr/local/bin/mihomo -t -d /var/lib/mihomo -f /etc/mihomo/config.yaml.new
```

对不熟悉配置的用户，先用电脑 Clash 管理订阅并提供 HTTP 代理更简单。面板访问使用 GET；`curl -I` 对面板返回 **405 Allow: GET** 不表示面板坏了。

## 地址放在哪里

Muse 使用 `/etc/thinksmart-muse/proxy.env`，只有 root 能读。要换代理地址，可以在仓库目录重新运行安装并指定新的 `--proxy`；账号配对和 Muse 会话会保留。若需要直连，重新运行不带 `--proxy` 的安装。

上游资料：[Mihomo](https://github.com/MetaCubeX/mihomo)、[MetaCubeXD](https://github.com/MetaCubeX/metacubexd)。脚本固定 Mihomo **1.19.33**、面板 **1.274.4**，不下载不可预测的“latest”。
