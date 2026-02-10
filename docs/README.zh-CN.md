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
