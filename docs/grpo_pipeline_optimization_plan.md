# GRPO 迭代状态与后续计划

最后更新：2026-05-24 | 当前 commit: `7af5492f6a535d6181583593f98a3d597331c02d`

## 主要结果概览

当前文档默认以**当前仓库下可复现的最新完整评估结果**为主；full `imo_95` 主口径以 ddar bug fix（commit `ed0b877`）后的最新重跑结果为准，旧 commit / 旧 run 结果放在后文作为历史结果保留。

| 版本 | agent / 评估链路 | dev_imo | imo_95 | 备注 |
|------|------------------|---------|--------|------|
| SFT baseline / pre-GRPO | `qwen3_vl_text` multiaux | 14/16 | 58/95 | 基线，`vlm_sft44 checkpoint-20084`，ddar bug fix 后重跑（20260522） |
| v17 checkpoint-500 | `qwen3_vl_text` multiaux | 14/16 | 61/95 | 5k `bucket_unified`，ddar bug fix 前结果（commit `6e24d512`） |
| v18 checkpoint-500 | `vlm` | 14/16 | 55/95 | 10k `bucket_unified`，非当前 commit 历史结果（`f384d702`） |
| **v19 checkpoint-500** | **`qwen3_vl_text` multiaux** | **14/16** | **58/95** | **ddar bug fix 后重跑（20260521）**，`select_balanced` 10k |

补充说明：
- ddar bug fix（commit `ed0b877`）后，sft44 和 v19 在 imo_95 上均为 58/95，GRPO 相对 baseline 的优势在当前 commit 下消失。v19 历史最高曾达 `66/95`（旧 run），bug fix 前最新完整补跑为 `65/95`（commit `6e24d512`），这些历史结果保留在下方来源列表中。
- v17/v19 使用的是 `qwen3_vl_text` multiaux 评估链路；v18 历史结果来自更早的 `vlm` 链路，跨版本比较主要用于主线演进记录。
- v17 尚未在 ddar bug fix 后重跑，其 61/95 为旧 commit 结果，与 sft44/v19 新结果不可直接比较。

## v20-v25 短推理消融概览

`v20-v25` 这一轮不是继续追 `imo_95` 全量 headline，而是围绕短推理主线做 `loss_type / scale_rewards / importance_sampling_level` 对比。需要特别说明：`v21-v24` 基本构成单因子链路，但 `v25` 在最初文档里被误写成 `dapo + group + token`；实际 `train.log` 与 `args.json` 显示它跑的是 `dapo + batch + sequence`，因此应视为 `v20` 风格配置的复跑，而不是新的 grouptoken 消融。由于多次 `safe-eval` 受 Ray startup 假失败污染，这里统一以各版本各自修正后的 `imo95_score_diff_11_final.csv` 口径汇总；`v19` 的 `7/11` 则来自其完整 `imo_95` 结果中对应 11 题的逐题抽取。

| 版本 | 训练差异 | dev_imo | `imo95_score_diff_11`（修正后） | 备注 |
|------|----------|---------|-------------------------------|------|
| v19 | `grpo + group + token` | 14/16 | 7/11 | 当前 full `imo_95` 主线基线 |
| v20 | `dapo + batch + sequence` | 14/16 | 5/11 | 两道 30 多秒假失败补测后仍偏弱 |
| v21 | `dr_grpo + batch + sequence` | 14/16 | 6/11 | 相比 v20 回升，但仍弱于最佳组 |
| v22 | `dr_grpo + group + sequence` | 14/16 | 8/11 | 修正后当前最好之一 |
| v23 | `dr_grpo + group + token` | 14/16 | 6/11 | 两道异常题补测后都是真失败 |
| v24 | `grpo + group + token` | 14/16 | 8/11 | 与 v22 并列当前最好 |
| v25 | `实际与 v20 相同：dapo + batch + sequence` | 14/16 | 5/11 | 目录名/旧文档曾误写为 `grouptoken`；不构成新消融 |

这轮消融的当前结论是：
- `v20` 和 `v25` 实际上是同一组 `dapo + batch + sequence` 配置，并且两次修正后都停在 `5/11`，说明这组配置本身偏弱。
- `group` reward scaling 很关键；`v21 -> v22` 从 `6/11` 直接回升到 `8/11`。
- 在 `group + token` 这条线上，`grpo` 至少不弱于 `dr_grpo`；`v24=8/11`，而 `v23=6/11`。
- 当前没有有效的 `dapo + group + token` 对照实验；旧版文档把 `v25` 写成这组参数是错误归因。
- 当前最强的短推理对比口径仍是 `v22/v24=8/11`；但它们都还没有完整 `imo_95` 重跑，因此 full benchmark 主口径仍以 `v19=58/95`（ddar bug fix 后）为准。

主要证据：
- [v20 dev_imo](/C20545/home/wangzi/GenesisGeo-grpo/results/v20_dapo_batchseq_checkpoint500_qwen3_vl_text_multiaux/eval_single_problem_multi_gpu_qwen3_vl_text_dev_imo_v0-20260515-153615_checkpoint-500_sv1_auxfull_d32_b512_s4_gbs2_gbt100_seed123_20260515T182641Z.csv), [v20 11题修正后汇总](/C20545/home/wangzi/GenesisGeo-grpo/results/v20_dapo_batchseq_checkpoint500_qwen3_vl_text_multiaux/imo95_score_diff_11_final.csv)
- [v21 dev_imo](/C20545/home/wangzi/GenesisGeo-grpo/results/v21_drgrpo_batchseq_checkpoint500_qwen3_vl_text_multiaux/eval_single_problem_multi_gpu_qwen3_vl_text_dev_imo_v1-20260516-042514_checkpoint-500_sv1_auxfull_d32_b512_s4_gbs2_gbt100_seed123_20260516T074742Z.csv), [v21 11题修正后汇总](/C20545/home/wangzi/GenesisGeo-grpo/results/v21_drgrpo_batchseq_checkpoint500_qwen3_vl_text_multiaux/imo95_score_diff_11_final.csv)
- [v22 dev_imo](/C20545/home/wangzi/GenesisGeo-grpo/results/v22_drgrpo_groupseq_checkpoint500_qwen3_vl_text_multiaux/eval_single_problem_multi_gpu_qwen3_vl_text_dev_imo_v0-20260516-134720_checkpoint-500_sv1_auxfull_d32_b512_s4_gbs2_gbt100_seed123_20260516T164611Z.csv), [v22 11题修正后汇总](/C20545/home/wangzi/GenesisGeo-grpo/results/v22_drgrpo_groupseq_checkpoint500_qwen3_vl_text_multiaux/imo95_score_diff_11_final.csv)
- [v23 dev_imo](/C20545/home/wangzi/GenesisGeo-grpo/results/v23_drgrpo_grouptoken_checkpoint500_qwen3_vl_text_multiaux/eval_single_problem_multi_gpu_qwen3_vl_text_dev_imo_v0-20260516-195040_checkpoint-500_sv1_auxfull_d32_b512_s4_gbs2_gbt100_seed123_20260516T224915Z.csv), [v23 11题修正后汇总](/C20545/home/wangzi/GenesisGeo-grpo/results/v23_drgrpo_grouptoken_checkpoint500_qwen3_vl_text_multiaux/imo95_score_diff_11_final.csv)
- [v24 dev_imo](/C20545/home/wangzi/GenesisGeo-grpo/results/v24_grpo_grouptoken_checkpoint500_qwen3_vl_text_multiaux/eval_single_problem_multi_gpu_qwen3_vl_text_dev_imo_v1-20260517-035158_checkpoint-500_sv1_auxfull_d32_b512_s4_gbs2_gbt100_seed123_20260517T100147Z.csv), [v24 11题修正后汇总](/C20545/home/wangzi/GenesisGeo-grpo/results/v24_grpo_grouptoken_checkpoint500_qwen3_vl_text_multiaux/imo95_score_diff_11_final.csv)
- [v25 dev_imo](/C20545/home/wangzi/GenesisGeo-grpo/results/v25_dapo_grouptoken_checkpoint500_qwen3_vl_text_multiaux/eval_single_problem_multi_gpu_qwen3_vl_text_dev_imo_v0-20260517-170112_checkpoint-500_sv1_auxfull_d32_b512_s4_gbs2_gbt100_seed123_20260517T200141Z.csv), [v25 11题修正后汇总](/C20545/home/wangzi/GenesisGeo-grpo/results/v25_dapo_grouptoken_checkpoint500_qwen3_vl_text_multiaux/imo95_score_diff_11_final.csv)

## IMO-95 代理 Benchmark 子集

为了把 `imo_95` 的题目级差异单独拿出来复跑或做 trace drill-down，当前仓库额外维护两个从 [benchmarks/imo_95.txt](/C20545/home/wangzi/GenesisGeo-grpo/benchmarks/imo_95.txt) 抽取出的代理 benchmark：

- [benchmarks/imo95_score_diff_11.txt](/C20545/home/wangzi/GenesisGeo-grpo/benchmarks/imo95_score_diff_11.txt)
  - 格式与 `imo_95.txt` 完全一致，仍然是“题名行 + 题面行”的两行配对格式
  - 包含 `11` 道真正解释主比较 headline 分差的 swing 题
  - 用途：快速复跑主线 score delta 的关键题（基于 ddar bug fix 前的历史 run 构建，对应 `62/95 -> 61/95 -> 65/95`）
- [benchmarks/imo95_mixed_outcomes_20.txt](/C20545/home/wangzi/GenesisGeo-grpo/benchmarks/imo95_mixed_outcomes_20.txt)
  - 同样保持与 `imo_95.txt` 一致的两行配对格式
  - 包含 `20` 道在 8 个完整 run 里曾出现 solved / unsolved 翻转的题
  - 用途：覆盖全部不稳定题，用于 agent/link 差异、singleaux-vs-multiaux 差异和 trace 稳定性排查

