# 采购业务任务验收评测 v1

## 范围

真实 DeepSeek 调用 + `create_main_agent` 原有组装，保留系统提示、业务子 Agent、规则/模型审查、Skills、记忆中间件和 HITL。
四个 MCP 工具注册模块的原函数与参数契约不变，用注册适配器接入 LangChain；函数内 ERP HTTP 客户端替换为内存业务数据。
不是 HTTP/SSE MCP 传输测试，不访问真实 Java ERP，也不创建真实订单。

隔离差异：StateBackend 替代 Docker/LocalShell；内存 Store/Checkpointer 替代 MongoDB；禁用搜索、下载、技能安装、图表与宿主文件工具；框架 memory 文件加载关闭，但项目主提示保留。
路由固定使用 DeepSeek 非思考（本机可能配置 JEV）；主模型保留项目思考配置，模型请求禁用 SDK 自动重试。
因此结果称“真实模型 + 模拟 ERP 的业务流程验收”，不能叫完整生产环境成功率。

## 任务设计与口径

6 类模板各 3 个数字变体，共 18 个正式用例：单价查询、金额计算、库存缺口、缺数量追问、审批通过、审批拒绝。
另有 dev 数据，ID、价格与库存不同，不计入正式分母。不是 18 个独立业务类型，更不是线上采样。
查询类要求最终 JSON 字段，这是为确定性验收增加的输出约束；没有把正确答案传给模型。

- 查询/计算/库存：必须有 ERP 查询记录，所需字段精确匹配，无任何写入。
- 缺字段：没有写入，没有提前触发写审批，出现数量补充中断或明确数量询问。自然语言询问使用启发式规则，报告阶段需人工核对。
- 审批通过：观察到 order_create 的 HITL 中断，模拟审批后恰好创建一张订单，订单号、零件、数量、单价符合题意，没有额外写入。
- 审批拒绝：观察到审批中断并发送拒绝，最终不发生写入。单纯拒绝所有任务但从未到审批，不算通过。
- 超时、异常、未解决审批均判失败（缺字段场景等待补充属于预期成功）。不删除失败样本、不挑最好的一轮。

目前没有业务超时注入、进程崩溃恢复、并发隔离或模糊任务大规模泛化测试。fixture 只实现任务所需接口，其他接口返回501；由此产生的失败需标记环境覆盖问题，不伪装成真实 ERP 结果。
模拟 ERP 不做订单去重，因此重复创建会暴露给判定器，不会被测试环境悄悄修好。

## 运行

```bash
.venv/bin/python -m unittest src.test.test_business_eval -q
.venv/bin/python -m evals.business.run --dev --out evals/business/results/dev-new
.venv/bin/python -m evals.business.run --out evals/business/results/test-v1
```

API Key 仅使用本地 .env，不写入结果。输出目录必须不存在，防止覆盖历史结果。
每任务180秒deadline、主Agent每次run最多12次模型/20次工具调用，整个批次观察到的输入输出token累计超过100万后停止派发下一题。这是软上限，不是全局计费硬限制；子Agent、超时或未返回usage可能造成额外用量。
若提前停止，报告必须注明实际完成/计划总数，不能把未跑的题当作成功。

## 输出

dataset.json 保存题目、fixture、验收答案；manifest.json 保存Git版本、脚本哈希、数据哈希和环境差异。
results.jsonl 保存每题结果、输出、审批载荷、工具轨迹、ERP事实状态、模型usage与耗时。
summary.json 保存总体/分组通过率、nearest-rank P95、观测输入输出token。
耗时包含构建Agent、模型、审查及自动模拟审批，不包含人类真实等待、生产网络ERP或Docker开销。小样本P95不能当线上性能SLO。
模型usage来自回调已返回响应；无usage和失败响应的费用不能推算为零。没有当前价目及账单核对，不输出货币成本。

首版只有当前方案单臂评测，没有“优化前后提升”结论。简历应带模拟环境、样本数和次数，不能写成线上成功率。

## 扩展评测入口（2026-10-11）

在原18条基础上另增18条，覆盖供应商关联查询、多零件金额汇总、库存充足/相等/为零和零件不存在6个分支。两批首轮累计36/36满足业务验收条件，详见 [扩展报告](results/EXPANDED_REPORT.md)。这不是一次36题统一运行，也不是36种独立业务场景。

运行新增用例：`python -m evals.business.run --extended --out <新的结果目录>`。
组件指标：`python -m evals.business.component_metrics`；合并报告：`python -m evals.business.expanded_report`。

验收器提取回复中的JSON字段，不要求整段回复是纯JSON；人工复核发现部分回复附带额外解释，所以36/36不能写成严格格式遵循率100%。新增组件指标使用内存替身，4000字符限长不等于无损压缩或Token节省。
