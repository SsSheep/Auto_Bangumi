# AutoBangumi（自用 Fork）

基于 [AutoBangumi 3.3](https://github.com/EstrellaXD/Auto_Bangumi) 的增强版：自动追番、RSS 订阅、重命名一站式完成。本镜像自带 WebUI，单容器即可部署。

> 完整功能对比与使用说明见 [GitHub README](https://github.com/SsSheep/Auto_Bangumi)

## 快速部署（docker compose，推荐）

```yaml
services:
  AutoBangumi:
    image: shiamiea/auto-bangumi:latest
    container_name: AutoBangumi
    environment:
      - TZ=Asia/Shanghai
      - PUID=1000
      - PGID=1000
      # 可选：修改容器内 WebUI 端口（默认 7892，每次启动都生效）
      # - AB_WEBUI_PORT=7892
    volumes:
      - ./config:/app/config    # 配置文件
      - ./data:/app/data        # 数据库与海报
    ports:
      - "7892:7892"             # 冒号左边可改成宿主机任意端口
    restart: unless-stopped
```

```bash
docker compose up -d
```

## docker run 方式

```bash
docker run -d \
  --name AutoBangumi \
  -p 7892:7892 \
  -v $(pwd)/config:/app/config \
  -v $(pwd)/data:/app/data \
  -e TZ=Asia/Shanghai \
  -e PUID=1000 -e PGID=1000 \
  --restart unless-stopped \
  shiamiea/auto-bangumi:latest
```

## 环境变量

| 变量 | 默认 | 说明 |
|---|---|---|
| `TZ` | `Asia/Shanghai` | 时区 |
| `PUID` / `PGID` | `1000` / `1000` | 容器内进程的 UID/GID，与挂载目录属主匹配 |
| `AB_WEBUI_PORT` | `7892` | WebUI 监听端口，环境变量优先于配置文件，容器健康检查自动跟随 |

## 卷与端口

- `/app/config`：配置文件（config.json），建议挂载持久化
- `/app/data`：数据库、日志、海报缓存
- `7892`：WebUI 与 API（含移动端界面）

## 首次使用

1. 浏览器打开 `http://NAS的IP:7892`，默认账号 `admin` / `adminadmin`（**登录后请立即修改密码**）
2. 设置 → 下载设置：填写 qBittorrent 地址/账号密码，点「测试下载器连接」验证
3. 主页「添加」：粘贴 Mikan 等番剧源的 RSS 链接即可订阅

## 大陆网络环境提示

Mikan（mikanani.me）、TMDB、Bangumi API 在大陆直连不稳定。若你的 NAS 无法直连，在 设置 → 代理 填写局域网内可用的 HTTP/SOCKS5 代理；配好后可在 设置 → 网络设置 里分别测试 TMDB / Bangumi API 连通性。qBittorrent 无需配代理（本应用会把种子文件取回后再交给下载器）。

## 下载器路径提示

设置里的下载地址请填 **qBittorrent 容器内视角**的路径（例如 qB 把 NAS 的 `/vol1/media` 挂载为 `/downloads`，这里就要填 `/downloads/...`），否则添加任务会因保存路径不存在而报错。

## 支持的平台

当前发布 `linux/amd64`。