这两个子集的关系是：

- `imo95_score_diff_11.txt` 是更小、更聚焦的主分差题集
- `imo95_mixed_outcomes_20.txt` 是它的超集，额外包含 9 道“有翻转但不解释主比较 headline 分差”的题

这两个子集的分析来源固定为 `8` 个完整 `95/95` 的 `imo_95` run；所有集合判断都基于这些 run 的逐题 `Solved` 列，明确排除了 `partial` / `resume` 中间产物，以及 `2026-05-12` 那个只解出 `1/95` 的中断 run。具体来源如下：

- pre-GRPO multiaux baseline
  - agent：`qwen3_vl_text`
  - model：`vlm_sft44 checkpoint-20084`
  - **最新结果 CSV（ddar bug fix 后，20260522，58/95）**：`results/pre_grpo_vlm_sft44_checkpoint20084_qwen3_vl_text_multiaux/eval_single_problem_multi_gpu_qwen3_vl_text_imo_95_vlm_sft44_checkpoint-20084_sv1_auxfull_d32_b512_s4_gbs2_gbt100_seed123_20260522T073225Z.csv`
  - 历史结果 CSV（ddar bug fix 前，20260510，62/95）：`results/pre_grpo_vlm_sft44_checkpoint20084_qwen3_vl_text_multiaux/eval_single_problem_multi_gpu_qwen3_vl_text_imo_95_vlm_sft44_checkpoint-20084_sv1_d32_b512_s4_gbs2_gbt100_seed123_20260510T045624Z.csv`
  - eval commit（历史）：`392ea7f6dd8d2f91824783494b78384c12db4428`
- v17 multiaux
  - agent：`qwen3_vl_text`
  - model：`models/grpo_vlm_sft44_geometry100k_v17_s1_4gpu_lr5e6/v0-20260423-165556/checkpoint-500`
  - 结果 CSV：`results/v17_lr5e6_checkpoint500_qwen3_vl_text_multiaux/eval_single_problem_multi_gpu_qwen3_vl_text_imo_95_v0-20260423-165556_checkpoint-500_sv1_auxfull_d32_b512_s4_gbs2_gbt100_seed123_20260514T043538Z.csv`
  - eval commit：`6e24d5121e6264eaf5f7c2dc30e184c52f8d5436`
- v19 multiaux
  - agent：`qwen3_vl_text`
  - model：`models/grpo_vlm_sft44_geometry100k_v19_s1_4gpu_lr5e6/v0-20260508-105855/checkpoint-500`
  - **最新结果 CSV（ddar bug fix 后，20260521，58/95）**：`results/v19_lr5e6_checkpoint500_qwen3_vl_text_multiaux/eval_single_problem_multi_gpu_qwen3_vl_text_imo_95_v0-20260508-105855_checkpoint-500_sv1_auxfull_d32_b512_s4_gbs2_gbt100_seed123_20260521T133115Z.csv`
  - 历史结果 CSV（ddar bug fix 前，20260513，65/95）：`results/v19_lr5e6_checkpoint500_qwen3_vl_text_multiaux/eval_single_problem_multi_gpu_qwen3_vl_text_imo_95_v0-20260508-105855_checkpoint-500_sv1_auxfull_d32_b512_s4_gbs2_gbt100_seed123_20260513T073845Z.csv`
  - eval commit（历史）：`6e24d5121e6264eaf5f7c2dc30e184c52f8d5436`
- v17 singleaux
  - agent：`qwen3_vl_text`
  - model：`models/grpo_vlm_sft44_geometry100k_v17_s1_4gpu_lr5e6/v0-20260423-165556/checkpoint-500`
  - 结果 CSV：`results/v17_lr5e6_checkpoint500_qwen3_vl_text_singleaux/eval_single_problem_multi_gpu_qwen3_vl_text_imo_95_v0-20260423-165556_checkpoint-500_sv1_d32_b512_s4_gbs2_gbt100_seed123_20260430T073751Z.csv`
  - eval commit：`7f98879d4a0006112636abbbe5cd44f5a2e676a4`
- v19 singleaux
  - agent：`qwen3_vl_text`
  - model：`models/grpo_vlm_sft44_geometry100k_v19_s1_4gpu_lr5e6/v0-20260508-105855/checkpoint-500`
  - 结果 CSV：`results/v19_lr5e6_checkpoint500_qwen3_vl_text_singleaux/eval_single_problem_multi_gpu_qwen3_vl_text_imo_95_v0-20260508-105855_checkpoint-500_sv1_auxfirst_d32_b512_s4_gbs2_gbt100_seed123_20260511T091631Z.csv`
  - eval commit：`5b167cf2ec6cd6b65adf849152fbcb7520783149`
- v16 `vlm`
  - agent：`vlm`
  - model：`models/grpo_vlm_sft44_geometry100k_maxaux8_v16_s1_4gpu_lr5e6/v0-20260422-154539/checkpoint-500`
  - 结果 CSV：`results/v16_lr5e6_checkpoint500_vlm/imo_95_v16_checkpoint500_merged.csv`
  - eval commit：`a5482b00ad8b8f5623b3c48166415490303ae7a7`
- v17 `vlm`
  - agent：`vlm`
  - model：`models/grpo_vlm_sft44_geometry100k_v17_s1_4gpu_lr5e6/v0-20260423-165556/checkpoint-500`
  - 结果 CSV：`results/v17_lr5e6_checkpoint500_vlm/imo_95_v17_checkpoint500_merged.csv`
  - eval commit：`e577945a27a86a7038ed57b7c9039eab55f8d3e9`
- v18 `vlm`
  - agent：`vlm`
  - model：`models/grpo_vlm_sft44_geometry100k_v18_s1_4gpu_lr5e6/v0-20260427-200556/checkpoint-500`
  - 结果 CSV：`results/v18_lr5e6_checkpoint500_vlm/imo_95_v18_checkpoint500_merged.csv`
  - eval commit：`f384d7029f283c790acb9fb77a1b039511a3b750`

## 背景

- 基础模型（SFT baseline / pre-GRPO）：`vlm_sft44`
  - 模型路径：`/C20545/home/wangzi/GenesisGeo_data_models/models/vlm_sft44/checkpoint-20084`
  - 结果归属：均为**非当前 commit 历史结果**
    - **评估结果路径**：
    - **dev_imo 评估**：
      - CSV：`results/devimo_grpo_compare/vlm_sft44/eval_single_problem_multi_gpu_qwen3_vl_text_dev_imo_vlm_sft44_checkpoint-20084_sv1_d32_b512_s4_gbs4_gbt100_seed123_20260422T062514Z.csv`（14/16，run commit: `88851cfca89a9e2f286b3db820ecf20b4dcf32e4`）
      - trace 目录：`results/devimo_grpo_compare/vlm_sft44/eval_single_problem_multi_gpu_qwen3_vl_text_dev_imo_vlm_sft44_checkpoint-20084_sv1_d32_b512_s4_gbs4_gbt100_seed123_20260422T062514Z/`
        - problems/：单题 trace（`0000_translated_imo_2000_p6.jsonl` 等）
        - attempts/：求解尝试记录
    - **imo_95 评估**：
      - 初始 run trace 目录：`results/devimo_grpo_compare/eval_single_problem_multi_gpu_qwen3_vl_text_imo_95_vlm_sft44_checkpoint-20084_d32_b512_s4_gbs2_gbt100_seed123_20260417T062654Z/`（run commit: `51686a420ce49dd991f5d4b10d3f9e904553b24c`）
      - resume run trace 目录：`results/devimo_grpo_compare/eval_single_problem_multi_gpu_qwen3_vl_text_imo_95_resume_from_20260417T062654Z_vlm_sft44_checkpoint-20084_d32_b512_s4_gbs2_gbt100_seed123_20260417T104054Z/`（run commit: `51686a420ce49dd991f5d4b10d3f9e904553b24c`）
      - **merged 合并结果**：`results/devimo_grpo_compare/imo_95_resume_from_20260417T062654Z_merged.csv`（54/95，非当前 commit 历史结果，对应 run commit: `51686a420ce49dd991f5d4b10d3f9e904553b24c`）
        - problems/：单题 trace（`0000_imo_1983_p2.jsonl` 等）
        - attempts/：求解尝试记录
- 原始数据源（版本相关）：
  - v12 及以前：`/C20545/home/wangzi/GenesisGeo_data_models/datasets/0123/geometry_clauses10_samples1M_aux_updated_img512_inverted_pt_new_remove_proof.jsonl`
  - v13：`/C20545/home/wangzi/GenesisGeo/datasets/20260421_maxaux5/geometry_clauses10_samples100k.jsonl`
  - v14-v18：`/C20545/home/wangzi/GenesisGeo/datasets/maxaux8/20260421/geometry_clauses10_samples100k.jsonl`
  - v19-v25：`datasets/maxaux8/20260429/geometry_clauses10_samples1M_select_balanced_10k.jsonl`
- 当前训练入口：`scripts/grpo/train_grpo.sh`
- 当前 selector 入口：`scripts/grpo/select_debug_set.py`
- 核心判断：主要瓶颈仍然还是数据分布，但 `v20-v25` 表明 `reward scaling / loss_type / importance_sampling_level` 也会显著影响短推理子集表现

## 采样效率分析

**详细分析文档**：[v17 vs Baseline 采样效率对比分析](v17_vs_baseline_sampling_efficiency_analysis.md)

