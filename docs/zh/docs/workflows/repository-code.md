---
title: 理解当前 Git 仓库
description: 为多语言 Git 工作区建立本地代码索引，定位定义、分析关系，并在修改后同步和核对证据。
---

# 理解当前 Git 仓库

Memory 保存历史决策与约束；代码查询提供当前工作区的定义、关系和源码证据。
两者组合时，Agent 可以同时回答“此前为什么这样设计”和“现在代码实际如何实现”。
代码索引是可重建的本机缓存，不会把每个函数创建为 Memory、Source 或 Artifact，也不新增业务数据库表。

本能力默认关闭。结构分析支持 UTF-8 Python、TypeScript/JavaScript（含 TSX/JSX）和 Go，使用 Tree-sitter 提取语法，再保守地解析仓库内引用。
它不需要生成模型、Embedding、Node.js 或 CodeGraph 服务。动态分派、反射、框架隐含调用及不支持的语法可能缺失；
`candidate` 关系只表示线索，不能当作运行时调用证明。
本机索引目前在 Linux 验证，依赖 POSIX 文件锁、进程资源限制和 SQLite FTS5；其他系统可通过 HTTP 使用该服务。
macOS 和 Windows 的本机索引尚未验收。

## 多语言范围

同一个 Scope 可以绑定包含 Python、TypeScript/JavaScript 和 Go 的混合仓库，无需逐语言创建索引。
语言由文件扩展名识别；`.jsx` 使用 JavaScript grammar，`.tsx` 使用独立的 TSX grammar。

| 语言 | 文件 | 结构和静态关系 |
| --- | --- | --- |
| Python | `.py`、`.pyi` | 类、函数、方法、词法作用域、显式导入及别名、相对导入和静态重导出 |
| JavaScript / TypeScript | `.js`、`.jsx`、`.mjs`、`.cjs`、`.ts`、`.tsx`、`.mts`、`.cts` | 函数、箭头函数、类和方法；TS 接口、类型及枚举；相对 ESM 导入、具名/默认导出、别名和具名重导出 |
| Go | `.go`，模块身份取自 `go.mod` | 函数、方法、结构体、接口及类型；同包跨文件调用、当前模块内的显式包导入及别名 |

所有语言共用源码摘要、索引代次、查询预算和 `prepare_context`。查询证据包含 `language`，
`coverage.languages` 分别统计各语言文件的 `ok`、`partial`、`failed` 数量；文件被发现不等于结构解析成功。
JS/TS 的 `.test`、`.spec`、`__tests__` 和 Go 的 `_test.go` 参与测试候选发现，名称匹配始终标为 `candidate`。

JS/TS 不解析 CommonJS 模块关系、包导出映射、tsconfig 路径别名、通配重导出、继承分派或类型推断；
Go 不执行工具链，不解析 workspace/replace 依赖、接口分派或方法接收者类型。
Go 条件编译文件仍可检索，其相关关系降为候选，不按当前机器选择构建目标。
动态接收者、参数遮蔽及无法唯一绑定的名称不会被当作确定调用；候选或未解析原因保留在索引诊断中。
混合语言检索不推断 Python、JS/TS 和 Go 之间的 HTTP、RPC 或 FFI 调用。
其他受支持文本文件保留文件导航和源码读取能力。

## 配置并构建

在源码安装中执行 `uv sync --extra code`；部署包需要安装 `powercontext[server,cli,code]`。
先创建一个已有访问控制约束的 Scope，再由服务运维者配置该 Scope 对应的本地 Git 根目录。
同一仓库的不同 worktree 使用不同 Scope 绑定。HTTP 客户端不能提交任意服务器目录。

在 Server 环境文件中设置以下 JSON，将示例 Scope 和绝对路径替换为实际值：

```dotenv
POWERCONTEXT_SERVER_CODE='{"enabled":true,"cache_dir":"/srv/powercontext/code-cache","repositories":{"scp_demo":{"root":"/srv/git/project","source_roots":["src","."]}}}'
```

缓存必须位于仓库之外。默认只读取 Git 跟踪文件，并按文件名排除常见凭据文件，同时排除符号链接、二进制和构建产物。
需要分析未跟踪文件时，在该绑定中设置 `"include_untracked": true`；Git ignore 规则仍然生效。
`exclude` 接受仓库相对路径 glob；`source_roots` 只影响 Python 导入解析，不扩大目录访问范围。

```bash
powercontext code index --scope scp_demo --env-file /srv/powercontext/server.env
powercontext code status --scope scp_demo --env-file /srv/powercontext/server.env
```

`index` 全量重建；`sync` 复用未变化文件的解析事实，再重新解析全图引用。
构建成功后原子切换索引代次，查询期间仍可继续构建。解析失败或被省略的文件通过 coverage 和诊断显式呈现。

## 查询与引用

把请求保存为 `code-query.json`：

```json
{"operation":{"kind":"explore","query":"prepare_context"},"max_bytes":16000}
```

```bash
powercontext code query --scope scp_demo --request-file code-query.json --env-file /srv/powercontext/server.env
```

相同请求可以发送到 `POST /v1/scopes/{scope_id}/code/query`，或通过 Python Client 的 `query_code`、
Runtime 的 `code.for_scope(scope_id).query(...)`、PowerContext MCP 的 `query_code` 调用。
MCP 参数中的 `operation` 必须是 JSON 对象。索引构建与同步只提供本机管理命令。

