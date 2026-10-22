"""Combine retained first runs; never imply they were a single run."""
import json
from pathlib import Path
from .run import summarize

def main():
    root=Path(__file__).parent/'results'
    batches={name:[json.loads(line) for line in (root/name/'results.jsonl').read_text().splitlines()]
             for name in ('test-v1','extended-v1')}
    assert all(len(rows)==18 for rows in batches.values())
    rows=sum(batches.values(),[])
    summary=summarize(rows)
    components=json.loads((root/'component-v1.json').read_text())
    names={'lookup':'单价查询','calculation':'金额计算','stock':'库存不足','missing':'缺数量追问','approve':'允许工具创建','reject':'拒绝工具创建',
           'supplier':'零件关联供应商','sufficient':'库存充足','exact_stock':'库存刚好够用','zero_stock':'零库存','not_found':'零件不存在','multi_total':'多零件金额汇总'}
    lines=['# 扩展业务与组件评测报告','', '日期：2026-10-11。保留两批各自首轮结果，没有重跑择优。',
           '',f"累计 {summary['overall']['passed']}/36 通过，覆盖12个场景/边界模板，每个3个参数变体；不是36种独立业务。真实模型、模拟ERP；其他运行范围见各批manifest。",
           '', '| 场景/边界 | 验收通过 |','|---|---:|']
    for kind,g in summary['categories'].items(): lines.append(f"| {names[kind]} | {g['passed']}/{g['total']} |")
    lines+=['','## 不同段落可使用的证据','',
            '1. 任务编排：36条业务自动验收用例、12个场景/边界分支；结果如上。不是线上成功率或优化提升。',
            '2. 工具控制：第一批3次授权后建单均仅写入1笔正确订单、3次拒绝均阻断写入；属于工具执行授权，不是ERP订单业务审批状态流转。样本仍少，不建议单写“阻断率100%”。',
            f"3. 沙箱与隔离：离线组件回归 {components['regression']['sandbox_and_isolation']}；覆盖代理替换、健康检查重建、技能同步/恢复、路径安全、用户上下文和命名空间。使用FakeSandbox/FakeStore，不能写真实容器恢复耗时或并发承载能力。",
            f"4. 记忆：离线集成回归 {components['regression']['memory_integration']}；覆盖跨线程刷新、用户隔离、偏好更新、抽取降级及注入限长。另测10/100/300条合成记忆：",'',
            '| 记忆条数 | 原始摘要字符 | 实际注入字符 |','|---:|---:|---:|']
    for r in components['memory_scaling']: lines.append(f"| {r['records']} | {r['raw_brief_characters']} | {r['injected_characters']} |")
    lines+=['','这里的4000是字符，不是Token。实现包含截断，不能写无损压缩、准确率不变或成本降低95%。本次未验证检索Recall@K，也没有真实Docker故障注入或并发压测。',
            '', '## 复现', '', '`python -m evals.business.run --extended --out <新的结果目录>`',
            '`python -m evals.business.component_metrics`', '`python -m evals.business.expanded_report`',
            '', '原始轨迹与数据分别保留于test-v1、extended-v1。组件数据见component-v1.json。业务判定器测试不等于业务任务数量。',
            '', '## 仍存在的不足', '', '任务大多为明确指令的短链路；未覆盖复杂多轮和对抗指令。第一批人工核查发现工具授权与ERP审核的自然语言表述混淆，验收未对最终回复所有语句打分。组件测试不代表生产环境可靠性保证。']
    (root/'EXPANDED_REPORT.md').write_text('\n'.join(lines)+'\n',encoding='utf-8')
    print(json.dumps(summary,ensure_ascii=False))

if __name__=='__main__':main()
