---
title: 原生代码理解的实现与真实验收
description: 记录原生 Python 仓库引擎、接口、真实模型与数据库验证，以及性能和发布边界。
---

# 原生代码理解的实现与真实验收

日期：2026-09-21。设计见[原生 Git 仓库代码理解](0000-native-git-code-understanding.md)，使用方式见[仓库代码工作流](../docs/workflows/repository-code.md)。

当前实现能够完成本地 Python 仓库的索引、定位、关系查询、源码读取、修改后同步和影响复核。已取得 SQLite、OceanBase、HTTP/MCP、真实模型、embedding 和 Codex Hook 的通过证据；历史与代码组合场景也已通过，保留了一次模型参数错误及其定向复测记录。能力保持实验性质，默认关闭；10 文件同步仍超过性能目标，静态图和回答质量仍需要独立人工审计。

## 交付范围

| 能力 | 实现与行为 |
| --- | --- |
| 代码理解 | Tree-sitter Python 提取定义、引用与导入；保守解析别名、相对导入、re-export 和词法作用域，区分静态关系、候选与未知 |
| 检索与证据 | `map`、`symbols`、`explore`、`callers`、`callees`、`impact`、`affected_tests`、`read`；返回文件摘要、行范围、片段摘要和关系依据 |
| 仓库更新 | 内容摘要识别变更；复用未变化文件的语法事实并重新解析全图；`changes`、`impact_changes` 保留删除前证据 |
| 一致性 | 查询前后核对工作区；过期返回 `code_changed`；不可比较的分支/代次返回 `baseline_unavailable`；构建失败保留已发布代次 |
| 接口 | 本机 CLI、Runtime、Python Client、HTTP `query_code` 和 PowerContext MCP `query_code`；构建与同步由本机运维执行 |
| 上下文 | `include_code=false` 默认；启用后执行一次 `explore`，在共享预算中加入最多 4 条临时代码证据，保留已有历史类别选择 |
| 宿主 | Codex、Claude Code Hook 可显式启用；Codex Scope 绑定包含新工具 |
| 运维 | 分阶段 tracing、聚合计数与 RSS 诊断；本机 `clear` 保留活跃读者及其他 Scope；路径边界只返回省略边数 |

生产代码位于 `src/powercontext/builtin/code/`，上下文组装位于 `src/powercontext/builtin/runtime/prepared_code.py`。生产索引无需 CodeGraph、Node.js、生成模型或 embedding。CodeGraph 的 Node 适配器只存在于 `evaluation/native_code/`，用于真实引擎对照。

本机引擎在 Linux 验证，使用 POSIX 文件锁、进程资源限制与 SQLite FTS5。结构分析首期支持 UTF-8 Python。动态分派、反射和框架隐含关系可能缺失；候选测试不能代替项目要求的测试集合。

## 表结构与数据边界

现有业务数据库新增 **0 张表**。每个代码缓存包含 3 张逻辑表：

| 表 | 用途 |
| --- | --- |
| `code_nodes` | 文件和符号 |
| `code_edges` | 带解析依据的关系 |
| `code_search_fts` | 名称、路径、签名与文档字符串的全文检索 |

SQLite FTS5 还会维护 5 张内部 shadow 表；它们不构成额外业务实体。文件清单、原始提取事实、诊断和源码放在随代次发布的缓存文件中。对真实验收生成的两个代码库和一个 SQLite 业务库进行审计，确认逻辑缓存表为 3 张，业务库没有 `code_*` 表。

仓库绑定由服务运维者配置，HTTP 请求不接受任意服务器目录。缓存位于仓库之外，按 Scope 和绑定隔离。测试覆盖了未授权 Scope、权限撤销、符号链接、凭据文件、Git clean filter、同大小同 mtime 修改、损坏缓存和 FIFO 文件。

## 真实服务验收

最终交付源码使用 `.env` 中的真实生成模型、embedding 和隔离数据库完成验收。纯代码场景 **2 项通过，163.94 秒**。历史与代码组合首批为 **1 通过、1 失败，119.29 秒**：OceanBase 通过；SQLite 的 HTTP 组合上下文已经通过，但模型在后续 MCP 参数中漏写了 Scope ID 的一个字符，验收在调用前拦截该错误，尚未执行 Hook。保留这次失败后，以相同配置单独复测 SQLite，结果为 **1 项通过，62.86 秒**。没有修改产品代码或放宽参数断言，也不将两批表述为一次全部通过的运行。

| 最终场景 | SQLite | OceanBase |
| --- | --- | --- |
| 纯代码 HTTP、真实模型 MCP、已安装 Codex Hook | 通过；Hook 2.342 秒 | 通过；Hook 4.581 秒 |
| 历史与代码 HTTP 组合、真实模型 MCP、已安装 Codex Hook | 定向复测通过；Hook 2.598 秒 | 首批通过；Hook 1.351 秒 |