**核心发现**（dev_imo 数据集，按 attempt_key 计数真正的不同 aux）：
- v17 用 **2.7% 更少的总候选数**，生成了 **9.5% 更多的唯一 aux**
- **全局 aux 唯一率提升 4.30 个百分点**（38.53% vs 34.23%，相对提升 12.6%）
- **深度 2 aux 唯一率提升 3.49 pp**（27.13% vs 23.64%），是主要改进点（占总改进 81%）
- **深度 1 aux 唯一率提升 1.05 pp**（9.44% vs 8.40%），占总改进 24%
- 相对重复率下降 6.5%，说明模型的提议更加多样化
- **结论**：GRPO 训练显著提升了采样效率，特别是在深度 2 层级，模型学会了生成更多样化的 aux

---

## 版本历史（主线 + 归档）

### v25 (2026-05-17~18) - 更正：这不是 `group + token` 消融，而是 `v20` 风格复跑

**数据集**：`datasets/maxaux8/20260429/geometry_clauses10_samples1M_select_balanced_10k.jsonl`

**模型训练目录**：`models/grpo_vlm_sft44_geometry100k_v25_s1_4gpu_dapo_grouptoken`

**核心变更**：
- 错误更正（2026-05-18）：旧版文档曾把 `v25` 写成“在 `v24` 基础上只改 `loss_type = grpo -> dapo`”
- 实际 `train.log`、启动命令与最终 `args.json` 都显示，本次 run 的真实参数是 `loss_type = dapo`、`scale_rewards = batch`、`importance_sampling_level = sequence`
- 因此 `v25` 应视为 `v20` 风格配置的复跑，而不是 `dapo + group + token` 的有效对照实验
- 目录名里的 `dapo_grouptoken` 是历史误命名，不代表真实训练参数

**训练配置**：实际与 `v20` 一致
- `learning_rate = 5e-6`，`warmup_steps = 10`，`lr_scheduler_type = cosine`
- `per_device_train_batch_size = 1`，`gradient_accumulation_steps = 8`，`num_generations = 8`
- `NPROC_PER_NODE = 4`，`temperature = 1.1`，`top_p = 0.95`，`top_k = 0`，`beta = 0.02`
- `loss_type = dapo`，`scale_rewards = batch`，`importance_sampling_level = sequence`
- `max_steps = 500`，`save_steps = 50`
- 训练脚本：[tmp/train_v25.sh](/C20545/home/wangzi/GenesisGeo-grpo/tmp/train_v25.sh)
- 关键证据：
  - [tmp/train_v25.sh](/C20545/home/wangzi/GenesisGeo-grpo/tmp/train_v25.sh)
  - [train.log](/C20545/home/wangzi/GenesisGeo-grpo/models/grpo_vlm_sft44_geometry100k_v25_s1_4gpu_dapo_grouptoken/train.log)
  - [args.json](/C20545/home/wangzi/GenesisGeo-grpo/models/grpo_vlm_sft44_geometry100k_v25_s1_4gpu_dapo_grouptoken/v0-20260517-170112/args.json)

**评估结果**：
- ✅ dev_imo：**14/16**
  - [eval_single_problem_multi_gpu_qwen3_vl_text_dev_imo_v0-20260517-170112_checkpoint-500_sv1_auxfull_d32_b512_s4_gbs2_gbt100_seed123_20260517T200141Z.csv](/C20545/home/wangzi/GenesisGeo-grpo/results/v25_dapo_grouptoken_checkpoint500_qwen3_vl_text_multiaux/eval_single_problem_multi_gpu_qwen3_vl_text_dev_imo_v0-20260517-170112_checkpoint-500_sv1_auxfull_d32_b512_s4_gbs2_gbt100_seed123_20260517T200141Z.csv)
- ✅ imo95_score_diff_11：**5/11**
  - 初始 `safe-eval` 为 `4/11`
  - `imo_sl_2016_g5_variant` 在初始安全跑里是 `34.73s` 的 Ray startup 假失败；补测后修正为 `Success`
  - 修正后汇总：[imo95_score_diff_11_final.csv](/C20545/home/wangzi/GenesisGeo-grpo/results/v25_dapo_grouptoken_checkpoint500_qwen3_vl_text_multiaux/imo95_score_diff_11_final.csv)
- full `imo_95`：暂未完整补跑
- 评估产物目录：`results/v25_dapo_grouptoken_checkpoint500_qwen3_vl_text_multiaux/`

**结论**：
- `v25` 不能再被解读为“`dapo + group + token` 也只有 `5/11`”
- 正确解读是：`dapo + batch + sequence` 这组配置在 `v20` 与 `v25` 两次 run 里都停在 `5/11`
- 因而它强化的是 `v20` 这组配置偏弱的判断，而不是对 `dapo + group + token` 的判断

---

### v24 (2026-05-17) - `grpo` 在 `group + token` 上追平当前最好结果

**数据集**：`datasets/maxaux8/20260429/geometry_clauses10_samples1M_select_balanced_10k.jsonl`

**模型训练目录**：`models/grpo_vlm_sft44_geometry100k_v24_s1_4gpu_grpo_grouptoken`

**核心变更**：
- 在 `v23` 基础上只改一项：`loss_type = dr_grpo -> grpo`
- 其余保留 `group` reward scaling 与 `token` importance sampling

**训练配置**：与 `v23` 基本一致
- `learning_rate = 5e-6`，`warmup_steps = 10`，`lr_scheduler_type = cosine`
- `per_device_train_batch_size = 1`，`gradient_accumulation_steps = 8`，`num_generations = 8`
- `NPROC_PER_NODE = 4`，`temperature = 1.1`，`top_p = 0.95`，`top_k = 0`，`beta = 0.02`
- `max_steps = 500`，`save_steps = 50`
- 训练脚本：[tmp/train_v24.sh](/C20545/home/wangzi/GenesisGeo-grpo/tmp/train_v24.sh)

**评估结果**：
- ✅ dev_imo：**14/16**
  - [eval_single_problem_multi_gpu_qwen3_vl_text_dev_imo_v1-20260517-035158_checkpoint-500_sv1_auxfull_d32_b512_s4_gbs2_gbt100_seed123_20260517T100147Z.csv](/C20545/home/wangzi/GenesisGeo-grpo/results/v24_grpo_grouptoken_checkpoint500_qwen3_vl_text_multiaux/eval_single_problem_multi_gpu_qwen3_vl_text_dev_imo_v1-20260517-035158_checkpoint-500_sv1_auxfull_d32_b512_s4_gbs2_gbt100_seed123_20260517T100147Z.csv)
- ✅ imo95_score_diff_11：**8/11**
  - 初始 `safe-eval` 为 `5/11`
  - `imo_sl_2009_g6`、`imo_sl_2013_g2`、`imo_sl_2015_g5_variant`、`imo_sl_2020_g6` 在初始安全跑里都受 Ray startup 假失败污染
  - 补测修正后汇总：[imo95_score_diff_11_final.csv](/C20545/home/wangzi/GenesisGeo-grpo/results/v24_grpo_grouptoken_checkpoint500_qwen3_vl_text_multiaux/imo95_score_diff_11_final.csv)
- full `imo_95`：暂未完整补跑
- 评估产物目录：`results/v24_grpo_grouptoken_checkpoint500_qwen3_vl_text_multiaux/`

**结论**：
- `v24` 修正后达到 `8/11`，与 `v22` 并列当前最好
- 在这条 `group + token` 主线上，`grpo` 至少不弱于 `dr_grpo`

---

### v23 (2026-05-16~17) - `token` importance sampling 未带来收益

**数据集**：`datasets/maxaux8/20260429/geometry_clauses10_samples1M_select_balanced_10k.jsonl`

**模型训练目录**：`models/grpo_vlm_sft44_geometry100k_v23_s1_4gpu_drgrpo_grouptoken`

**核心变更**：
- 在 `v22` 基础上只改一项：`importance_sampling_level = sequence -> token`
- 其余保留 `dr_grpo + group`

**训练配置**：与 `v22` 基本一致
- `learning_rate = 5e-6`，`warmup_steps = 10`，`lr_scheduler_type = cosine`
- `per_device_train_batch_size = 1`，`gradient_accumulation_steps = 8`，`num_generations = 8`
- `NPROC_PER_NODE = 4`，`temperature = 1.1`，`top_p = 0.95`，`top_k = 0`，`beta = 0.02`
- `max_steps = 500`，`save_steps = 50`
- 训练脚本：[tmp/train_v23.sh](/C20545/home/wangzi/GenesisGeo-grpo/tmp/train_v23.sh)

**评估结果**：
- ✅ dev_imo：**14/16**
  - [eval_single_problem_multi_gpu_qwen3_vl_text_dev_imo_v0-20260516-195040_checkpoint-500_sv1_auxfull_d32_b512_s4_gbs2_gbt100_seed123_20260516T224915Z.csv](/C20545/home/wangzi/GenesisGeo-grpo/results/v23_drgrpo_grouptoken_checkpoint500_qwen3_vl_text_multiaux/eval_single_problem_multi_gpu_qwen3_vl_text_dev_imo_v0-20260516-195040_checkpoint-500_sv1_auxfull_d32_b512_s4_gbs2_gbt100_seed123_20260516T224915Z.csv)
- ✅ imo95_score_diff_11：**6/11**
  - 初始 `safe-eval` 为 `6/11`
  - `imo_sl_2002_g7_variant` 和 `imo_sl_2013_g2` 都出现了约 `34s` 的异常失败；补测后两题都仍为真实失败
  - 修正后汇总：[imo95_score_diff_11_final.csv](/C20545/home/wangzi/GenesisGeo-grpo/results/v23_drgrpo_grouptoken_checkpoint500_qwen3_vl_text_multiaux/imo95_score_diff_11_final.csv)
- full `imo_95`：暂未完整补跑
- 评估产物目录：`results/v23_drgrpo_grouptoken_checkpoint500_qwen3_vl_text_multiaux/`

