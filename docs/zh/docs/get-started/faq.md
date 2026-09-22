---
title: 常见问题
description: 关于 Memory、Handoff、Experience、Skill 与知识生命周期的常见问题。
---

# 常见问题

本页回答学习 PowerContext 时经常遇到的问题。更系统的概念介绍见[核心概念](./core-concepts.md)；具体操作步骤请
参阅相应的工作流指南。

## 四类 Artifact 速览

**问：我经常看到 Memory、Handoff、Experience 和 Skill，应该分别在什么时候用？**

这四个 family 在同一个工作循环里扮演不同角色。想象一个 Agent 在修复 `amount.py` 中的 CSV 解析 bug：

| Family | 在修复 bug 过程中扮演的角色 | 适用场景 |
| --- | --- | --- |
| **Memory** | 保存长期项目约定："金额以整数分存储；超过两位小数的输入必须拒绝。" | 跨越多个会话与 Agent 都应成立的事实、决策或规则。 |
| **Handoff** | 记录"我已确认 bug 在 `cents()` 函数里；明天由下一个 Agent 跑失败的测试并打补丁。" | 把未完成工作的当前状态交接给另一个 Agent 或会话。 |
| **Experience** | 记录已经验证的教训："直接调用 `int(Decimal(text) * 100)` 把 `1.999` 静默截断成了 `199`；现在我们在转换前先校验精度。" | 保留基于证据的情境教训。 |
| **Skill** | 沉淀可复用流程："如何验证金额转换修复——运行测试夹具、检查边界、记录结果。" | 供其他 Agent 加载并遵循的、已验证的可复用配方。 |

一次 bug 修复通常会同时产生这四类内容：要遵守的约定（Memory）、移交的进展（Handoff）、学到的教训
（Experience）、可复用的做法（Skill）。

详见 [Memory 与 Handoff](../workflows/memory-and-handoff.md) 以及
[Experience 与 Skill 的生命周期](../workflows/experience-and-skill-lifecycle.md)。

## Source、Candidate 与知识流水线

**问：Source、Candidate 和已批准的 Artifact 是一条强制流水线吗？**

不是。它们是可以组合的独立概念，但捕获证据本身不会产生已批准的知识：

```text
Source（证据）──┐
                ├──→ Candidate（提案）──→ Review ──→ 已批准 Artifact
已有 Artifact ──┘
```

- **Source** 是原始证据——一轮对话、一次工具结果、一份文档。
- **Candidate** 是从证据或已有 Artifact 派生的提案。在审核前处于 `pending` 状态。
- **Artifact** 是审核批准后得到的产物——带有稳定引用的不可变 Revision。

也可以通过 `remember_memory` 直接写入 Memory，跳过 Source 提取和 Candidate 审核。

**问：pending 状态的 Candidate 会被 `PreparedContext` 召回吗？**

不会。pending Candidate 不参与召回。只有已批准的当前 Revision 才能进入 `PreparedContext`。这样可以防止
未经审核的模型输出悄悄进入 Agent 的工作上下文。

**问：我批准了一个 Skill Candidate，为什么 Agent 还用不了？**

批准、安装和执行是三个独立步骤：

1. **批准**在 PowerContext 中创建一个不可变的 Skill Revision。
2. **导出 / 安装**把指定 Revision 复制到 Agent 宿主（例如通过 Remote Skill 分发，或手动调用
   `download_skill_package`）。
3. **执行**发生在 Agent 宿主发现并加载已安装的 `SKILL.md` 之后。

批准 Skill 不等于安装它；安装它也不等于执行它。每一步都是显式的，以便你掌控"什么内容在什么地方运行"。

## Memory

**问：Source 和 Memory 有什么区别？**

- **Source** 是原始证据：一条聊天消息、一份文件、一段 HTTP 调用记录。按原样保存。
- **Memory** 是经过提炼的知识：一个决策、一条约束、一项事实。它是被刻意写入的（由应用显式写入，或由经过
  批准的提取流程产生）。

Source 是输入；Memory 是策展后的结果。

**问：我通过通用 Artifact API 创建了 Memory，但 `search_memory` 找不到，为什么？**

两条写入路径的效果不同：

| 路径 | 结果 |
| --- | --- |
| `POST /v1/scopes/{id}/artifacts`，`family=memory` | 创建独立的 Memory Artifact；**不参与**日常召回。 |
| `POST /v1/memory/remember` | 写入 Scope 的默认 Memory；**可以被** `search_memory` 检索，并被 `prepare_context` 使用。 |

如果你希望 Agent 真正能召回这条事实，请使用 `/v1/memory/remember`。

**问：修订 Memory 时旧版本会被删除吗？**

不会。Revision 是不可变的。修订 Memory 会创建一个新 Revision，并把旧 Revision 从活跃召回中退役；但旧
Revision 仍可通过 `GET .../revisions/{n}` 读取。这样既能保留审计轨迹，也能在需要时恢复早期措辞。

## Handoff

**问：Handoff 是手动创建的还是 Agent 自动创建的？**

都可以。当人类判断需要移交工作时，应用可以直接调用 `handoff_current_work`；Agent 也可以在其工具流程中
提出 Handoff。两种情况下的流程相同：先返回一份临时预览，只有 `commit_handoff` 才会写入持久的 Revision。

**问：接收方 Agent 怎么知道要做什么？**

Handoff 自身带有结构化字段：目标、带证据引用的当前状态、处置方式（`continuable` / `complete`）、下一步
动作以及已声明的遗漏。接收方 Agent 阅读的是这份内容，而不是完整的先前会话。

## Experience 与 Skill

**问：Experience 和 Skill 有什么区别？**

- **Experience** 是一段经过验证的叙事：情境 → 行动 → 结果 → 教训。它告诉后来的读者*当时发生了什么、学到
  了什么*。
- **Skill** 是一个可复用流程：名称、描述、指令、验证步骤。它告诉后来的 Agent *该怎么做*。

常见模式是：先有一条已批准的 Experience，再基于它生成 Skill Candidate，审核通过后才成为可安装的
Skill。

**问：PowerContext 会自动安装 Skill 吗？**

不会。Skill 作为 Artifact 存储在 PowerContext 中。要让 Agent 能使用它，应用（或 Remote Skill Receiver）必
须显式下载并安装到 Agent 的工作目录。

## 还有疑问？

- 概念模型请见[核心概念](./core-concepts.md)。
- 端到端流程请见[工作流](../workflows/index.md)章节。
- API 细节请见 `openapi/powercontext.yaml`。
- 如果本页内容不清楚或有误，欢迎[提出 Issue](https://github.com/oceanbase/powercontext/issues/new) 帮助
  我们改进。
