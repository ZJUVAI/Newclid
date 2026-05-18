# v19-v25 实验与效果临时总结

更新时间：`2026-05-18`

这份表只使用当前工作区里能直接核对到的脚本、CSV、日志与补测记录。
其中 `dev_imo` 和 `imo95_score_diff_11` 是这轮 `v20-v25` 对比里最一致的口径；
`v19` 当前仍没有找到单独落盘的 `imo95_score_diff_11` 汇总 CSV，所以保留它的 `imo_95` 全量结果作为主参考。

## 总表

| 版本 | 相对上一版的主要改动 | 训练关键参数 | `dev_imo` | `imo95_score_diff_11` | 当前结论 |
| --- | --- | --- | --- | --- | --- |
| `v19` | 主线基线版 | `loss_type=grpo`, `scale_rewards=group`, `importance_sampling_level=token`, `lr=5e-6`, `beta=0.02` | `14/16` | 7/11 | 当前这组实验的参考基线；全量 `imo_95=65/95` |
| `v20` | 只改结构化训练目标：切到 `dapo + batch + sequence` | `loss_type=dapo`, `scale_rewards=batch`, `importance_sampling_level=sequence` | `14/16` | 初始 `3/11`，补测修正后 `5/11` | 两道 30 多秒假失败纠正后仍明显偏弱 |
| `v21` | 从 `v20` 单因子回滚：`dapo -> dr_grpo` | `loss_type=dr_grpo`, `scale_rewards=batch`, `importance_sampling_level=sequence` | `14/16` | 初始 `5/11`，补测修正后 `6/11` | 比 `v20` 回升，但仍弱于 `v22/v24` |
| `v22` | 从 `v21` 单因子回滚：`batch -> group` | `loss_type=dr_grpo`, `scale_rewards=group`, `importance_sampling_level=sequence` | `14/16` | 初始 `4/11`，补测修正后 `8/11` | 修正后当前最好之一 |
| `v23` | 从 `v22` 单因子回滚：`sequence -> token` | `loss_type=dr_grpo`, `scale_rewards=group`, `importance_sampling_level=token` | `14/16` | 初始 `6/11`，补测后仍 `6/11` | 两道异常题补测后都是真失败；弱于 `v22/v24` |
| `v24` | 从 `v23` 单因子改动：`dr_grpo -> grpo` | `loss_type=grpo`, `scale_rewards=group`, `importance_sampling_level=token` | `14/16` | 初始 `5/11`，补测修正后 `8/11` | 与 `v22` 修正后并列当前最好；`grpo` 不弱于 `dr_grpo` |
| `v25` | 更正：实际与 `v20` 同参复跑，不是 `v24 -> dapo` 单因子 | `loss_type=dapo`, `scale_rewards=batch`, `importance_sampling_level=sequence` | `14/16` | 初始 `4/11`，补测修正后 `5/11` | 目录名/旧文档误写为 `grouptoken`；不能拿它证明 `dapo+group+token` 弱 |

## 逐版说明

### `v19`

- 作用：这轮 `v20-v25` 消融的主线基线。
- 训练脚本：[tmp/train_v19.sh](/C20545/home/wangzi/GenesisGeo-grpo/tmp/train_v19.sh)
- 已核对结果：
  - `dev_imo=14/16`
    - 证据：[dev_imo_resume_from_20260513_054215_merged.csv](/C20545/home/wangzi/GenesisGeo-grpo/results/v19_lr5e6_checkpoint500_qwen3_vl_text_multiaux/dev_imo_resume_from_20260513_054215_merged.csv)
  - `imo_95=65/95`
    - 证据：[eval_single_problem_multi_gpu_qwen3_vl_text_imo_95_v0-20260508-105855_checkpoint-500_sv1_auxfull_d32_b512_s4_gbs2_gbt100_seed123_20260513T073845Z.csv](/C20545/home/wangzi/GenesisGeo-grpo/results/v19_lr5e6_checkpoint500_qwen3_vl_text_multiaux/eval_single_problem_multi_gpu_qwen3_vl_text_imo_95_v0-20260508-105855_checkpoint-500_sv1_auxfull_d32_b512_s4_gbs2_gbt100_seed123_20260513T073845Z.csv)