**结论**：
- 把 `importance_sampling_level` 从 `sequence` 改回 `token` 后，修正后仍只有 `6/11`
- 至少在当前主线上，`token` importance sampling 明显不如 `sequence`

---

### v22 (2026-05-16~17) - `group` reward scaling 是关键回升点

**数据集**：`datasets/maxaux8/20260429/geometry_clauses10_samples1M_select_balanced_10k.jsonl`

**模型训练目录**：`models/grpo_vlm_sft44_geometry100k_v22_s1_4gpu_drgrpo_groupseq`

**核心变更**：
- 在 `v21` 基础上只改一项：`scale_rewards = batch -> group`
- 其余保留 `dr_grpo + sequence`

**训练配置**：与 `v21` 基本一致
- `learning_rate = 5e-6`，`warmup_steps = 10`，`lr_scheduler_type = cosine`
- `per_device_train_batch_size = 1`，`gradient_accumulation_steps = 8`，`num_generations = 8`
- `NPROC_PER_NODE = 4`，`temperature = 1.1`，`top_p = 0.95`，`top_k = 0`，`beta = 0.02`
- `max_steps = 500`，`save_steps = 50`
- 训练脚本：[tmp/train_v22.sh](/C20545/home/wangzi/GenesisGeo-grpo/tmp/train_v22.sh)

**评估结果**：
- ✅ dev_imo：**14/16**
  - [eval_single_problem_multi_gpu_qwen3_vl_text_dev_imo_v0-20260516-134720_checkpoint-500_sv1_auxfull_d32_b512_s4_gbs2_gbt100_seed123_20260516T164611Z.csv](/C20545/home/wangzi/GenesisGeo-grpo/results/v22_drgrpo_groupseq_checkpoint500_qwen3_vl_text_multiaux/eval_single_problem_multi_gpu_qwen3_vl_text_dev_imo_v0-20260516-134720_checkpoint-500_sv1_auxfull_d32_b512_s4_gbs2_gbt100_seed123_20260516T164611Z.csv)
- ✅ imo95_score_diff_11：**8/11**
  - 初始 `safe-eval` 为 `4/11`
  - 多道题在初始安全跑里出现约 `34s` 的 Ray startup 假失败；补测后真实结果回升
  - 修正后汇总：[imo95_score_diff_11_final.csv](/C20545/home/wangzi/GenesisGeo-grpo/results/v22_drgrpo_groupseq_checkpoint500_qwen3_vl_text_multiaux/imo95_score_diff_11_final.csv)
- full `imo_95`：暂未完整补跑
- 评估产物目录：`results/v22_drgrpo_groupseq_checkpoint500_qwen3_vl_text_multiaux/`

**结论**：
- `v22` 修正后达到 `8/11`，是当前短推理对比口径里最强的一组
- `v21 -> v22` 的跃升说明 `group` reward scaling 比 `batch` 明显更适合当前主线

---

### v21 (2026-05-16~18) - 去掉 `dapo` 后先回升一步

**数据集**：`datasets/maxaux8/20260429/geometry_clauses10_samples1M_select_balanced_10k.jsonl`

**模型训练目录**：`models/grpo_vlm_sft44_geometry100k_v21_s1_4gpu_drgrpo_batchseq`

**核心变更**：
- 在 `v20` 基础上只改一项：`loss_type = dapo -> dr_grpo`
- 其余保留 `batch` reward scaling 与 `sequence` importance sampling

**训练配置**：与 `v20` 基本一致
- `learning_rate = 5e-6`，`warmup_steps = 10`，`lr_scheduler_type = cosine`
- `per_device_train_batch_size = 1`，`gradient_accumulation_steps = 8`，`num_generations = 8`
- `NPROC_PER_NODE = 4`，`temperature = 1.1`，`top_p = 0.95`，`top_k = 0`，`beta = 0.02`
- `max_steps = 500`，`save_steps = 50`
- 训练脚本：[tmp/train_v21.sh](/C20545/home/wangzi/GenesisGeo-grpo/tmp/train_v21.sh)

**评估结果**：
- ✅ dev_imo：**14/16**
  - [eval_single_problem_multi_gpu_qwen3_vl_text_dev_imo_v1-20260516-042514_checkpoint-500_sv1_auxfull_d32_b512_s4_gbs2_gbt100_seed123_20260516T074742Z.csv](/C20545/home/wangzi/GenesisGeo-grpo/results/v21_drgrpo_batchseq_checkpoint500_qwen3_vl_text_multiaux/eval_single_problem_multi_gpu_qwen3_vl_text_dev_imo_v1-20260516-042514_checkpoint-500_sv1_auxfull_d32_b512_s4_gbs2_gbt100_seed123_20260516T074742Z.csv)
- ✅ imo95_score_diff_11：**6/11**
  - 初始 `safe-eval` 为 `5/11`
  - `imo_sl_2013_g2` 和 `imo_sl_2020_g6` 在初始安全跑里受 infra 污染；补测后前者修正为 `Success`，后者仍为真实失败
  - 修正后汇总：[imo95_score_diff_11_final.csv](/C20545/home/wangzi/GenesisGeo-grpo/results/v21_drgrpo_batchseq_checkpoint500_qwen3_vl_text_multiaux/imo95_score_diff_11_final.csv)
- full `imo_95`：暂未完整补跑
- 评估产物目录：`results/v21_drgrpo_batchseq_checkpoint500_qwen3_vl_text_multiaux/`

**结论**：
- 单独把 `loss_type` 从 `dapo` 改回 `dr_grpo` 后，结果从 `5/11` 回升到 `6/11`
- 这说明优先去掉 `dapo` 是对的，但 `batch + sequence` 这条线还不是最佳组合

---

### v20 (2026-05-15~18) - 结构化目标首测但短推理表现偏弱

**数据集**：`datasets/maxaux8/20260429/geometry_clauses10_samples1M_select_balanced_10k.jsonl`

**模型训练目录**：`models/grpo_vlm_sft44_geometry100k_v20_s1_4gpu_dapo_batchseq`

**核心变更**：
- 相对 `v19`，优先验证 `dapo + batch + sequence` 这一组更结构化的训练目标
- 目标是测试它在非长推理场景下是否也能成为更好的主线

**训练配置**：与 `v19` 基本一致，重点只改目标函数相关项
- `learning_rate = 5e-6`，`warmup_steps = 10`，`lr_scheduler_type = cosine`
- `per_device_train_batch_size = 1`，`gradient_accumulation_steps = 8`，`num_generations = 8`
- `NPROC_PER_NODE = 4`，`temperature = 1.1`，`top_p = 0.95`，`top_k = 0`，`beta = 0.02`
- `loss_type = dapo`，`scale_rewards = batch`，`importance_sampling_level = sequence`
- `max_steps = 500`，`save_steps = 50`
- 训练脚本：[tmp/train_v20.sh](/C20545/home/wangzi/GenesisGeo-grpo/tmp/train_v20.sh)

**评估结果**：
- ✅ dev_imo：**14/16**
  - [eval_single_problem_multi_gpu_qwen3_vl_text_dev_imo_v0-20260515-153615_checkpoint-500_sv1_auxfull_d32_b512_s4_gbs2_gbt100_seed123_20260515T182641Z.csv](/C20545/home/wangzi/GenesisGeo-grpo/results/v20_dapo_batchseq_checkpoint500_qwen3_vl_text_multiaux/eval_single_problem_multi_gpu_qwen3_vl_text_dev_imo_v0-20260515-153615_checkpoint-500_sv1_auxfull_d32_b512_s4_gbs2_gbt100_seed123_20260515T182641Z.csv)
- ✅ imo95_score_diff_11：**5/11**
  - 初始 `safe-eval` 为 `3/11`
  - `imo_sl_2015_g5_variant` 和 `imo_sl_2020_g6` 在初始安全跑里是 30 多秒的 Ray startup 假失败；补测后都修正为 `Success`
  - 修正后汇总：[imo95_score_diff_11_final.csv](/C20545/home/wangzi/GenesisGeo-grpo/results/v20_dapo_batchseq_checkpoint500_qwen3_vl_text_multiaux/imo95_score_diff_11_final.csv)
- full `imo_95`：暂未完整补跑
- 评估产物目录：`results/v20_dapo_batchseq_checkpoint500_qwen3_vl_text_multiaux/`

**结论**：
- `dev_imo` 没掉，但修正 infra 后 11 题子集仍只有 `5/11`
- 这说明 `dapo + batch + sequence` 不适合作为当前短推理主线的优先方向

---

### v19 (2026-05-08~14) - **当前最新 multiaux 主线**

**数据集**：`datasets/maxaux8/20260429/geometry_clauses10_samples1M_select_balanced_10k.jsonl`

**模型训练目录**：`models/grpo_vlm_sft44_geometry100k_v19_s1_4gpu_lr5e6`

**核心变更**：
- 从 v17/v18 的 debug-set 5k/10k bucket_unified 选集切换到 `select_balanced` 10k 数据集
- 训练配置保持与 v17/v18 对齐，重点验证更大、更平衡的数据源是否能提升 `qwen3_vl_text` multiaux 评估

**训练配置**：与 v17/v18 基本一致
- `learning_rate = 5e-6`，`warmup_steps = 10`，`lr_scheduler_type = cosine`
- `per_device_train_batch_size = 1`，`gradient_accumulation_steps = 8`，`num_generations = 8`
- `NPROC_PER_NODE = 4`，`temperature = 1.1`，`top_p = 0.95`，`top_k = 0`，`beta = 0.02`
- `max_steps = 500`，`save_steps = 50`
- 训练脚本：`tmp/train_v19.sh`

**主评估结果（multiaux / `qwen3_vl_text`，当前 commit）**：
- ✅ dev_imo：**14/16**
  - 2026-05-13 05:42:15 UTC 的中断 run 先停在 8/16，随后恢复并合并为：
  - `results/v19_lr5e6_checkpoint500_qwen3_vl_text_multiaux/dev_imo_resume_from_20260513_054215_merged.csv`