组合场景实际执行：

1. 使用配置的 embedding 服务写入历史 Memory，再通过 HTTP 取得同时包含历史与代码的上下文。
2. 通过 MCP 让真实生成模型找到临时仓库中随机生成的标识，并给出正确源码位置，验证工具返回影响了回答。
3. 使用插件声明的 `uv run --frozen --quiet --project … python hooks/recall.py` 运行已安装 Codex Hook；请求超时 6 秒、HTTP 总预算 8 秒、进程截止 10 秒，确认只交付一次代码区块。
4. Hook 使用纯代码 assembly；历史保留由前面的 HTTP 组合检查验证。模型消费历史约束的独立验证见下面的 B0/B1 实验。
5. 停止服务；OceanBase 临时数据库删除后，再查询系统目录确认不存在。

Hook 运行环境安装准备单独计时，没有混入表中的 Hook 时延；四个通过场景的准备耗时为 0.052～0.239 秒。本机使用已缓存的依赖，这不是冷网络安装耗时。

验收期间，embedding 曾返回 HTTP 400、`model_price_error`，导致一次组合复测受阻；失败与清理记录保留在 `live-acceptance-delivery/`。北京时间 2026-09-21 23:30 使用固定测试文本复核时，当前配置已成功返回 1,024 维向量，随后上述组合场景通过。没有修改 `.env`，也没有切换模型。探针记录为 `embedding-delivery-probe.json`。

当前交付的纯代码证据位于 `live-code-only-tight/`，组合证据位于 `live-combined-tight/` 与 `live-combined-sqlite-retry/`；首次模型参数错误及所有通过记录均保留。五次场景的测试服务均已停止，两次临时 OceanBase 库均已删除并核验，测试未向共享业务库写入验收数据。

Claude Code Hook 使用自动化回归覆盖。此处宿主实测是已安装 Codex Hook 子进程；模型工具调用使用独立验收 Agent，未执行完整 Codex 宿主自主修复验收。当前未配置独立 seekdb 实例，本次没有 seekdb 的真实服务结果。

真实服务证据根目录为 `/data/codex-tmp/native-code-20260921/`，各场景的 `native-code-acceptance.json` 包含结果和清理记录。

## 自动上下文独立实验

一个三文件工作流固定相同模型、历史约束、原生引擎及 4,000 字节预算，B0 按需查询、B1 自动注入，每组重复 3 次。

| 观测 | B0 | B1 |
| --- | --- | --- |
| 正确答案 | 3/3 | 3/3 |
| 保留随机历史约束 | 3/3 | 3/3 |
| 后续工具调用 | 10、10、8 | 9、9、7 |
| 注入字节数 | 748 | 2,459 |
| 平均任务耗时 | 39.69 秒 | 39.48 秒 |

在这个工作流中，自动注入平均减少一次后续查询，耗时接近。样本只有一个工作流，不能据此得出普遍收益或建议默认开启。结果保存在 `context-experiment/` 下的 `context-experiment.json`，与引擎 A/B/C 成绩分开统计。

## 正确性与回归证据

| 检查 | 结果与边界 |
| --- | --- |
| 原生引擎、PreparedContext、API/MCP、两种 Hook 的集中回归 | 201 项通过；增量/全量等价、构建失败保留代次、缓存 FIFO 和合并结果截断用例也通过 |
| 交付补充回归 | 隔离交付源码的原生引擎、PreparedContext、API/MCP 共 151 项通过；实际 OpenTelemetry 错误导出与隐私用例另有 1 项通过；循环/菱形/嵌套测试与真实 Git worktree 隔离另有 2 项通过 |
| API 合约 | `make contract-test`：48 项通过；OpenAPI 与 Python、JavaScript 生成结果一致 |
| 现有跨组件回归 | 83 项通过、3 跳过；包含新工具的 MCP 传输清单另经定向复测通过 |
| 最后一轮非真实服务全量回归 | 2,706 通过、53 跳过、4 失败；失败为 3 项系统 Node 版本不支持类型转换参数，以及 1 项进程启动的 10 秒等待超时 |
| 上述失败复测 | 显式使用 Node 22，复测启动场景及整个集成指引评测模块：54 通过、1 跳过；产品代码未因此改动 |
| Python 兼容性 | Python 3.11、3.12、3.13 独立环境各 84 通过、1 跳过；主回归使用 3.14.6 |
| 安装包 | 隔离源码快照构建 sdist 与 wheel，15 个原生模块与工作区逐字节一致；Python 3.11 安装后的 CLI index/status/query/sync/clear 通过；仅安装 `powercontext[code]` 的独立环境可完成索引、查询和清理 |
| 文档 | `make docs-test` 完成静态构建与内部链接检查 |
| 类型与风格 | 本次代码的 Ruff、类型检查通过；`make check` 的其他钩子通过，整仓类型检查仍有基线也能复现的 4 项 `scripts.*` 导入诊断 |

