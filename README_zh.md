# yfinance-mcp

> **⚠️ 服务条款灰区 — 详见 [docs/SECURITY.md](docs/SECURITY.md)**
>
> 本服务器使用 [`yfinance`](https://github.com/ranaroussi/yfinance)，它
> **抓取的是 Yahoo Finance 的未公开接口**。Yahoo 服务条款禁止数据再分发，
> 也未授权自动抓取。**仅限个人、低频、研究用途** —— 不可用于商业用途或批量
> 再分发。数据为**延迟（约 15 分钟）且尽力而为**，绝非实时或权威数据。风险
> 自担。
>
> **🔒 只读** —— 无下单 / 交易 / 写入接口。yfinance 是数据抓取库，无法下单。

[![test](https://github.com/kevinkda/yfinance-mcp/actions/workflows/test.yml/badge.svg)](https://github.com/kevinkda/yfinance-mcp/actions/workflows/test.yml)
[![CodeQL](https://github.com/kevinkda/yfinance-mcp/actions/workflows/codeql.yml/badge.svg)](https://github.com/kevinkda/yfinance-mcp/actions/workflows/codeql.yml)

[English](README.md)

`yfinance-mcp` 是一个 MCP（Model Context Protocol）服务器，向任意兼容 MCP 的
LLM 客户端（Claude Desktop、Cursor 等）暴露一小组**只读**的 Yahoo Finance
数据点。它刻意作为以下姊妹只读服务器的**补充** ——
[`schwab-marketdata-mcp`](https://github.com/kevinkda/schwab-marketdata-mcp)、
[`polygon-news-mcp`](https://github.com/kevinkda/polygon-news-mcp)、
[`sec-edgar-mcp`](https://github.com/kevinkda/sec-edgar-mcp) —— 填补它们未覆盖
的空白（拆股、简单的财报日历、利润表、分析师评级）。凡是上述持牌服务器已覆盖的
数据，应优先使用它们。

## 工具（6 个）

### 数据工具（4 个）

| 工具 | 说明 |
| ---- | ---- |
| `get_splits` | 历史拆股事件（日期 → 拆股比例）。 |
| `get_earnings_calendar` | 未来 / 过去的财报日期，含 EPS 预期 / 实际 / 超预期%。 |
| `get_financial_statements` | 利润表科目（`period="annual"` 或 `"quarterly"`），宽表 + 长表两种形式。 |
| `get_analyst_recommendations` | 分析师评级汇总 + 可选的升降级历史。 |

### 元工具（2 个）

| 工具 | 说明 |
| ---- | ---- |
| `health_check` | 就绪探针 —— 确认 yfinance 可导入，**不**联网访问 Yahoo。 |
| `get_server_info` | 服务器元信息 —— 版本、平台、`is_read_only: true`、`data_is_realtime: false`、ToS 提示、工具列表。 |

## 安装

```bash
git clone https://github.com/kevinkda/yfinance-mcp.git
cd yfinance-mcp
uv sync --extra dev
```

需要 Python ≥ 3.11。**无需 API key、无需 OAuth、无需任何凭证** —— yfinance 抓取
的是 Yahoo 公开接口。

## 配置（可选）

无任何**必须**配置项。若想调节缓存或超时，复制示例环境文件：

```bash
cp .env.example .env
# 编辑 .env 设置 YFINANCE_CACHE_ENABLED、YFINANCE_TIMEOUT_SECONDS 等。
```

## 运行

```bash
uv run yfinance-mcp            # MCP stdio 传输
# 或
uv run python -m yfinance_mcp  # 等价写法
```

按常规 MCP 的 `command` + `args` 形式接入 Claude Desktop / Cursor。

## 缓存

抓取到的数据帧（拆股 / 财报 / 财务 / 评级）会作为历史快照持久化到本地 DuckDB
`~/.local/state/yfinance-mcp/cache.duckdb`，让 LLM agent 可以做"与上次相比有何
变化"的查询，而**无需再次抓取 Yahoo**（既慢又涉及 ToS 风险）。缓存是尽力而为的：
任何 DuckDB 错误都会被记录，工具回退到实时抓取。缓存为**选择性启用（默认禁用）**——
通过 `YFINANCE_CACHE_ENABLED=true`（也接受 `1` / `yes` / `on`）开启。

## 安全与服务条款

- **ToS 灰区：** 见 [docs/SECURITY.md](docs/SECURITY.md) —— 本仓库最重要的文档。
  部署前务必阅读。
- **威胁模型：** 见 [docs/THREAT_MODEL.md](docs/THREAT_MODEL.md)。
- **只读：** 无下单 / 交易 / 写入接口；客户端方法 allow-list 见
  `src/yfinance_mcp/client.py`。
- **无凭证落盘：** 没有任何可泄露的密钥。

## 许可证

MIT —— 见 [LICENSE](LICENSE)。MIT 许可证仅覆盖*本代码*，**不**授予对 Yahoo 数据的
任何权利。详见 [docs/SECURITY.md](docs/SECURITY.md)。