- 备注：
  - 当前没有在工作区里找到 `v19` 的独立 `imo95_score_diff_11` 汇总 CSV，所以这里不硬写 11 题数。

### `v20`

- 目标：优先验证“非长推理场景下，是否值得先把目标函数改成更结构化的 `dapo + batch + sequence`”。
- 训练脚本：[tmp/train_v20.sh](/C20545/home/wangzi/GenesisGeo-grpo/tmp/train_v20.sh)
- 已核对结果：
  - `dev_imo=14/16`
    - 证据：[eval_single_problem_multi_gpu_qwen3_vl_text_dev_imo_v0-20260515-153615_checkpoint-500_sv1_auxfull_d32_b512_s4_gbs2_gbt100_seed123_20260515T182641Z.csv](/C20545/home/wangzi/GenesisGeo-grpo/results/v20_dapo_batchseq_checkpoint500_qwen3_vl_text_multiaux/eval_single_problem_multi_gpu_qwen3_vl_text_dev_imo_v0-20260515-153615_checkpoint-500_sv1_auxfull_d32_b512_s4_gbs2_gbt100_seed123_20260515T182641Z.csv)
  - 初始 `imo95_score_diff_11=3/11`
    - 证据：[eval_single_problem_multi_gpu_safe_imo95_score_diff_11_20260515T220518Z.csv](/C20545/home/wangzi/GenesisGeo-grpo/results/v20_dapo_batchseq_checkpoint500_qwen3_vl_text_multiaux/eval_single_problem_multi_gpu_safe_imo95_score_diff_11_20260515T220518Z.csv)
- 但初始 11 题结果存在明显 infra 污染：
  - `2015_g5_variant=35.93s`
  - `2020_g6=31.82s`
- 补测结果：
  - `2015_g5_variant` 补测后为 `Success`
  - `2020_g6` 补测后为 `Success`
  - 证据：
    - [eval_single_problem_multi_gpu_qwen3_vl_text_0007_imo_sl_2015_g5_variant_v0-20260515-153615_checkpoint-500_sv1_auxfull_d32_b512_s4_gbs2_gbt100_seed123_20260518T022912Z.csv](/C20545/home/wangzi/GenesisGeo-grpo/results/v20_dapo_batchseq_checkpoint500_qwen3_vl_text_multiaux_infra_rerun/eval_single_problem_multi_gpu_qwen3_vl_text_0007_imo_sl_2015_g5_variant_v0-20260515-153615_checkpoint-500_sv1_auxfull_d32_b512_s4_gbs2_gbt100_seed123_20260518T022912Z.csv)
    - [eval_single_problem_multi_gpu_qwen3_vl_text_0010_imo_sl_2020_g6_v0-20260515-153615_checkpoint-500_sv1_auxfull_d32_b512_s4_gbs2_gbt100_seed123_20260518T023547Z.csv](/C20545/home/wangzi/GenesisGeo-grpo/results/v20_dapo_batchseq_checkpoint500_qwen3_vl_text_multiaux_infra_rerun/eval_single_problem_multi_gpu_qwen3_vl_text_0010_imo_sl_2020_g6_v0-20260515-153615_checkpoint-500_sv1_auxfull_d32_b512_s4_gbs2_gbt100_seed123_20260518T023547Z.csv)
- 修正后口径：
  - 两道异常题都修正为成功
  - 因而修正后当前可用口径是 `5/11`
- 结论：
  - `dev_imo` 没掉，但即使修正后也只有 `5/11`，说明这组改动不适合作为短推理主线。

### `v21`

