# Skills 按需渐进披露

## 目标与实施方案

旧的 `_load_skills_prompt` 会将所有 SKILL.md 和其他 Markdown 正文预先拼入系统提示；沙箱中虽然有技能文件，模型上下文却没有做到按需加载。

本次按以下方案落地：

1. 将技能发现与正文读取拆分，首次只提供元数据。
2. 提供选中技能正文、指定参考资源两类只读工具。
3. 在主 Agent 和配置的业务子 Agent 中接入动态目录，绑定服务端确定的用户身份。
4. 保留物理文件同步和恢复，单独测试提示边界、动态更新和隔离。

## 调用链

```text
用户请求 / 子任务委派
  → 每次模型调用前刷新目录（ID、名称、描述）
  → 模型判断是否需要技能
      ├─ 不需要：直接回答或使用业务工具
      └─ 需要：read_skill(skill_id)
                 → 选中技能完整正文作为工具结果返回
                 → 需要具体引用时 read_skill_resource(skill_id, path)
                 → 大文件按 next_offset 继续读取
                 → 使用已有业务工具/沙箱完成任务
```

`list_skills(query, offset, limit)` 支持目录搜索和翻页。ID 包含来源，避免基础技能与用户技能重名覆盖，例如 `builtin/采购/SKILL.md`、`user/my-skill/SKILL.md`。

## 实现与兼容

- `src/agent/progressive_skills.py`：目录发现、frontmatter 解析、读取工具、中间件及子 Agent 接入。
- `src/agent/main_agent.py`：替换全量正文注入，注册三个工具；`skills=None` 避免与框架内置加载器重复运行。
- 基础技能读取项目 `src/skills`，用户技能读取 Store 的 `("persisted-skills", user_id)` 命名空间。工具参数不能指定其他用户。
- 目录每次模型调用前重新发现，同一缓存 Session 也能看到持久化技能的安装、修改和删除。异步模型调用中的同步发现在线程中执行。
- 只有 frontmatter 的名称与描述进入目录，不会从正文截取摘要。独立 Markdown 只有显式 description 且同目录没有 SKILL.md 时才视作旧格式技能。
- SkillsSyncMiddleware / UserSkillsRestoreMiddleware 仍负责沙箱物理文件和依赖。本文的按需加载指进入模型上下文的时机，不是“只有选中技能才下载文件”。

## 边界与限制

- 目录最多 8,000 字符；单个技能正文最多 64 KiB，超限明确失败而非截断正文；文本资源最多 1 MiB，每次最多返回 16,000 字符（默认 12,000）。这些是字符/字节限制，不是 token 限制。
- 用户目录分页扫描最多 2,000 条持久化文件记录；超限会提示目录可能不完整。每次刷新有文件/Store I/O 开销，尚未做大规模目录吞吐基准。
- 禁止绝对路径、`..`、隐藏路径、符号链接及跨嵌套技能目录读取；只允许指定文本扩展名，并拒绝常见密钥文件名。文件过滤不是任意内容的秘密检测，不能把密钥放入技能文档。
- 技能是低信任参考资料；工具只读，不会执行脚本。原有订单审批与工具授权仍有效。技能可见性不是独立细粒度权限系统。
- “先正文、后资源”由提示引导，不是强制状态机；已知资源可以直接读取。也不能保证模型每次都选对技能，应结合真实任务继续评估选择质量。
- 已读正文作为 ToolMessage 保留在当前历史中，由现有上下文压缩机制处理，不会自动逐轮驱逐。没有新增技能结果缓存，因此重复读取仍会产生工具结果和上下文开销。
- 读取内容来自项目文件/用户 Store。返回的 `execution_path` 在 Docker 模式下是预期同步位置，不代表这个工具已经确认物理文件与依赖恢复成功；无 Docker 时不保证用户技能可在该路径执行。
- 删除/更新会改变下一次目录及读取结果，但不会抹除已经进入对话历史的旧内容。

## 测试与测量

在 WSL 项目根目录运行：

```bash
.venv/bin/python -m unittest src.test.test_progressive_skills src.test.test_sandbox_lifecycle src.test.test_hybrid_review src.test.test_jev_router src.test.test_memory_integration -q
.venv/bin/python -m src.test.test_memory_layer
.venv/bin/python -m src.test.measure_skill_prompt
```

本次结果：67 项 unittest（含 19 项新增专项）及 34 项记忆测试通过。覆盖真实 LangChain 同步/异步图、DeepAgents 主 Agent 委派到子 Agent 后按需读取、三层内容进入提示的时机、用户隔离、中文路径、动态更新、分页及路径拒绝。

图执行使用脚本化模型和内存 Store；本次未运行真实模型、MongoDB、Docker 的端到端组合，因此测试证明链路与边界，不证明线上技能选择准确率。

测量脚本读取本地基线标签 `baseline/pre-progressive-skills-20261009`（需保留该 Git 标签）。相同 9 个基础技能，旧技能提示片段 10,516 字符，新目录 1,476 字符，减少 85.96%。不含新增工具 schema、其他系统提示及后续正文读取；不是 Token、费用、延迟或准确率提升数据。

## 启动后的人工验收

重启 WSL 后端以加载新代码；不需要新增 Key 或修改数据库结构。

1. 问“你好”，查看首轮模型输入中仅有技能目录，没有全量技能正文。
2. 要求“先列出与采购相关的技能，然后读取合适技能，按需要查看其引用文件”，检查工具调用依次按需发生。
3. 安装用户技能后，在同一会话调用 `list_skills` 验证可发现；用另一个用户验证不可见。
4. 触发子任务，确认子 Agent 拥有相同的读取工具；不要要求它预读全部技能。

本次分支为 `codex/progressive-skills`，改造前基线标签已保留。需要对照时用单独 worktree 检出基线，不要用强制重置覆盖当前工作。