- ✅ imo_95：**65/95**
  - 最新完整重跑 CSV：`results/v19_lr5e6_checkpoint500_qwen3_vl_text_multiaux/eval_single_problem_multi_gpu_qwen3_vl_text_imo_95_v0-20260508-105855_checkpoint-500_sv1_auxfull_d32_b512_s4_gbs2_gbt100_seed123_20260513T073845Z.csv`
- 评估产物目录：`results/v19_lr5e6_checkpoint500_qwen3_vl_text_multiaux/`

**历史结果（旧 commit / 旧 run）**：
- dev_imo：**14/16**
  - `results/v19_lr5e6_checkpoint500_qwen3_vl_text_multiaux/eval_single_problem_multi_gpu_qwen3_vl_text_dev_imo_v0-20260508-105855_checkpoint-500_sv1_d32_b512_s4_gbs2_gbt100_seed123_20260508T143514Z.csv`（run commit: `392ea7f6dd8d2f91824783494b78384c12db4428`）
- imo_95：**66/95**
  - 初始 partial CSV：`results/v19_lr5e6_checkpoint500_qwen3_vl_text_multiaux/imo_95_v19_checkpoint500_partial.csv`（42/95，对应 run commit: `627150920bd4b856c5577b6ec9206d5996da3b6c`）
  - remaining CSV：`results/v19_lr5e6_checkpoint500_qwen3_vl_text_multiaux/eval_single_problem_multi_gpu_qwen3_vl_text_imo_95_v19_checkpoint500_remaining_v0-20260508-105855_checkpoint-500_sv1_d32_b512_s4_gbs2_gbt100_seed123_20260509T053840Z.csv`（24/52，对应 run commit: `392ea7f6dd8d2f91824783494b78384c12db4428`）
  - merged 合并结果：`results/v19_lr5e6_checkpoint500_qwen3_vl_text_multiaux/imo_95_v19_checkpoint500_merged.csv`（非当前 commit 历史结果，由上述两个旧 run 合并）
- 说明：
  - 当前 commit 的主结果应以最新完整补跑 `65/95` 为准
  - `66/95` 作为历史最佳 run 保留，说明该配置在不同 run 间存在轻微波动上界

**singleaux 对照结果**：
- dev_imo：`13/16`
  - `results/v19_lr5e6_checkpoint500_qwen3_vl_text_singleaux/eval_single_problem_multi_gpu_qwen3_vl_text_dev_imo_v0-20260508-105855_checkpoint-500_sv1_auxfirst_d32_b512_s4_gbs2_gbt100_seed123_20260511T084607Z.csv`（非当前 commit，run commit: `5b167cf2ec6cd6b65adf849152fbcb7520783149`）
- imo_95：`55/95`
  - `results/v19_lr5e6_checkpoint500_qwen3_vl_text_singleaux/eval_single_problem_multi_gpu_qwen3_vl_text_imo_95_v0-20260508-105855_checkpoint-500_sv1_auxfirst_d32_b512_s4_gbs2_gbt100_seed123_20260511T091631Z.csv`（非当前 commit，run commit: `5b167cf2ec6cd6b65adf849152fbcb7520783149`）

**说明**：
- `v19` 文档主结果使用的是 `qwen3_vl_text` agent；下面的 `v16/v17/v18` 历史结果则来自更早的 `vlm` agent 评估链路
- 因此跨版本结论主要用于主线演进记录，不应把 `v16/v17/v18` 与 `v19 qwen3_vl_text` 做严格 apples-to-apples 的 agent 实现对比

**对比基线**：

| 版本 | dev_imo | imo_95 | 备注 |
|------|---------|--------|------|
| SFT baseline / pre-GRPO multiaux | 14/16 | 62/95 | `qwen3_vl_text` multiaux，`vlm_sft44 checkpoint-20084`，非当前 commit（dev: `88851cfc` / imo95: `51686a42`） |
| v17 checkpoint-500 (`qwen3_vl_text`，当前 commit) | 14/16 | 61/95 | 2026-05-14 multiaux 补跑 |
| v17 checkpoint-500 (`vlm` 历史结果) | 14/16 | 59/95 | 5k bucket_unified，非当前 commit / 旧评估链路 |
| v18 checkpoint-500 | 14/16 | 55/95 | 10k bucket_unified，非当前 commit 历史结果 |
| v19 checkpoint-500 singleaux | 13/16 | 55/95 | 仅保留首个 aux，明显低于 multiaux，非当前 commit（`5b167cf2`） |
| **v19 checkpoint-500 multiaux（当前 commit）** | **14/16** | **65/95** | `select_balanced` 10k，最新完整补跑 |
| v19 checkpoint-500 multiaux（历史最佳 run） | 14/16 | 66/95 | 非当前 commit / 旧 run 的 merged 最佳结果 |

**与 pre-GRPO multiaux 对比（62/95 → 65/95，当前 commit）**：
- v19 新增（+6）：至少包含 `imo_sl_1999_g6`、`imo_sl_2002_g7_variant`、`imo_sl_2008_g1b`、`imo_sl_2009_g3`、`imo_sl_2009_g6`、`imo_sl_2016_g5_variant`
- v19 回退：相对历史最佳 `66/95` 少解 1 题
- 净变化：`+3`

**关键分析结论**：
- v19 的主收益来自 **multiaux 搜索**，不是单 aux 本身；singleaux 对照只做到 `13/16` 和 `55/95`
- 在当前 commit 的最新完整补跑里，`dev_imo` 保持 `14/16`，`imo_95` 达到 `65/95`，依然明显优于 pre-GRPO multiaux 的 `62/95`
- 历史上同配置曾跑到 `66/95`，说明当前结论稳定成立，但 `imo_95` headline 会有小幅 run-to-run 波动

**结论**：
- v19 是当前最值得保留的 multiaux 主线：以当前 commit 计，`dev_imo 14/16`、`imo_95 65/95`，明显优于 pre-GRPO、v17 和 v18
- singleaux 结果显著低于 multiaux，后续比较与回归时应继续把 multiaux 作为主汇报口径
- 旧 commit 的 `66/95` 应作为历史最佳 run 记录，而不是覆盖当前 commit 的主结果

---

### v18 (2026-04-27~29) - 已归档（未优于 v17）

**数据集**：`datasets/grpo_geometry100k_vlm_label_20260421_maxaux8_bucket_unified_10k_v18`

**模型训练目录**：`models/grpo_vlm_sft44_geometry100k_v18_s1_4gpu_lr5e6`

**核心变更**：在 v17 基础上将训练集从 5k 扩大到 10k，500 步覆盖约 1.6 epoch（v17 为 3.2 epoch）

**数据集静态指标**：
- `selected_rows = 10000`，`zero_pass_ratio = 0.1299`（优于 5k 的 0.1736）
- `multi_point_shortage = 4000`（core 供给在 10k 规模下明显不足）

**Selector 参数说明**：v18 使用当前代码库的 `scripts/grpo/select_debug_set.py`（`bucket_unified`）生成数据集。参考 commit: `da70fd477dc18c4859c1c96b8014e5c954b08254`

**生成 v18 数据集的完整命令**：

```bash
python scripts/grpo/select_debug_set.py \
  datasets/grpo_geometry100k_vlm_label_20260421_maxaux8/difficulty_labels.jsonl \
  datasets/grpo_geometry100k_vlm_label_20260421_maxaux8_bucket_unified_10k_v18/grpo_train_selected_10000.jsonl \
  --report-output datasets/grpo_geometry100k_vlm_label_20260421_maxaux8_bucket_unified_10k_v18/grpo_train_report_10000.json \
  --selection-policy bucket_unified \
  --target-size 10000 \
  --core-pass-min 0.125 \
  --core-pass-max 0.625 \
  --mastered-pass-min 0.90 \
  --near-high-mid-max-pass 0.75 \
  --near-high-mid-max-fraction 0.08 \
  --mastered-max-fraction 0.0 \
  --mastered-fallback-min-fill-fraction 0.90 \
  --multi-segment-min-fraction 0.45 \
  --multi-point-min-fraction 0.40 \
  --family-min-fraction 0.10 \
  --goal-max-fraction 0.18 \
  --zero-valid-min 0.25 \
  --zero-valid-max 0.875 \
  --zero-pass-reward-std-min 0.15 \
  --reward-mixed-zero-unique-aux-min 2 \
  --reward-mixed-zero-max-fraction 0.15 \
  --near-low-min-fraction 0.05 \
  --near-low-max-fraction 0.20 \
  --reward-mixed-zero-min-fraction 0.05 \
  --near-high-mid-min-fraction 0.03 \
  --greedy-success-max-fraction 1.0 \
  --pass-one-max-fraction 1.0 \
  --high-pass-min 0.75 \
  --high-pass-max-fraction 1.0 \
  --pass-one-value 1.0
```

**验证**：按上述命令生成的数据集与现有 v18 数据集完全一致（集合和顺序都相同）。

**关键差异（v17 → v18）**：
- `--target-size 5000` → `10000`
- `--reward-mixed-zero-max-fraction 0.20` → `0.15`

**训练配置**：与 v17 完全一致
- `learning_rate = 5e-6`，`warmup_steps = 10`，`lr_scheduler_type = cosine`
- `per_device_train_batch_size = 1`，`gradient_accumulation_steps = 8`，`num_generations = 8`
- `NPROC_PER_NODE = 4`，`temperature = 1.1`，`top_p = 0.95`，`top_k = 0`，`beta = 0.02`
- `max_steps = 500`，`save_steps = 50`