| 操作 | 用途 |
| --- | --- |
| `status` | 检查启用、构建状态及新鲜度 |
| `map` | 按目录浏览文件 |
| `symbols` / `explore` | 定位符号；或为问题组合少量定义和直接关系 |
| `callers` / `callees` | 从已定位符号查询调用者或被调用者 |
| `impact` / `affected_tests` | 查看可能受影响的代码与候选测试，保留关系证据 |
| `read` | 按路径、文件摘要和行范围读取当前源码 |
| `changes` / `impact_changes` | 比较相邻索引代次，结合删除前与修改后的图分析影响 |

关系查询和源码读取需要前一次定位结果的 `expected_fingerprint`。
`read` 还需要 `path`、`file_sha256`、`start_line`、`end_line`；API 行号从 1 开始，包含终点。
引用时保留 fingerprint、路径、文件摘要、行范围和片段摘要。完整请求结构见 [HTTP API](../develop/http-api.md)。

成功查询的 JSON 响应受 `max_bytes` 限制，默认 16000，允许 512–32768。
结果达到遍历或输出上限时标记 `partial`。静态影响分析没有覆盖到某个测试，不代表该测试可以安全跳过。

## 仓库更新以后

```mermaid
flowchart LR
  A[修改或切换工作区] --> B[旧索引查询返回 code_changed]
  B --> C[本机执行 code sync]
  C --> D[原子发布新 generation]
  D --> E[重新定位并使用新 fingerprint]
```

```bash
powercontext code sync --scope scp_demo --env-file /srv/powercontext/server.env
```

查询前后都会核对实际文件内容；相同 HEAD、mtime 或文件大小不能证明索引仍然新鲜。
内容变化时返回 `409 code_changed`，不会把旧关系配上新源码。查询不会隐式触发构建。
新增、删除、重命名和未修改调用者的重新绑定均由同步处理。

删除影响需要在同步前保存旧 fingerprint，并在同步后把前后 fingerprint 传给 `impact_changes`。
只保留相邻可比较代次；缺少旧代次、切换分支或基线不兼容时返回 `baseline_unavailable`。
缓存损坏时显式报不可用，可使用 `sync` 修复；全量重建仍可用 `index`。

## 缓存维护与诊断

运维者可以清除当前配置绑定的缓存：

```bash
powercontext code clear --scope scp_demo --env-file /srv/powercontext/server.env
```

命令先取消当前代次的发布，再清理没有活跃读者的代次；其他 Scope 的缓存不受影响。
`retained_reader_generations` 表示仍被读者持有的代次数，读者退出后再次 `clear` 或后续构建会回收它们。
清理后需执行 `index` 或 `sync` 才能查询。移除部署绑定前先执行清理。

Server 的 tracing 会记录 `code.query`、`code.verify`、`code.search`、`code.traverse` 和渲染阶段；
本机构建的 DEBUG 诊断还包括捕获、提取、解析、存储、发布、缓存字节和覆盖率。
属性只包含耗时、计数、状态和稳定原因，不记录查询文本、源码或绝对路径。
RSS 字段是进程生命周期的高水位，父进程和已回收子进程分别报告，不能相加当作一次请求的峰值。
路径受限的图查询通过 `coverage.path_boundary_edges` 报告范围外邻接边数量，不返回对应目标或源码。

## 可选的自动上下文

`prepare_context` 默认不查询代码。请求中设置 `"include_code": true` 才会执行一次 `explore` 并合并代码候选。
多语言候选由同一次查询召回、按统一预算排序和裁剪，不会为每种语言单独占用预算。
PreparedContext 继续使用原有四字段响应，代码引用单独保留为临时证据，不伪造 Artifact 引用。

- 省略 `assembly`：保持既有 Memory、Experience、Topic Memory 选择。
- 显式 `assembly: {}`：保持其 Memory 6 条、Experience 2 条的默认配置。
- `assembly: {"sections": []}` 加 `include_code: true`：只交付代码。

代码最多 4 条；选用了历史类别时，代码最多占总条数与字节预算的一半，未使用额度归还历史内容。
关闭代码、索引缺失、过期或不可用时，历史上下文继续使用完整预算；两者都为空仍返回 `empty`。
源码按不可信数据渲染，出处与信任边界计入内容字节预算。

Codex 和 Claude Code 的召回 Hook 可分别设置：

```dotenv
POWERCONTEXT_CODEX_INCLUDE_CODE=true
POWERCONTEXT_CODEX_REQUEST_TIMEOUT_SECONDS=6
POWERCONTEXT_CODEX_HTTP_BUDGET_SECONDS=8
POWERCONTEXT_CLAUDE_INCLUDE_CODE=true
POWERCONTEXT_CLAUDE_REQUEST_TIMEOUT_SECONDS=6
POWERCONTEXT_CLAUDE_HTTP_BUDGET_SECONDS=8
```

Hook 原有请求超时默认是 1 秒，HTTP 总预算是 4 秒；较大仓库的代码查询可能超过请求超时。
以上示例为默认最多 5 秒的代码查询留出请求余量，同时在插件配置的 10 秒 Hook 截止时间内预留进程开销。
总预算还包括 Scope 解析和其他 HTTP 操作，应按实际部署时延验证；网络或宿主先行超时时，本次上下文可能无法交付。

宿主的 Server 地址、Scope 绑定和认证仍按各自安装配置生效；Codex 地址来自已安装插件的 `.mcp.json`。
只在需要的宿主启用对应变量，并检查 Hook 的实际注入结果。代码查询和自动注入的价值应分别评测，
不能仅凭索引构建成功就判断 Agent 修复质量有所提升。