- 目标：只把 `loss_type` 从 `dapo` 回滚到 `dr_grpo`，其他保留 `v20`。
- 训练脚本：[tmp/train_v21.sh](/C20545/home/wangzi/GenesisGeo-grpo/tmp/train_v21.sh)
- 已核对结果：
  - `dev_imo=14/16`
    - 证据：[eval_single_problem_multi_gpu_qwen3_vl_text_dev_imo_v1-20260516-042514_checkpoint-500_sv1_auxfull_d32_b512_s4_gbs2_gbt100_seed123_20260516T074742Z.csv](/C20545/home/wangzi/GenesisGeo-grpo/results/v21_drgrpo_batchseq_checkpoint500_qwen3_vl_text_multiaux/eval_single_problem_multi_gpu_qwen3_vl_text_dev_imo_v1-20260516-042514_checkpoint-500_sv1_auxfull_d32_b512_s4_gbs2_gbt100_seed123_20260516T074742Z.csv)
  - 初始 `imo95_score_diff_11=5/11`
    - 证据：[eval_single_problem_multi_gpu_safe_imo95_score_diff_11_20260516T091040Z.csv](/C20545/home/wangzi/GenesisGeo-grpo/results/v21_drgrpo_batchseq_checkpoint500_qwen3_vl_text_multiaux/eval_single_problem_multi_gpu_safe_imo95_score_diff_11_20260516T091040Z.csv)
- 但初始 11 题结果存在明显 infra 污染：
  - `2013_g2=31.78s`
  - `2020_g6=34.65s`
- 补测结果：
  - `2013_g2` 补测后为 `Success`
  - `2020_g6` 补测后仍为 `Failed`
  - 证据：
    - [eval_single_problem_multi_gpu_qwen3_vl_text_0006_imo_sl_2013_g2_v1-20260516-042514_checkpoint-500_sv1_auxfull_d32_b512_s4_gbs2_gbt100_seed123_20260518T025307Z.csv](/C20545/home/wangzi/GenesisGeo-grpo/results/v21_drgrpo_batchseq_checkpoint500_qwen3_vl_text_multiaux_infra_rerun/eval_single_problem_multi_gpu_qwen3_vl_text_0006_imo_sl_2013_g2_v1-20260516-042514_checkpoint-500_sv1_auxfull_d32_b512_s4_gbs2_gbt100_seed123_20260518T025307Z.csv)
    - [eval_single_problem_multi_gpu_qwen3_vl_text_0010_imo_sl_2020_g6_v1-20260516-042514_checkpoint-500_sv1_auxfull_d32_b512_s4_gbs2_gbt100_seed123_20260518T031659Z.csv](/C20545/home/wangzi/GenesisGeo-grpo/results/v21_drgrpo_batchseq_checkpoint500_qwen3_vl_text_multiaux_infra_rerun/eval_single_problem_multi_gpu_qwen3_vl_text_0010_imo_sl_2020_g6_v1-20260516-042514_checkpoint-500_sv1_auxfull_d32_b512_s4_gbs2_gbt100_seed123_20260518T031659Z.csv)
- 修正后口径：
  - 只新增 `2013_g2` 这一道成功
  - 因而修正后当前可用口径是 `6/11`
- 结论：
  - 相对 `v20` 明显回升，基本支持“优先不用 `dapo`”这个判断，但它仍然不如 `v22/v24`。

### `v22`

