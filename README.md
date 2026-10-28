# GitHub Releases 监控 & 飞书推送

用于监控 GitHub 仓库的 Releases 更新，并通过飞书 Webhook 推送富文本卡片通知。  
专为群晖 NAS 的 `docker-compose` 部署设计。

## 功能特性

- 监控一个或多个 GitHub 仓库的 Releases
- 首次启动自动推送 `✉️ 开始监控` 富文本卡片
- 检测到新版本推送 `📢 Release 更新通知` 富文本卡片，包含仓库名称、Tag、发布时间及更新日志
- 支持 alpha / beta / rc / 正式版，按发布时间取最新版本（自动排除 draft）
- 飞书 Webhook 签名校验（HMAC-SHA256）
- 检查间隔默认 10 分钟，可按需调整
- 状态持久化到 `data/state.json`，容器重启不丢失监控进度

## 项目结构

```
github-release-monitor/
├── docker-compose.yml
├── .env.example         # 凭据模板，复制为 .env 后填写
├── .gitignore           # 忽略 .env / data/ / 编译缓存
├── app/
│   ├── Dockerfile
│   ├── main.py
│   └── requirements.txt
└── data/                # 运行时自动生成，持久化状态文件
```

## 群晖 NAS 部署步骤

### 1. 上传项目

将整个 `github-release-monitor` 文件夹上传到群晖，例如：

```
/volume1/docker/github-release-monitor/
```

### 2. 配置凭据

凭据统一放在 `.env`，仓库里只保留模板文件：

```bash
cp .env.example .env
```

```ini
GITHUB_REPOS=deepseek-ai/deepseek-harness
CHECK_INTERVAL=600
FEISHU_WEBHOOK=https://open.feishu.cn/open-apis/bot/v2/hook/xxxx
FEISHU_SECRET=your-secret-here
GITHUB_TOKEN=
```

- `GITHUB_REPOS`：要监控的仓库，逗号分隔，格式 `owner/repo`
- `CHECK_INTERVAL`：检查间隔秒数，默认 `600`（10 分钟）
- `FEISHU_WEBHOOK`：飞书自定义机器人的 Webhook 地址
- `FEISHU_SECRET`：飞书签名密钥（在飞书机器人安全设置中开启签名校验后获取）
- `GITHUB_TOKEN`：可选，Personal Access Token，用于提高 GitHub API 限额（未认证仅 60 次/小时）

`docker-compose.yml` 只引用变量（如 `${FEISHU_SECRET:-}`），本身不含任何真实凭据，可安全提交到版本库。`.env` 已被 `.gitignore` 忽略，请勿提交。

### 3. 启动容器

通过 SSH 登录群晖后执行：

```bash
cd /volume1/docker/github-release-monitor
docker-compose up -d --build
```

或在群晖 Docker → 项目 → 新增中指向该文件夹。

### 4. 查看日志

```bash
docker-compose logs -f github-release-monitor
```

看到类似 `[INFO] 飞书卡片推送成功: ✉️ 开始监控` 即表示首次推送成功。

### 5. 更新配置后重启

```bash
docker-compose up -d --build
```

## 飞书签名校验

飞书自定义机器人安全设置中开启「签名校验」后，将密钥填入 `FEISHU_SECRET`。  
程序会自动计算 `timestamp + secret` 的 HMAC-SHA256 签名，并在请求中携带。

## 环境变量说明

| 变量 | 必填 | 说明 | 默认值 |
| --- | --- | --- | --- |
| `GITHUB_REPOS` | 是 | 监控仓库列表，逗号分隔，格式 `owner/repo` | 空 |
| `CHECK_INTERVAL` | 否 | 检查间隔（秒） | `600` |
| `FEISHU_WEBHOOK` | 是 | 飞书自定义机器人 Webhook URL | 空 |
| `FEISHU_SECRET` | 否 | 飞书签名密钥（建议填写） | 空 |
| `GITHUB_TOKEN` | 否 | GitHub Personal Access Token，提高 API 限额 | 空 |

## DaoCloud 镜像源

`app/Dockerfile` 已使用 DaoCloud 镜像加速：

```dockerfile
FROM daocloud.io/library/python:3.11-slim
```

如果你的群晖 Docker 已全局配置 DaoCloud 加速，也可改为官方镜像：

```dockerfile
FROM python:3.11-slim
```

## 常见问题

**Q: 群晖是 ARM 架构（如 DS920+），镜像拉取失败？**  
A: DaoCloud 镜像通常支持多架构。如遇问题，可尝试将 Dockerfile 基础镜像改为 `python:3.11-slim`，并在群晖 Docker → 设置 → 镜像加速中配置 DaoCloud 加速器。

**Q: 如何增加更多监控仓库？**  
A: 在 `GITHUB_REPOS` 中逗号分隔即可，例如：  
`GITHUB_REPOS: "deepseek-ai/deepseek-harness,nginx/nginx,kubernetes/kubernetes"`

**Q: 如何修改检查频率？**  
A: 修改 `CHECK_INTERVAL` 值，单位为秒。例如 `300` 表示 5 分钟，`1800` 表示 30 分钟。

## License

MIT
