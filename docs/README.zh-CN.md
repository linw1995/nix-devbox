# nix-devbox 文档

**简体中文** | [English](README.md)

## 目录

- [configuration.zh-CN.md](./configuration.zh-CN.md) - `devbox.yaml` 配置参考

## 快速开始

```bash
# 进入示例目录
cd examples/base

# 构建镜像
nix-devbox build .

# 运行容器
nix-devbox run .
```

## 配置位置

在项目根目录或任一 flake 目录中放置 `devbox.yaml`：

```
project/
├── flake.nix
└── devbox.yaml
```

多项目合并时，配置按加载顺序自动合并。

## Flake 引用

nix-devbox 支持多种 flake URL 格式：

### 本地路径

```bash
# 绝对或相对路径（自动转换为 path: 格式）
nix-devbox build /path/to/project
nix-devbox build ./my-project
nix-devbox build ../projects/app
```

### 远程 URL

```bash
# GitHub 仓库
github:owner/repo
github:owner/repo/main
github:owner/repo/v1.0.0
github:owner/repo?dir=subdir

# GitLab
gitlab:owner/repo
gitlab:owner/repo/branch

# HTTPS Git
git+https://github.com/owner/repo
git+https://github.com/owner/repo?ref=main

# HTTP/HTTPS 压缩包
https://example.com/flake.tar.gz

# 其他支持的协议
sourcehut:~owner/repo
hg+https://example.com/repo
```

### 子目录支持

对于位于仓库子目录中的 flake：

```bash
nix-devbox build "github:owner/repo?dir=dev"
```

`dir` 参数指定包含 `flake.nix` 的子目录。

### Shell 选择

追加 `#shellname` 选择特定的 devShell：

```bash
# 本地路径指定 shell
nix-devbox build ./project#nodejs

# 远程 URL 指定 shell
nix-devbox build "github:NixOS/nixpkgs#hello"

# 完整属性路径
nix-devbox build ./project#devShells.x86_64-linux.custom
```

### 远程 devbox.yaml

使用远程 URL 时，nix-devbox 会自动获取 flake 并读取其中的 `devbox.yaml` 配置。此功能与配置合并特性透明协作。
