# 🛠️ DIY Image Builder

上游开源项目不提供预构建 Docker 镜像？在这里自动构建！

## ✨ 这是什么

一个集中管理的 Docker 镜像自动构建仓库。对于那些官方不提供 Docker image 的开源项目，
通过 GitHub Actions 每日自动检查上游最新 release，发现新版本就自动构建并推送到 GHCR。

## 📦 已构建镜像

| 项目 | 上游仓库 | 镜像地址 | 架构 |
|------|----------|----------|------|
| OpenMAIC | [THU-MAIC/OpenMAIC](https://github.com/THU-MAIC/OpenMAIC) | `ghcr.io/sopyk/openmaic:latest` | amd64 |

## 🚀 使用方法

```bash
# 拉取镜像
docker pull ghcr.io/sopyk/openmaic:latest
```

## ➕ 添加新项目

1. 在 `.github/workflows/` 下新建一个 `build-xxx.yml`
2. 复制 `build-openmaic.yml` 作为模板
3. 修改 `UPSTREAM_REPO` 和镜像名
4. 提交 push 就行

## ⚙️ 工作原理

```
每日定时触发 → 检查上游最新 release
    ↓
发现新版本 → 直接拉取上游源码构建 → 推送到 GHCR
    ↓
已有版本 → 跳过，什么都不做
```

---
*自动构建，省心省力~*