各批次存在重叠，不相加作为总通过数。全量运行覆盖主要实现；交付的清理、tracing 和路径边界计数由补充回归覆盖，精确路径与 glob 排除优化另有 1 项公开行为回归通过。全量日志和定向复测日志均保留，不能将定向通过表述为一次完全无失败的全量运行。用户原有未跟踪文件 `tests/test_sdist.py` 未纳入本次全量命令。

SQLite 能力故障验收另有 1 项通过：使用真实 SQLite authorizer 拒绝创建 FTS5 虚表，确认构建和查询返回 503，状态为缺少索引且 `last_build` 保留存储失败原因。该测试模拟 FTS 不可用的存储边界，没有替换实际 SQLite 引擎。

小型源码标注静态图包含 11 条预定义调用关系，以及同名、局部遮蔽、动态接收者等负例。实测静态关系 precision/recall 和候选测试 recall@20 均为 1.0。标注来自源码定义，独立人工复核尚未完成；这些数字只描述该小型 fixture。

评测引用解析回归另有 **9 项通过**，覆盖 Markdown、`L` 和 `lines` 格式、多段行范围及无效范围的拒绝。运行后修正评价器的原因和证据身份见 A/B/C 报告。

最终交付源码的原生引擎全文件回归 **37 项通过**，包括构建事务结束即关闭 SQLite 连接的资源回归。性能数据来自相同 1,536 文件语料上的该交付构建，原始记录为 `performance-final/results.json`。不同负载时段曾测得 40.73 秒冷索引、17.68 秒同步；这些差异不归因于连接关闭修复。

## 性能与发布判断

性能数据来自固定的 1,536 文件 PowerContext 捕获快照，Linux、16 个可见 CPU、Python 3.14.6。完整查询包含工作区新鲜度核对；采样期间机器还有其他工作负载，因此是本机观测值。

| 指标 | 实测 | RFC 初始目标 |
| --- | --- | --- |
| 冷索引 | 39.42 秒 | ≤60 秒 |
| 10 文件同步 | **22.74 秒**，提取 10 文件、复用 1,526 文件事实 | ≤5 秒，未达到 |
| 查询 p50 / p95 | 0.92 / 1.83 秒 | p95 ≤2 秒 |
| 缓存文件逻辑字节总量 | 411,280,913 字节 | 单绑定受配置上限约束 |
| 父进程 / 最大子进程 max RSS | 343,992 / 343,992 KiB | 分别报告，不能相加当作进程树同时峰值 |

交付构建在相同捕获源码上复测；另一负载时段曾测得 34.39 秒同步，两次均未达到 5 秒目标。同步分析显示，全图关系解析和不可变代次文件写入占主要成本。当前实现满足显式使用的功能闭环，尚不适合把 5 秒同步目标作为服务承诺。自动注入保持默认关闭。

相对 CodeGraph 和普通文件工具的任务质量、效率见 [A/B/C 实测报告](0000-native-git-code-understanding-experiment.md)。真实服务连通、小型静态 fixture 和单工作流 B0/B1 均不能替代引擎对照或独立人工审计。

## 复现验收

在安装了项目开发依赖和 `code` 可选依赖的源码环境中运行。真实服务测试会调用环境文件中的模型；配置数据库使用独立临时库，并在结束时删除和确认。为 `--basetemp` 指定新的证据目录，pytest 会清空该目录。

```bash
TMPDIR=/data/codex-tmp .venv/bin/python -m pytest tests/builtin/test_native_code.py
make contract-test
TMPDIR=/data/codex-tmp .venv/bin/python -m pytest \
  tests/e2e/real_experience_skill/test_native_code.py \
  -k test_native_code_only_with_real_services --run-real-e2e \
  --real-e2e-env-file .env --basetemp /absolute/evidence/new-code-only-run
```

将选择器改为 `-k test_native_code_with_real_services` 可重放历史与代码组合场景；该场景需要可用的 embedding。`-k test_native_code_automatic_context_controlled_experiment` 运行独立 B0/B1 实验。每次使用不同证据目录。引擎 A/B/C 的准备、执行、评阅和统计命令见 `evaluation/native_code/README.md`。

## 证据保留

本机证据根目录为 `/data/codex-tmp/native-code-20260921/`，包含合约与回归日志、真实服务报告、表结构审计、安装包验收、静态图结果及性能数据。验证包使用 `0.0.0` 测试版本，未提交、推送或发布。

安装包从只包含仓库源码和本次文件的隔离快照构建；用户已有的演示文稿、报告及网站构建产物未纳入最终源码包。测试临时 SQLite 与图缓存作为本机证据保留；外部 OceanBase 临时库已删除，真实验收服务已停止。