**评估结果**：
- ✅ dev_imo：**14/16**（与 v17 持平，非当前 commit，run commit: `f384d7029f283c790acb9fb77a1b039511a3b750`）
- ✅ imo_95：**55/95**（低于 v17 的 59/95，-4 题；非当前 commit，run commit: `f384d7029f283c790acb9fb77a1b039511a3b750`）
- 评估设置：`agent=vlm`，`search_version=v1`，`decoding_size=32`，`beam_size=512`，`search_depth=4`，`num_gpus_for_eval=4`，`gpu_batch_size=2`
- 评估产物：`results/v18_lr5e6_checkpoint500_vlm/`
  - dev_imo CSV：`results/v18_lr5e6_checkpoint500_vlm/eval_single_problem_multi_gpu_vlm_dev_imo_v0-20260427-200556_checkpoint-500_sv1_d32_b512_s4_gbs2_gbt100_seed123_20260428T000747Z.csv`
  - imo_95 CSV：`results/v18_lr5e6_checkpoint500_vlm/eval_single_problem_multi_gpu_vlm_imo_95_v0-20260427-200556_checkpoint-500_sv1_d32_b512_s4_gbs2_gbt100_seed123_20260428T012443Z.csv`
  - imo_95 合并 CSV：`results/v18_lr5e6_checkpoint500_vlm/imo_95_v18_checkpoint500_merged.csv`

**对比基线**：

| 版本 | dev_imo | imo_95 | 备注 |
|------|---------|--------|------|
| SFT baseline | 14/16 | - | pre-GRPO，非当前 commit |
| v16 checkpoint-500 | 14/16 | 55/95 | lr=5e-6，2k 数据集，8 epoch，非当前 commit（`a5482b00`） |
| **v17 checkpoint-500** | **14/16** | **59/95** | lr=5e-6，5k 数据集，3.2 epoch，非当前 commit 历史结果（dev: `497d6aaf` / imo95: `e577945a`） |
| v18 checkpoint-500 | 14/16 | 55/95 | lr=5e-6，10k 数据集，1.6 epoch，非当前 commit（`f384d702`） |

**imo_95 逐题对比（v17 → v18）**：
- v18 回退（-4）：`imo_sl_2002_g7_variant`、`imo_sl_2009_g8`、`imo_sl_2013_g2`、`imo_sl_2020_g6`
- v18 新增（+0）：无
- 净变化：-4 题

**失败原因分析（基于 imo_sl_2020_g6 单题 trace 对比）**：
- v18 在 depth0 未生成 v17 解题路径的关键第一步构造（`l = on_line l a b, on_line l c d`）
- v18 在 depth2 每节点 unique 候选数显著更多（31.9 vs 17.5），重复率从 45% 降至 0.2%
- v18 搜索更"发散"但关键构造的概率质量下降，导致解题路径断裂
- 根本原因：10k 数据集（1.6 epoch）相比 5k（3.2 epoch）重复率更低，但模型对关键构造的集中度也随之下降

**结论**：
- 扩大数据集到 10k 并不带来进一步提升，反而因 epoch 数减少（3.2 → 1.6）导致模型对关键构造的学习不充分
- 当时结论是 v17（5k，3.2 epoch）仍优于 v18；后续已被 v19 multiaux 超过
- 下一步应探索：在保持 3.2 epoch 的前提下扩大数据集，或改善 10k 数据集的质量（降低 multi_point_shortage）

---

### v17 (2026-04-23) - 曾经最优（已被 v19 multiaux 超过）

**数据集**：`datasets/grpo_geometry100k_vlm_label_20260421_maxaux8_bucket_unified_5k_v17`

**模型训练目录**：`models/grpo_vlm_sft44_geometry100k_v17_s1_4gpu_lr5e6`

**核心变更**：在 v16 基础上将训练集从 2k 扩大到 5k，effective batch size 不变（32 problems/step），500 步覆盖约 3.2 epoch（v16 为 8 epoch）

**数据集静态指标**：
- `selected_rows = 5000`，`fallback_triggered = false`
- `selected_zero_pass_ratio = 0.1736`（v16: 0.05，因 reward_mixed_zero 配额按比例扩大）
- `selected_avg_proxy_reward_std = 0.3607`，`selected_median_proxy_reward_std = 0.3476`
- `multi_point_shortage = 573`（core 供给在 5k 规模下接近上限）

**Selector 参数说明**：v17 使用当前代码库的 `scripts/grpo/select_debug_set.py`（`bucket_unified`）生成数据集。参考 commit: `da70fd477dc18c4859c1c96b8014e5c954b08254`

**生成 v17 数据集的完整命令**：

```bash
python scripts/grpo/select_debug_set.py \
  datasets/grpo_geometry100k_vlm_label_20260421_maxaux8/difficulty_labels.jsonl \
  datasets/grpo_geometry100k_vlm_label_20260421_maxaux8_bucket_unified_5k_v17/grpo_train_selected_5000.jsonl \
  --report-output datasets/grpo_geometry100k_vlm_label_20260421_maxaux8_bucket_unified_5k_v17/grpo_train_report_5000.json \
  --selection-policy bucket_unified \
  --target-size 5000 \
  --core-pass-min 0.125 \
  --core-pass-max 0.625 \
  --mastered-pass-min 0.90 \
  --near-high-mid-max-pass 0.75 \
  --near-high-mid-max-fraction 0.08 \
  --mastered-max-fraction 0.0 \
  --mastered-fallback-min-fill-fraction 0.90 \
  --multi-segment-min-fraction 0.45 \
  --multi-point-min-fraction 0.40 \
  --family-min-fraction 0.10 \
  --goal-max-fraction 0.18 \
  --zero-valid-min 0.25 \
  --zero-valid-max 0.875 \
  --zero-pass-reward-std-min 0.15 \
  --reward-mixed-zero-unique-aux-min 2 \
  --reward-mixed-zero-max-fraction 0.20 \
  --near-low-min-fraction 0.05 \
  --near-low-max-fraction 0.20 \
  --reward-mixed-zero-min-fraction 0.05 \
  --near-high-mid-min-fraction 0.03 \
  --greedy-success-max-fraction 1.0 \
  --pass-one-max-fraction 1.0 \
  --high-pass-min 0.75 \
  --high-pass-max-fraction 1.0 \
  --pass-one-value 1.0
```

**验证**：按上述命令生成的数据集与现有 v17 数据集完全一致（集合和顺序都相同）。

**训练配置**：与 v16 完全一致
- `learning_rate = 5e-6`，`warmup_steps = 10`，`lr_scheduler_type = cosine`
- `per_device_train_batch_size = 1`，`gradient_accumulation_steps = 8`，`num_generations = 8`
- `NPROC_PER_NODE = 4`，`temperature = 1.1`，`top_p = 0.95`，`top_k = 0`，`beta = 0.02`
- `max_steps = 500`，`save_steps = 50`

**训练进度**：
- ✅ 500-step 训练：**已完成**（2026-04-23）
- 全程 `avg_zero_std = 0.1248`，`median_reward_std = 0.3415`，`max_consecutive_zero = 0`
- 前 50 步：`avg_zero_std = 0.0778`，`median_reward_std = 0.3569`（smoke gate 全部通过）
- 优于 v16 全程指标（avg_zero_std: 0.1670 → 0.1248，降低 25%）

**评估结果**：
- ✅ dev_imo：**14/16**（与 v16 和 SFT baseline 持平；非当前 commit，run commit: `497d6aaf46fa996c41ba95f6c64ac33d392a579a`）
- ✅ imo_95：**59/95**（94 题完成，1 题未完成，优于 v16 的 55/95；非当前 commit，run commit: `e577945a27a86a7038ed57b7c9039eab55f8d3e9`）
- ✅ checkpoint-300 验证：dev_imo **13/16**（低于 checkpoint-500，确认 500 步是最优点；非当前 commit 历史结果）
- 评估设置：`agent=vlm`，`search_version=v1`，`decoding_size=32`，`beam_size=512`，`search_depth=4`，`num_gpus_for_eval=4`，`gpu_batch_size=2`
- 评估产物：`results/v17_lr5e6_checkpoint500_vlm/`
  - dev_imo CSV：`results/v17_lr5e6_checkpoint500_vlm/eval_single_problem_multi_gpu_vlm_dev_imo_v0-20260423-165556_checkpoint-500_sv1_d32_b512_s4_gbs2_gbt100_seed123_20260423T112909Z.csv`
  - imo_95 初始 CSV：`results/v17_lr5e6_checkpoint500_vlm/eval_single_problem_multi_gpu_vlm_imo_95_v0-20260423-165556_checkpoint-500_sv1_d32_b512_s4_gbs2_gbt100_seed123_20260424T040027Z.csv`
  - imo_95 resume CSV：`results/v17_lr5e6_checkpoint500_vlm/eval_single_problem_multi_gpu_vlm_imo_95_resume_v17_checkpoint500_v0-20260423-165556_checkpoint-500_sv1_d32_b512_s4_gbs2_gbt100_seed123_20260424T043041Z.csv`
  - imo_95 partial CSV：`results/v17_lr5e6_checkpoint500_vlm/imo95_partial_recovered.csv`
  - imo_95 合并 CSV：`results/v17_lr5e6_checkpoint500_vlm/imo_95_v17_checkpoint500_merged.csv`

**主评估结果（`qwen3_vl_text` multiaux，当前 commit）**：
- ✅ dev_imo：**14/16**
  - `results/v17_lr5e6_checkpoint500_qwen3_vl_text_multiaux/eval_single_problem_multi_gpu_qwen3_vl_text_dev_imo_v0-20260423-165556_checkpoint-500_sv1_auxfull_d32_b512_s4_gbs2_gbt100_seed123_20260514T030032Z.csv`