- 目标：只把 `scale_rewards` 从 `batch` 回滚到 `group`，其他保留 `v21`。
- 训练脚本：[tmp/train_v22.sh](/C20545/home/wangzi/GenesisGeo-grpo/tmp/train_v22.sh)
- 已核对结果：
  - `dev_imo=14/16`
    - 证据：[eval_single_problem_multi_gpu_qwen3_vl_text_dev_imo_v0-20260516-134720_checkpoint-500_sv1_auxfull_d32_b512_s4_gbs2_gbt100_seed123_20260516T164611Z.csv](/C20545/home/wangzi/GenesisGeo-grpo/results/v22_drgrpo_groupseq_checkpoint500_qwen3_vl_text_multiaux/eval_single_problem_multi_gpu_qwen3_vl_text_dev_imo_v0-20260516-134720_checkpoint-500_sv1_auxfull_d32_b512_s4_gbs2_gbt100_seed123_20260516T164611Z.csv)
  - 初始 `imo95_score_diff_11=4/11`
    - 证据：[eval_single_problem_multi_gpu_safe_imo95_score_diff_11_20260516T181502Z.csv](/C20545/home/wangzi/GenesisGeo-grpo/results/v22_drgrpo_groupseq_checkpoint500_qwen3_vl_text_multiaux/eval_single_problem_multi_gpu_safe_imo95_score_diff_11_20260516T181502Z.csv)
- 但初始 11 题结果存在明显 infra 污染：
  - 多题是约 `34s` 的异常快速失败。
  - 之后补测发现真实结果分别为：
    - `1999_g6 Success`
    - `2002_g7_variant Failed`
    - `2009_g6 Success`
    - `2013_g2 Failed`
    - `2015_g5_variant Success`
    - `2020_g6 Success`
  - 证据：[tmp/run_v22_v23_infra_rerun.log](/C20545/home/wangzi/GenesisGeo-grpo/tmp/run_v22_v23_infra_rerun.log)
- 修正后口径：
  - 初始安全跑中未受 infra 影响的题有 `4` 道成功：`2008_g1b`、`2009_g6_variant`、`2016_g5_variant`、`2017_g4`
  - 补测 6 道里又新增 `4` 道成功：`1999_g6`、`2009_g6`、`2015_g5_variant`、`2020_g6`
  - 因而修正后当前可用口径是 `8/11`
- 结论：
  - 一旦去掉 infra 污染，`v22` 是目前这组消融里最强的已补完版本之一。

### `v23`

- 目标：只把 `importance_sampling_level` 从 `sequence` 回滚到 `token`，其他保留 `v22`。
- 训练脚本：[tmp/train_v23.sh](/C20545/home/wangzi/GenesisGeo-grpo/tmp/train_v23.sh)
- 已核对结果：
  - `dev_imo=14/16`
    - 证据：[eval_single_problem_multi_gpu_qwen3_vl_text_dev_imo_v0-20260516-195040_checkpoint-500_sv1_auxfull_d32_b512_s4_gbs2_gbt100_seed123_20260516T224915Z.csv](/C20545/home/wangzi/GenesisGeo-grpo/results/v23_drgrpo_grouptoken_checkpoint500_qwen3_vl_text_multiaux/eval_single_problem_multi_gpu_qwen3_vl_text_dev_imo_v0-20260516-195040_checkpoint-500_sv1_auxfull_d32_b512_s4_gbs2_gbt100_seed123_20260516T224915Z.csv)
  - 初始 `imo95_score_diff_11=6/11`
    - 证据：[eval_single_problem_multi_gpu_safe_imo95_score_diff_11_20260517T001922Z.csv](/C20545/home/wangzi/GenesisGeo-grpo/results/v23_drgrpo_grouptoken_checkpoint500_qwen3_vl_text_multiaux/eval_single_problem_multi_gpu_safe_imo95_score_diff_11_20260517T001922Z.csv)
- 但这份 `6/11` 也被 infra 污染：
  - `2002_g7_variant` 与 `2013_g2` 都是约 `34s` 的异常失败。
