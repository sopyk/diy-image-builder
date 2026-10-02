# 🛠️ DIY Image Builder

上游开源项目不提供预构建 Docker 镜像？在这里自动构建！

## ✨ 这是什么

一个集中管理的 Docker 镜像自动构建仓库。对于那些官方不提供 Docker image（或提供的镜像不满足自托管需求）的开源项目，
通过 GitHub Actions 自动检查上游更新，发现新版本就自动构建并推送到 GHCR。

- 全部产物推送到 `ghcr.io/sopyk/diy-image-builder/*`，仅构建 `linux/amd64`
- 仓库 public，镜像可匿名 `docker pull`，无需登录
- 幂等：已有版本/tag 已构建过就跳过，不重复构建；均可在 Actions 手动触发

## 📦 已构建镜像

| 项目 | 上游仓库 | 镜像地址 | 架构 | 检查频率 | 触发条件 |
|------|----------|----------|------|----------|----------|
| AgentMemory | [rohitg00/agentmemory](https://github.com/rohitg00/agentmemory) | `…/agentmemory:<version>` + `:latest` | amd64 | 每日 | 新 release tag |
| OpenMAIC | [THU-MAIC/OpenMAIC](https://github.com/THU-MAIC/OpenMAIC) | `…/openmaic:latest` | amd64 | 每日 | 新 release tag |
| Mem0 API | [mem0ai/mem0](https://github.com/mem0ai/mem0) | `…/mem0-api:latest` + `:sha-<sha>` | amd64 | 每周二 | main 有新 commit |
| Mem0 Dashboard | [mem0ai/mem0](https://github.com/mem0ai/mem0) | `…/mem0-dashboard:latest` + `:sha-<sha>` | amd64 | 每周二 | main 有新 commit |
| ArgyBargy | [titusblair/argybargy](https://github.com/titusblair/argybargy) | `…/argybargy:latest` | amd64 | 每周二 | main 有新 commit |

> `…` 代表 `ghcr.io/sopyk/diy-image-builder`。

## 🚀 使用方法

```bash
# AgentMemory（版本号 tag，跟随上游 release）
docker pull ghcr.io/sopyk/diy-image-builder/agentmemory:latest
docker pull ghcr.io/sopyk/diy-image-builder/agentmemory:v0.9.29

# OpenMAIC
docker pull ghcr.io/sopyk/diy-image-builder/openmaic:latest

# Mem0（API + Dashboard 两个镜像）
docker pull ghcr.io/sopyk/diy-image-builder/mem0-api:latest
docker pull ghcr.io/sopyk/diy-image-builder/mem0-dashboard:latest

# ArgyBargy
docker pull ghcr.io/sopyk/diy-image-builder/argybargy:latest
```

## 📅 更新时间表

| 项目 | 检查时间（北京时间） | 触发条件 |
|------|----------------------|----------|
| AgentMemory | 每天 09:17 | 上游有新 release tag（GHCR 已有该 tag 则跳过） |
| OpenMAIC | 每天 08:00 | 上游有新 release tag |
| Mem0（API + Dashboard） | 每周二 09:00 | main 分支有新 commit，打 `latest` + `sha-*` |
| ArgyBargy | 每周二 09:00 | main 分支有新 commit |

> GitHub Actions 的 schedule 不保证准点，实际可能延迟数分钟到数十分钟。所有 workflow 均支持 Actions 页面手动触发。

## 🧩 各项目构建方式

- **AgentMemory** — 做法甲：仓库里**不维护 Dockerfile 副本**，构建时 checkout 官方 release tag，直接用上游自带的
  [`deploy/coolify/Dockerfile`](https://github.com/rohitg00/agentmemory/tree/main/deploy/coolify)
  （iii 引擎 + `@agentmemory/agentmemory` 同次构建合体），每个 tag 的 iii 引擎与应用版本由官方绑死，跟随 tag 即可。
- **Mem0** — 做法乙：官方镜像/构建不满足自托管需求，在本仓库
  [`dockerfiles/`](./dockerfiles) 维护自定义 Dockerfile 与启动补丁，checkout 上游 main 后套用。
- **OpenMAIC / ArgyBargy** — checkout 上游源码后用各自方式构建。

## ➕ 添加新项目

1. 在 `.github/workflows/` 下新建一个 `build-xxx.yml`
2. 参考已有模板：
   - 有正式 release tag、且能用官方 Dockerfile 的 → 参考 `build-agentmemory.yml`（钉 tag、不存副本）
   - 有 release 但需要自定义构建的 → 参考 `build-openmaic.yml`
   - 无 release、跟 main 分支的 → 参考 `build-argybargy.yml` / `build-mem0.yml`
3. 修改 `UPSTREAM_REPO`、镜像名与检查频率
4. 提交 push 就行（首次可能需要在 Actions 手动触发一次验证）

## 📋 构建策略

| 策略 | 适用项目 | 触发方式 |
|------|----------|----------|
| **Release 模式** | 有正式 release tag 的项目 | 上游发新版本才构建，打版本号 tag + `latest` |
| **Commit/Weekly 模式** | 没有 release、更新不频繁的项目 | 每周检查 main 分支，有新 commit 就构建，打 `latest` + `sha-*` |

## ⚙️ 工作原理

```
定时 / 手动触发 → 检查上游最新 release tag 或 main commit
    ↓
GHCR 中不存在该版本 → 拉取上游源码（套用自定义 Dockerfile）→ 构建 → 推送 GHCR
    ↓
该版本已构建过      → 跳过，什么都不做
```

---
*自动构建，省心省力~*
