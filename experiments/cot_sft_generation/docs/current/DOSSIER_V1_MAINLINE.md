# Dossier V1 Mainline

## Status

`dossier_v1` 现在是：

- legacy
- benchmark
- fallback

它不再是默认主线。默认主线请读 [INSIGHT_V1_MAINLINE.md](/root/GenesisGeo-cot/experiments/cot_sft_generation/docs/current/INSIGHT_V1_MAINLINE.md)。

## 仍然保留它的原因

### 1. benchmark 对照

`dossier_v1` 仍然是最接近旧 full-closure 叙述的稳定口径，适合做：

- 回归对照
- 老 artifact 回放
- 结构化质量比较

### 2. scripted fallback

当 `insight_v1` 无法完成以下步骤时，runtime 允许降级到 `dossier_v1`：

- `InsightSlots` 无法从 proof DAG 中可靠抽出
- insight planner 未通过校验
- insight writer 未通过校验

### 3. proof DAG 直出仍有工程价值

`dossier_v1` 现有的 `generate_proof_dag_thinking(...)` 仍适合：

- 检查 proof DAG 可解析性
- 做低成本脚本回归
- 复查 legacy benchmark 的 route fidelity

## 当前范围

保留维护的核心文件：

- [generate_cot_sft.py](/root/GenesisGeo-cot/experiments/cot_sft_generation/generate_cot_sft.py)
- [core/proof_dag.py](/root/GenesisGeo-cot/experiments/cot_sft_generation/core/proof_dag.py)
- [core/audits.py](/root/GenesisGeo-cot/experiments/cot_sft_generation/core/audits.py)
- [tests/test_cot_sft_fixture_pipeline.py](/root/GenesisGeo-cot/tests/test_cot_sft_fixture_pipeline.py)

不再建议继续往 `dossier_v1` 增加新的主训练字段或新的主目标。

## 使用方式

如果需要显式跑 legacy 路线：

```bash
python experiments/cot_sft_generation/generate_cot_sft.py \
  --generation-style dossier_v1
```

如果只是要默认主线，不要再用 `dossier_v1`，直接使用默认 `insight_v1` 即可。