- 补测结果：
  - `2002_g7_variant` 补测后仍为 `Failed`
  - `2013_g2` 补测后仍为 `Failed`
  - 证据：
    - [eval_single_problem_multi_gpu_qwen3_vl_text_0001_imo_sl_2002_g7_variant_v0-20260516-195040_checkpoint-500_sv1_auxfull_d32_b512_s4_gbs2_gbt100_seed123_20260517T090913Z.csv](/C20545/home/wangzi/GenesisGeo-grpo/results/v23_drgrpo_grouptoken_checkpoint500_qwen3_vl_text_multiaux_infra_rerun/eval_single_problem_multi_gpu_qwen3_vl_text_0001_imo_sl_2002_g7_variant_v0-20260516-195040_checkpoint-500_sv1_auxfull_d32_b512_s4_gbs2_gbt100_seed123_20260517T090913Z.csv)
    - [eval_single_problem_multi_gpu_qwen3_vl_text_0006_imo_sl_2013_g2_v0-20260516-195040_checkpoint-500_sv1_auxfull_d32_b512_s4_gbs2_gbt100_seed123_20260517T093714Z.csv](/C20545/home/wangzi/GenesisGeo-grpo/results/v23_drgrpo_grouptoken_checkpoint500_qwen3_vl_text_multiaux_infra_rerun/eval_single_problem_multi_gpu_qwen3_vl_text_0006_imo_sl_2013_g2_v0-20260516-195040_checkpoint-500_sv1_auxfull_d32_b512_s4_gbs2_gbt100_seed123_20260517T093714Z.csv)
- 修正后口径：
  - 两道异常题补测后都没有新增成功题
  - 因而修正后当前可用口径仍是 `6/11`
- 结论：
  - `token` importance sampling 在这条主线上不如 `v22` 的 `sequence`，至少当前 `v23=6/11` 明显弱于 `v22/v24=8/11`。

### `v24`

- 目标：只把 `loss_type` 从 `dr_grpo` 改成 `grpo`，其他保留 `v23`。
- 训练脚本：[tmp/train_v24.sh](/C20545/home/wangzi/GenesisGeo-grpo/tmp/train_v24.sh)
- 已核对结果：
  - `dev_imo=14/16`
    - 证据：[eval_single_problem_multi_gpu_qwen3_vl_text_dev_imo_v1-20260517-035158_checkpoint-500_sv1_auxfull_d32_b512_s4_gbs2_gbt100_seed123_20260517T100147Z.csv](/C20545/home/wangzi/GenesisGeo-grpo/results/v24_grpo_grouptoken_checkpoint500_qwen3_vl_text_multiaux/eval_single_problem_multi_gpu_qwen3_vl_text_dev_imo_v1-20260517-035158_checkpoint-500_sv1_auxfull_d32_b512_s4_gbs2_gbt100_seed123_20260517T100147Z.csv)
  - 初始 `imo95_score_diff_11=5/11`
    - 证据：[eval_single_problem_multi_gpu_safe_imo95_score_diff_11_20260517T111956Z.csv](/C20545/home/wangzi/GenesisGeo-grpo/results/v24_grpo_grouptoken_checkpoint500_qwen3_vl_text_multiaux/eval_single_problem_multi_gpu_safe_imo95_score_diff_11_20260517T111956Z.csv)
- 但初始 11 题结果存在明显 infra 污染：
  - `2009_g6`、`2013_g2`、`2015_g5_variant`、`2020_g6` 都是约 `35s` 的异常快速失败。
  - 之后补测发现真实结果分别为：
    - `2009_g6 Success`
    - `2013_g2 Failed`
    - `2015_g5_variant Success`
    - `2020_g6 Success`
  - 证据：[results/v24_grpo_grouptoken_checkpoint500_qwen3_vl_text_multiaux_infra_rerun_fixed](/C20545/home/wangzi/GenesisGeo-grpo/results/v24_grpo_grouptoken_checkpoint500_qwen3_vl_text_multiaux_infra_rerun_fixed)
- 修正后口径：
  - 初始安全跑中未受 infra 影响的成功题有 `5` 道：`1999_g6`、`2008_g1b`、`2009_g6_variant`、`2016_g5_variant`、`2017_g4`
  - 补测 4 道里又新增 `3` 道成功：`2009_g6`、`2015_g5_variant`、`2020_g6`
  - 因而修正后当前可用口径是 `8/11`
