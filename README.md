# 🛠️ DIY Image Builder

上游开源项目不提供预构建 Docker 镜像？在这里自动构建！

## ✨ 这是什么

一个集中管理的 Docker 镜像自动构建仓库。对于那些官方不提供 Docker image 的开源项目，
通过 GitHub Actions 自动检查上游更新，发现新版本就自动构建并推送到 GHCR。

## 📦 已构建镜像

| 项目 | 上游仓库 | 镜像地址 | 架构 | 检查频率 |
|------|----------|----------|------|----------|
| OpenMAIC | [THU-MAIC/OpenMAIC](https://github.com/THU-MAIC/OpenMAIC) | `ghcr.io/sopyk/diy-image-builder/openmaic:latest` | amd64 | 每日 release |
| ArgyBargy | [titusblair/argybargy](https://github.com/titusblair/argybargy) | `ghcr.io/sopyk/diy-image-builder/argybargy:latest` | amd64 | 每周二 main |

## 🚀 使用方法

```bash
# OpenMAIC
docker pull ghcr.io/sopyk/diy-image-builder/openmaic:latest

# ArgyBargy
docker pull ghcr.io/sopyk/diy-image-builder/argybargy:latest
```

## 📅 更新时间表

| 项目 | 检查时间 | 触发条件 |
|------|----------|----------|
| OpenMAIC | 每天 UTC 0 点（北京时间 8 点） | 上游有新 release tag |
| ArgyBargy | 每周二 UTC 1 点（北京时间 9 点） | main 分支有新 commit |

## ➕ 添加新项目

1. 在 `.github/workflows/` 下新建一个 `build-xxx.yml`
2. 参考已有模板（有 release 用 openmaic 模板，没 release 用 argybargy 模板）
3. 修改 `UPSTREAM_REPO` 和镜像名
4. 提交 push 就行

## 📋 构建策略

| 策略 | 适用项目 | 触发方式 |
|------|----------|----------|
| **Release 模式** | 有正式 release tag 的项目 | 上游发新版本才构建 |
| **Daily 模式** | 没有 release、更新频繁的项目 | 每天检查 main 分支，有变化就构建 |
| **Weekly 模式** | 没有 release、更新不频繁的项目 | 每周检查 main 分支，有变化就构建 |

## ⚙️ 工作原理

```
定时触发 → 检查上游最新 release / commit
    ↓
有新版本 → 拉取上游源码构建 → 推送到 GHCR
    ↓
已有版本 → 跳过，什么都不做
```

---
*自动构建，省心省力~*
