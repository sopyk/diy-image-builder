# 🛠️ DIY Image Builder

上游开源项目不提供预构建 Docker 镜像？在这里自动构建！

## ✨ 这是什么

一个集中管理的 Docker 镜像自动构建仓库。对于那些官方不提供 Docker image 的开源项目，
通过 GitHub Actions 每日自动检查上游最新 release，发现新版本就自动构建并推送到 GHCR。

## 📦 已构建镜像

| 项目 | 上游仓库 | 镜像地址 | 架构 | 更新方式 |
|------|----------|----------|------|----------|
| OpenMAIC | [THU-MAIC/OpenMAIC](https://github.com/THU-MAIC/OpenMAIC) | `ghcr.io/sopyk/diy-image-builder/openmaic:latest` | amd64 | release tag |
| ArgyBargy | [titusblair/argybargy](https://github.com/titusblair/argybargy) | `ghcr.io/sopyk/diy-image-builder/argybargy:latest` | amd64 | daily main |
| AgentBBS Web | [ruvnet/AgentBBS](https://github.com/ruvnet/AgentBBS) | `ghcr.io/sopyk/diy-image-builder/agentbbs-web:latest` | amd64 | release tag |
| AgentBBS SSH | [ruvnet/AgentBBS](https://github.com/ruvnet/AgentBBS) | `ghcr.io/sopyk/diy-image-builder/agentbbs-ssh:latest` | amd64 | release tag |

## 🚀 使用方法

```bash
# OpenMAIC
docker pull ghcr.io/sopyk/diy-image-builder/openmaic:latest

# ArgyBargy
docker pull ghcr.io/sopyk/diy-image-builder/argybargy:latest

# AgentBBS (Web)
docker pull ghcr.io/sopyk/diy-image-builder/agentbbs-web:latest

# AgentBBS (SSH)
docker pull ghcr.io/sopyk/diy-image-builder/agentbbs-ssh:latest
```

## ➕ 添加新项目

1. 在 `.github/workflows/` 下新建一个 `build-xxx.yml`
2. 复制已有模板（有 release 的用 openmaic 模板，没 release 的用 argybargy 模板）
3. 修改 `UPSTREAM_REPO` 和镜像名
4. 提交 push 就行

## 📋 构建策略

| 策略 | 适用项目 | 触发方式 |
|------|----------|----------|
| **Release 模式** | 有正式 release tag 的项目 | 上游发新版本才构建 |
| **Daily 模式** | 没有 release 的项目 | 每天构建 main 分支最新版 |

## ⚙️ 工作原理

```
每日定时触发 → 检查上游最新 release / commit
    ↓
有新版本 → 直接拉取上游源码构建 → 推送到 GHCR
    ↓
已有版本 → 跳过，什么都不做
```

---
*自动构建，省心省力~*