- 结论：
  - `v24` 与 `v22` 修正后同为 `8/11`，说明在这条主线上 `grpo` 至少不弱于 `dr_grpo`。

### `v25`

- 错误更正（`2026-05-18`）：
  - 旧版文档曾把 `v25` 写成“在 `v24` 基础上只改 `loss_type=grpo -> dapo`”
  - 但实际 `tmp/train_v25.sh`、`train.log` 和最终 `args.json` 都显示，它跑的是 `loss_type=dapo`, `scale_rewards=batch`, `importance_sampling_level=sequence`
  - 因此 `v25` 应视为 `v20` 风格配置的复跑，不是 `dapo + group + token` 对照实验
- 训练脚本：[tmp/train_v25.sh](/C20545/home/wangzi/GenesisGeo-grpo/tmp/train_v25.sh)
- 已核对结果：
  - `dev_imo=14/16`
    - 证据：[eval_single_problem_multi_gpu_qwen3_vl_text_dev_imo_v0-20260517-170112_checkpoint-500_sv1_auxfull_d32_b512_s4_gbs2_gbt100_seed123_20260517T200141Z.csv](/C20545/home/wangzi/GenesisGeo-grpo/results/v25_dapo_grouptoken_checkpoint500_qwen3_vl_text_multiaux/eval_single_problem_multi_gpu_qwen3_vl_text_dev_imo_v0-20260517-170112_checkpoint-500_sv1_auxfull_d32_b512_s4_gbs2_gbt100_seed123_20260517T200141Z.csv)
  - 初始 `imo95_score_diff_11=4/11`
    - 证据：[eval_single_problem_multi_gpu_safe_imo95_score_diff_11_20260517T211814Z.csv](/C20545/home/wangzi/GenesisGeo-grpo/results/v25_dapo_grouptoken_checkpoint500_qwen3_vl_text_multiaux/eval_single_problem_multi_gpu_safe_imo95_score_diff_11_20260517T211814Z.csv)
- 初始 11 题结果存在一处明确 infra 污染：
  - `2016_g5_variant` 是 `34.73s` 的 Ray startup 异常失败，不是模型真实失败。
  - 补测后真实结果为 `Success`，耗时 `1208.38s`。
  - 证据：[eval_single_problem_multi_gpu_qwen3_vl_text_0008_imo_sl_2016_g5_variant_v0-20260517-170112_checkpoint-500_sv1_auxfull_d32_b512_s4_gbs2_gbt100_seed123_20260518T004421Z.csv](/C20545/home/wangzi/GenesisGeo-grpo/results/v25_dapo_grouptoken_checkpoint500_qwen3_vl_text_multiaux_infra_rerun/eval_single_problem_multi_gpu_qwen3_vl_text_0008_imo_sl_2016_g5_variant_v0-20260517-170112_checkpoint-500_sv1_auxfull_d32_b512_s4_gbs2_gbt100_seed123_20260518T004421Z.csv)
- 修正后口径：
  - 初始 `4/11` 加上补测纠正的 `2016_g5_variant`
  - 因而修正后当前可用口径是 `5/11`
- 结论：
  - `v25` 不能被解读为“`dapo + group + token` 只有 `5/11`”
  - 正确解读是：`dapo + batch + sequence` 在 `v20` 与 `v25` 两次 run 里都停在 `5/11`
  - 这强化的是 `v20` 配置偏弱的判断，而不是对 `dapo + group + token` 的判断

## 当前阶段的简短判断