- ✅ imo_95：**61/95**
  - `results/v17_lr5e6_checkpoint500_qwen3_vl_text_multiaux/eval_single_problem_multi_gpu_qwen3_vl_text_imo_95_v0-20260423-165556_checkpoint-500_sv1_auxfull_d32_b512_s4_gbs2_gbt100_seed123_20260514T043538Z.csv`
- 说明：
  - 这组结果使用与 v19 相同的 `qwen3_vl_text` multiaux 评估链路，便于直接比较

**历史结果（旧 commit / 旧 run）**：
- `vlm` 链路：dev_imo **14/16**，imo_95 **59/95**（均为非当前 commit；dev run commit: `497d6aaf46fa996c41ba95f6c64ac33d392a579a`，imo95 run commit: `e577945a27a86a7038ed57b7c9039eab55f8d3e9`）
- `results/v17_lr5e6_checkpoint500_vlm/imo_95_v17_checkpoint500_merged.csv`
- 2026-05-12 的那次 `imo_95` auxfull run 只产出 `1/95`，明显是异常/中断产物，不作为正式结论

**对比基线**：

| 版本 | dev_imo | imo_95 | 备注 |
|------|---------|--------|------|
| SFT baseline | 14/16 | - | pre-GRPO，非当前 commit |
| GRPO505 sv1 | 13/16 | - | 历史最佳 GRPO |
| v14 checkpoint-500 | 12/16 | - | lr=1e-4，后期退化 |
| v16 checkpoint-500 | 14/16 | 55/95 | lr=5e-6，2k 数据集，8 epoch，非当前 commit（`a5482b00`） |
| **v17 checkpoint-500 (`qwen3_vl_text` multiaux)** | **14/16** | **61/95** | 当前 commit，和 v19 使用同一评估链路 |
| v17 checkpoint-500 (`vlm` 历史结果) | 14/16 | 59/95 | lr=5e-6，5k 数据集，3.2 epoch，非当前 commit / 旧评估链路 |

**结论**：
- v17 是首个在 5k 数据集（3.2 epoch）上保持稳定的 GRPO 版本
- 训练指标优于 v16（avg_zero_std: 0.1670 → 0.1248，降低 25%）
- 以当前 commit 的 `qwen3_vl_text` multiaux 结果计，v17 达到 `dev_imo 14/16`、`imo_95 61/95`
- 扩大数据集、降低重复率（8 epoch → 3.2 epoch）对 GRPO 训练和评估都有益，但 v17 已被 v19 的当前 commit 结果 `65/95` 明确超过

**v17 深度分析（2026-04-27）**：

*训练稳定性对比（v16 vs v17）*：

| 区间 | v16 avg_zero_std | v17 avg_zero_std | 改善 |
|------|------------------|------------------|------|
| 1-50 | 0.0875 | 0.0778 | -11.1% |
| 1-170 | 0.1004 | 0.0909 | -9.5% |
| 171-300 | 0.1865 | 0.1231 | -34.0% |
| 301-500 | 0.2073 | 0.1518 | -26.8% |
| **全程 (1-500)** | **0.1653** | **0.1236** | **-25.2%** |

- v17 在所有训练阶段都优于 v16，尤其是后期（171-500）改善显著
- 两个版本都无 `max_consecutive_full_zero` 步数，训练全程稳定

*评估结果详细对比*：

| 版本 | dev_imo | imo_95 | 与 SFT baseline 对比 | 与 GRPO505 sv1 对比 |
|------|---------|--------|---------------------|-------------------|
| SFT baseline | 14/16 | - | - | +1 题 |
| GRPO505 sv1 | 13/16 | - | -1 题 | - |
| v16 | 14/16 | 55/95 | 持平 | +1 题 |
| **v17** | **14/16** | **59/95** | **持平** | **+1 题** |

*imo_95 新增解题（v16 → v17）*：
- ✅ `imo_sl_2002_g7_variant`
- ✅ `imo_sl_2009_g8`
- ✅ `imo_sl_2013_g2`
- ✅ `imo_sl_2020_g6`
- 无回退题

*Proposal 分布分析（dev_imo 14 题）*：

| 指标 | GRPO505 sv1 | v16 | v17 | v17 vs v16 |
|------|-------------|-----|-----|-----------|
| mean_unique_ratio | 0.3209 | 0.3739 | 0.3860 | +3.2% |
| mean_top1_share | 0.0216 | 0.0258 | 0.0306 | +18.6% |
| mean_effective_ratio | 0.2621 | 0.3174 | 0.3238 | +2.0% |

构造家族分布：

| 家族 | GRPO505 sv1 | v16 | v17 | v17 vs v16 |
|------|-------------|-----|-----|-----------|
| on_circum | 58.13% | 32.11% | 33.56% | +1.45% |
| on_circle | 26.20% | 22.93% | 22.61% | -0.32% |
| on_line | 10.37% | 21.18% | 21.06% | -0.12% |
| on_tline | 0.37% | 13.44% | 12.58% | -0.86% |
| on_bline | 2.91% | 6.19% | 5.37% | -0.82% |

**关键发现**：
1. **训练稳定性显著提升**：v17 的 avg_zero_std 全程降低 25%，后期（301-500）降低 27%
2. **评估性能稳步提升**：dev_imo 持平 SFT baseline，imo_95 净增 4 题无回退
3. **Proposal 分布健康**：
   - v17 相比 v16 略有改善（unique_ratio +3.2%）
   - 构造家族分布与 v16 基本一致，无明显 proposal shift
   - 相比 GRPO505 sv1 的严重 on_circum 偏移（58%），v16/v17 的分布更加平衡（~33%）
4. **数据集规模效应验证**：5k 数据集（3.2 epoch）优于 2k 数据集（8 epoch），降低重复率对训练和评估都有益

**下一步**：
- ✅ 已验证 checkpoint-300（13/16）低于 checkpoint-500（14/16），确认 500 步是最优点
- ✅ 已完成 v18（10k）训练与评估，结论见上节（未优于 v17）

---

### v16 (2026-04-22~23) - 已归档

**数据集**：`datasets/grpo_geometry100k_vlm_label_20260421_maxaux8_bucket_unified_2k`（与 v14/v15 相同）

**模型训练目录**：`models/grpo_vlm_sft44_geometry100k_maxaux8_v16_s1_4gpu_lr5e6`

**核心变更**：在 v15 基础上切换为 4 卡 DDP（`NPROC_PER_NODE=4`），effective batch size 从 8 扩大到 32 problems/step

**训练配置**：
- `learning_rate = 5e-6`，`warmup_steps = 10`，`lr_scheduler_type = cosine`
- `per_device_train_batch_size = 1`，`gradient_accumulation_steps = 8`，`num_generations = 8`
- `temperature = 1.1`，`top_p = 0.95`，`top_k = 0`，`beta = 0.02`，`max_completion_length = 256`
- `max_steps = 500`，`save_steps = 50`

**训练进度**：
- ✅ 500-step 训练：**已完成**
- 全程 `avg_zero_std = 0.1670`，`median_reward_std = 0.3480`，`max_consecutive_zero = 0`
- 前 50 步：`avg_zero_std = 0.1202`，`median_reward_std = 0.3759`（smoke gate 全部通过）
- 无后期崩溃，完全避免了 v14 的 301-500 退化（v14 同阶段 `avg_zero_std = 0.57`）

**评估结果**：
- ✅ dev_imo：**14/16**（与 SFT baseline 持平，优于 v14 的 12/16；非当前 commit，run commit: `a5482b00ad8b8f5623b3c48166415490303ae7a7`）
- ✅ imo_95：**55/95**（94 题完成，1 题因 Ray 崩溃未完成；非当前 commit，run commit: `a5482b00ad8b8f5623b3c48166415490303ae7a7`）
- 评估设置：`agent=vlm`，`search_version=v1`，`decoding_size=32`，`beam_size=512`，`search_depth=4`，`num_gpus_for_eval=4`，`gpu_batch_size=2`
- 评估产物：`results/v16_lr5e6_checkpoint500_vlm/`
  - dev_imo CSV：`results/v16_lr5e6_checkpoint500_vlm/eval_single_problem_multi_gpu_vlm_dev_imo_v0-20260422-154539_checkpoint-500_sv1_d32_b512_s4_gbs2_gbt100_seed123_20260422T134636Z.csv`
  - imo_95 partial CSV：`results/v16_lr5e6_checkpoint500_vlm/imo95_partial_recovered.csv`
  - imo_95 first8 CSV：`results/v16_lr5e6_checkpoint500_vlm/imo95_first8_recovered.csv`
  - imo_95 合并 CSV：`results/v16_lr5e6_checkpoint500_vlm/imo_95_v16_checkpoint500_merged.csv`

**对比基线**：

| 版本 | dev_imo | imo_95 | 备注 |
|------|---------|--------|------|
| SFT baseline | 14/16 | - | pre-GRPO，非当前 commit |
| GRPO505 sv1 | 13/16 | - | 历史最佳 GRPO |
| v14 checkpoint-500 | 12/16 | - | lr=1e-4，后期退化 |
| **v16 checkpoint-500** | **14/16** | **55/95** | lr=5e-6，4卡，首个稳定主线，非当前 commit（`a5482b00`） |

**结论**：
- v16 是首个在 500-step 全程保持稳定且 dev_imo 不低于 SFT baseline 的 GRPO 版本
- 学习率从 1e-4 降至 5e-6 是关键改进，4 卡 DDP 进一步稳定了 reward variance

---

### v15 (2026-04-22) - 已归档

**数据集**：`datasets/grpo_geometry100k_vlm_label_20260421_maxaux8_bucket_unified_2k`（与 v14 相同）

**模型训练目录**：`models/grpo_vlm_sft44_geometry100k_maxaux8_bucket_unified_s1_4gpu_lr5e6`

