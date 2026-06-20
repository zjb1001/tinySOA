# third_party

本目录存放以 git submodule 形式引入的第三方依赖。

## pysomeip

- 上游：<https://github.com/afflux/pysomeip>
- 引入路径：`third_party/pysomeip/`
- 提供的 Python 包：`someip`（源码位于 `third_party/pysomeip/src/someip/`）
- 用途：SOME/IP 协议栈（报文构造/解析、Service Discovery、socket 逻辑），由
  `src/tinysoa/eventbus/someip.py` 用于实现 SOME/IP 事件总线。
- 自身依赖：无（仅 Python 标准库 + asyncio）。

### 初始化 / 更新

```bash
# 首次拉取源码
git submodule update --init --recursive

# 升级到上游最新
cd third_party/pysomeip
git checkout main && git pull
cd ../..
git add third_party/pysomeip
```

### 让 `someip` 可被导入

- **pytest**：仓库根目录的 `conftest.py` 已自动注入 `third_party/pysomeip/src`，无需额外配置。
- **直接 `python` 运行**：

```bash
PYTHONPATH=src:third_party/pysomeip/src python your_script.py
```