1. `v20` 和 `v25` 实际上是同一组 `dapo + batch + sequence` 配置，并且都在补测修正后停在 `5/11`，说明这组配置偏弱。
2. `v21` 修正后是 `6/11`，说明把 `loss_type` 从 `dapo` 回到 `dr_grpo` 确实能回升，但这还不够。
3. `v22` 与 `v24` 都在修正 infra 后达到 `8/11`，说明 `group` reward scaling 很关键，而 `grpo` 本体并不弱。
4. `v23` 补测后仍是 `6/11`，说明把 `importance_sampling_level` 从 `sequence` 改回 `token` 并没有带来更好的最终结果。
5. 当前没有有效的 `dapo + group + token` 对照实验；当前最强口径仍是 `v22/v24=8/11`。

## 主要证据文件

- 配置脚本：
  - [tmp/train_v19.sh](/C20545/home/wangzi/GenesisGeo-grpo/tmp/train_v19.sh)
  - [tmp/train_v20.sh](/C20545/home/wangzi/GenesisGeo-grpo/tmp/train_v20.sh)
  - [tmp/train_v21.sh](/C20545/home/wangzi/GenesisGeo-grpo/tmp/train_v21.sh)
  - [tmp/train_v22.sh](/C20545/home/wangzi/GenesisGeo-grpo/tmp/train_v22.sh)
  - [tmp/train_v23.sh](/C20545/home/wangzi/GenesisGeo-grpo/tmp/train_v23.sh)
  - [tmp/train_v24.sh](/C20545/home/wangzi/GenesisGeo-grpo/tmp/train_v24.sh)
  - [tmp/train_v25.sh](/C20545/home/wangzi/GenesisGeo-grpo/tmp/train_v25.sh)
- 补测日志：
  - [tmp/run_v22_v23_infra_rerun.log](/C20545/home/wangzi/GenesisGeo-grpo/tmp/run_v22_v23_infra_rerun.log)
  - [tmp/eval_v24_after_rerun.log](/C20545/home/wangzi/GenesisGeo-grpo/tmp/eval_v24_after_rerun.log)
  - [tmp/eval_v20_infra_rerun.log](/C20545/home/wangzi/GenesisGeo-grpo/tmp/eval_v20_infra_rerun.log)
  - [tmp/eval_v21_infra_rerun.log](/C20545/home/wangzi/GenesisGeo-grpo/tmp/eval_v21_infra_rerun.log)
  - [tmp/run_v25_train_eval.log](/C20545/home/wangzi/GenesisGeo-grpo/tmp/run_v25_train_eval.log)
  - [tmp/eval_v25_infra_rerun.log](/C20545/home/wangzi/GenesisGeo-grpo/tmp/eval_v25_infra_rerun.log)
- `imo95_score_diff_11` 最终 CSV：
  - [imo95_score_diff_11_final.csv](/C20545/home/wangzi/GenesisGeo-grpo/results/v20_dapo_batchseq_checkpoint500_qwen3_vl_text_multiaux/imo95_score_diff_11_final.csv)
  - [imo95_score_diff_11_final.csv](/C20545/home/wangzi/GenesisGeo-grpo/results/v21_drgrpo_batchseq_checkpoint500_qwen3_vl_text_multiaux/imo95_score_diff_11_final.csv)
  - [imo95_score_diff_11_final.csv](/C20545/home/wangzi/GenesisGeo-grpo/results/v22_drgrpo_groupseq_checkpoint500_qwen3_vl_text_multiaux/imo95_score_diff_11_final.csv)
  - [imo95_score_diff_11_final.csv](/C20545/home/wangzi/GenesisGeo-grpo/results/v23_drgrpo_grouptoken_checkpoint500_qwen3_vl_text_multiaux/imo95_score_diff_11_final.csv)
  - [imo95_score_diff_11_final.csv](/C20545/home/wangzi/GenesisGeo-grpo/results/v24_grpo_grouptoken_checkpoint500_qwen3_vl_text_multiaux/imo95_score_diff_11_final.csv)
  - [imo95_score_diff_11_final.csv](/C20545/home/wangzi/GenesisGeo-grpo/results/v25_dapo_grouptoken_checkpoint500_qwen3_vl_text_multiaux/imo95_score_diff_11_final.csv)