**核心变更**：学习率从 `1e-4` 降至 `5e-6`，添加 `warmup_steps=10`，单卡

**训练进度**：
- ✅ 50-step smoke gate：**通过** (`avg_zero_std = 0.0682`, `median_reward_std = 0.3730`)
- 仅跑 50 步，作为 lr 调参验证，后续由 v16（4 卡）接替

---

### v14 (2026-04-22) - 已归档

**数据集**：`datasets/grpo_geometry100k_vlm_label_20260421_maxaux8_bucket_unified_2k`

**模型训练目录**：`models/grpo_vlm_sft44_geometry100k_maxaux8_bucket_unified_s1_4gpu_tuned`

**训练进度**：
- ✅ 50-step smoke gate：**通过** (`avg_zero_std = 0.2659`)
- ⚠️ 170-step mid gate：**部分通过** (`last50_avg_zero_std = 0.36`，略超阈值 0.35)
- ✅ 300-step 训练：**已完成**
- ✅ 500-step 训练：**已完成**
- ⚠️ dev_imo 评估：**12/16**（低于 SFT 的 14/16 和历史 GRPO505 的 13/16）

**结论**：
- 500-step 后半程（301-500）零方差占比升至 0.57，checkpoint-500 在 dev_imo 出现回退
- 根本原因：学习率 1e-4 相对 SFT 的 1e-5 偏高，导致后期策略分布偏移

---

### v13 及更早版本 - 历史归档

以下版本为早期探索，**详细记录见归档文件** `grpo_pipeline_optimization_plan_archive.md`。

#### v13 (2026-04-21)
- 数据集：`datasets/grpo_geometry100k_vlm_label_20260421_maxaux5_v10_stagebalanced_2k/`
- 50-step smoke 边缘失败（avg_zero_std = 0.4364）
- 详见归档文档的"v13（2026-04-21）：命名映射与结论"部分

#### v3-v12 早期版本
- **v3_tiered**：pass-zero 污染严重（67.85%），smoke 失败
- **v4_reward_mixed**：引入 reward_mixed_zero 过滤，规模仅 800 条
- **v5_rewardmix_2k**：扩大到 2k，但 smoke 仍未通过（avg_zero_std = 0.4375）
- **v6_mid_strict_zero**：收紧 core window，略有改善但仍未过 gate
- **v7_structure_strict_zero**：首个通过 50-step smoke gate 的版本（avg_zero_std = 0.2900）
- **v8_structure_full150k_strict_zero**：补齐 150k 标注池，早期稳定性优于 v7
- **v9_stage_balanced**：引入 stage-balanced 策略
- **v10-v12**：geometry100k 数据源上的各种 selector 实验

**详细历史演进、静态指标、smoke 结果、关键 bug audit 与 aux-fix 基础设施见归档文件** `grpo_pipeline_optimization_plan_archive_v13_and_earlier.md`。

---

## 当前 Gate

所有新的 GRPO 数据集迭代都统一采用两段式 smoke：

- 第一段：前 `50` 个 metric step 的 early gate
- 第二段：同一条 run 继续到 `170 step` 的 mid gate，用于覆盖 `v7/v8` 历史崩坏区间

early gate 固定检查：

- `first50_avg_frac_reward_zero_std <= 0.40`
- `first50_median_reward_std >= 0.20`
- `max_consecutive_full_zero_std_steps <= 3`

mid gate 固定检查：

- `first170_avg_frac_reward_zero_std <= 0.40`
- `first170_median_reward_std >= 0.15`
- `last50_avg_frac_reward_zero_std <= 0.35`
- `last50_median_reward_std >= 0.15`
- `121_170_avg_frac_reward_zero_std <= 0.35`
- `121_170_median_reward_std >= 0.15`
- `max_consecutive_full_zero_std_steps <= 3`

只有同时通过 early gate 和 mid gate 的数据集，才允许继续进入 `300-step` 训练与评估。

## 版本与文件系统路径映射

**注意**：部分版本在文档中使用新的版本号（v13、v14），但文件系统中的目录名保持不变。

| 版本 | 数据集路径 | 模型训练路径 |
|------|-----------|-------------|
| v13 | `datasets/grpo_geometry100k_vlm_label_20260421_maxaux5_v10_stagebalanced_2k/` | `models/grpo_vlm_sft44_geometry100k_v10_stagebalanced_s1_4gpu_tuned/` |
| v14 | `datasets/grpo_geometry100k_vlm_label_20260421_maxaux8_bucket_unified_2k/` | `models/grpo_vlm_sft44_geometry100k_maxaux8_bucket_unified_s1_4gpu_tuned/` |
| v15 | `datasets/grpo_geometry100k_vlm_label_20260421_maxaux8_bucket_unified_2k/` | `models/grpo_vlm_sft44_geometry100k_maxaux8_bucket_unified_s1_4gpu_lr5e6/` |
| v16 | `datasets/grpo_geometry100k_vlm_label_20260421_maxaux8_bucket_unified_2k/` | `models/grpo_vlm_sft44_geometry100k_maxaux8_v16_s1_4gpu_lr5e6/` |
| v17 | `datasets/grpo_geometry100k_vlm_label_20260421_maxaux8_bucket_unified_5k_v17/` | `models/grpo_vlm_sft44_geometry100k_v17_s1_4gpu_lr5e6/` |
| v18 | `datasets/grpo_geometry100k_vlm_label_20260421_maxaux8_bucket_unified_10k_v18/` | `models/grpo_vlm_sft44_geometry100k_v18_s1_4gpu_lr5e6/` |
| v19 | `datasets/maxaux8/20260429/geometry_clauses10_samples1M_select_balanced_10k.jsonl` | `models/grpo_vlm_sft44_geometry100k_v19_s1_4gpu_lr5e6/` |
| v20 | `datasets/maxaux8/20260429/geometry_clauses10_samples1M_select_balanced_10k.jsonl` | `models/grpo_vlm_sft44_geometry100k_v20_s1_4gpu_dapo_batchseq/` |
| v21 | `datasets/maxaux8/20260429/geometry_clauses10_samples1M_select_balanced_10k.jsonl` | `models/grpo_vlm_sft44_geometry100k_v21_s1_4gpu_drgrpo_batchseq/` |
| v22 | `datasets/maxaux8/20260429/geometry_clauses10_samples1M_select_balanced_10k.jsonl` | `models/grpo_vlm_sft44_geometry100k_v22_s1_4gpu_drgrpo_groupseq/` |
| v23 | `datasets/maxaux8/20260429/geometry_clauses10_samples1M_select_balanced_10k.jsonl` | `models/grpo_vlm_sft44_geometry100k_v23_s1_4gpu_drgrpo_grouptoken/` |
| v24 | `datasets/maxaux8/20260429/geometry_clauses10_samples1M_select_balanced_10k.jsonl` | `models/grpo_vlm_sft44_geometry100k_v24_s1_4gpu_grpo_grouptoken/` |
| v25 | `datasets/maxaux8/20260429/geometry_clauses10_samples1M_select_balanced_10k.jsonl` | `models/grpo_vlm_sft44_geometry100k_v25_s1_4gpu_dapo_grouptoken/` |

**版本说明**：
- **v13**：原称"v10 复跑"，使用 v10_auxfix_stage_balanced selector 在 geometry100k maxaux5 数据源上的实验，50-step smoke 边缘失败（avg_zero_std = 0.4364）
- **v14**：原称"maxaux8"，使用 bucket_unified selector 在 geometry100k maxaux8 数据源上的实验，首次通过 50-step smoke gate（avg_zero_std = 0.2659），但 500-step 后期退化，dev_imo 回退至 12/16
- **v15**：与 v14 相同数据集，将学习率从 1e-4 降至 5e-6 并添加 warmup，50-step smoke gate 大幅改善（avg_zero_std = 0.0682），仅跑 50 步作为调参验证
- **v16**：与 v15 相同配置，切换为 4 卡 DDP，500-step 全程稳定，dev_imo 14/16，imo_95 55/95（非当前 commit，评估 run commit: `a5482b00`）
- **v17**：与 v16 相同配置，训练集从 2k 扩大到 5k（约 3.2 epoch），前 50 步 avg_zero_std = 0.0778（优于 v16）；旧 `vlm` 链路结果为 59/95（非当前 commit，dev: `497d6aaf` / imo95: `e577945a`），当前 commit 的 `qwen3_vl_text` multiaux 补跑为 61/95
- **v18**：将 bucket_unified 训练集从 5k 扩大到 10k，但 500 步只覆盖约 1.6 epoch，dev_imo 持平、imo_95 回退至 55/95（非当前 commit，评估 run commit: `f384d702`）
- **v19**：切换到 `select_balanced` 10k 数据集，当前 commit 的 `qwen3_vl_text` multiaux 主结果为 `dev_imo 14/16`、`imo_95 65/95`；历史最佳旧 run 为 66/95（非当前 commit）
- **v20**：在 `v19` 数据集上首测 `dapo + batch + sequence`，`dev_imo 14/16` 但 `imo95_score_diff_11` 修正后仅 `5/11`
- **v21**：只把 `loss_type` 从 `dapo` 回到 `dr_grpo`，11 题修正后回升到 `6/11`
- **v22**：只把 `scale_rewards` 从 `batch` 回到 `group`，11 题修正后升到 `8/11`，是当前短推理最好口径之一
- **v23**：只把 `importance_sampling_level` 从 `sequence` 改回 `token`，11 题修正后回落到 `6/11`
- **v24**：只把 `loss_type` 从 `dr_grpo` 改成 `grpo`，11 题修正后达到 `8/11`，与 `v22` 并列最好
- **v25**：目录名虽为 `dapo_grouptoken`，但实际参数与 `v20` 相同，属于 `dapo + batch + sequence` 的复跑；修正后仍为 `5/11`
