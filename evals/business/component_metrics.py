"""Offline component evidence. No Docker/MongoDB or real model benchmark."""
import io
import json
import unittest
from pathlib import Path
from types import SimpleNamespace
from langchain_core.messages import SystemMessage
from src.test.test_memory_layer import FakeStore
from src.agent.memory.keeper import MemoryKeeper
from src.agent.middlewares.warm_memory import WarmMemoryMiddleware, WARM_MEMORY_SLOT


def main():
    groups = {
        'sandbox_and_isolation': [
            'src.test.test_sandbox_lifecycle.SandboxProxyTests',
            'src.test.test_sandbox_lifecycle.HealthRecoveryTests',
            'src.test.test_sandbox_lifecycle.SkillsLifecycleTests',
            'src.test.test_sandbox_lifecycle.IsolationTests',
            'src.test.test_sandbox_lifecycle.MongoNamespaceTests'],
        'memory_integration': ['src.test.test_memory_integration.MemoryIntegrationTests'],
    }
    results = {}
    for label, names in groups.items():
        suite = unittest.TestLoader().loadTestsFromNames(names)
        r = unittest.TextTestRunner(stream=io.StringIO()).run(suite)
        results[label] = dict(total=r.testsRun, failures=len(r.failures), errors=len(r.errors), skipped=len(r.skipped))
    scaling = []
    for count in (10, 100, 300):
        store = FakeStore()
        keeper = MemoryKeeper(store, 'scale-test')
        for i in range(count):
            keeper.upsert_semantic(f'preference-{i}', f'record-{i} ' + '采购偏好测试内容' * 30)
        raw = keeper.build_warm_brief()
        request = SimpleNamespace(system_message=SystemMessage(content=WARM_MEMORY_SLOT),
                                  override=lambda **kw: SimpleNamespace(**kw))
        refreshed = WarmMemoryMiddleware(store, 'scale-test')._refresh(request)
        injected = ''.join(b.get('text', '') for b in refreshed.system_message.content_blocks)
        scaling.append(dict(records=count, raw_brief_characters=len(raw), injected_characters=len(injected), bounded=len(injected)<=4000))
    output = {'scope': 'offline fake sandbox/store; no real Docker recovery time, Mongo concurrency or semantic quality measured',
              'regression': results, 'memory_scaling': scaling,
              'caveat': 'Truncation is a size bound, not proven lossless compression or token/cost improvement.'}
    target = Path(__file__).parent / 'results/component-v1.json'
    target.write_text(json.dumps(output, ensure_ascii=False, indent=2), encoding='utf-8')
    print(json.dumps(output, ensure_ascii=False, indent=2))


if __name__ == '__main__': main()
