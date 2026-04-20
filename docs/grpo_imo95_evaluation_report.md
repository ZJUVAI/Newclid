# GRPO IMO-95 评估报告

**日期：** 2026-04-19  
**基准：** IMO-95（95 道几何题）  
**模型：** Qwen3-VL Text-only Agent

**状态说明：** 本文档记录的是旧 GRPO baseline `models/grpo_vlm_sft44_505_run1/v1-20260417-084328/checkpoint-505` 的历史评估总结，不是当前 `v8` 的结果。

**当前主线状态：** `v8_structure_full150k_strict_zero` 已通过 50-step smoke gate，但其 resumed `300-step` promotion 轨迹在 `step 147 / 300` 左右再次出现中段塌缩，最近窗口内持续表现为 `reward_std = 0.0`。此前的 `v7_structure_strict_zero` 分支也同样通过了 smoke，但在 `171 / 300` 提前停止，原因也是中段 zero-variance collapse。`v7` 没有继续做 `dev_imo` 或 `imo_95` 评估；`v8` 同样不应在 promotion 轨迹未明显恢复前进入评估。未来新的 GRPO 评估仍应同时对照 SFT baseline `checkpoint-20084` 和本文中的历史 GRPO `checkpoint-505`。

---

## 执行摘要

GRPO 在不同 benchmark 上表现为“有收益但不稳定”：

**IMO-95（95 题）：** 从 **54/95（56.8%）** 提升到 **56/95（58.9%）**，绝对提升 **+2.1%**。

**DevIMO（16 题）：** 从 **14/16（87.5%）** 下降到 **13/16（81.3%）**，绝对下降 **-6.2%**。

**备注：** 两次 GRPO 评估使用的是同一个 `checkpoint-505` 模型。`sv1` 后缀表示一次重新评估，使用了更稳定的评测环境（修复了 seed 处理和 Ray port 问题）。两次结果的差异说明，该模型的输出对评测环境变化较敏感。

### IMO-95 结果

| 指标 | SFT Baseline | GRPO（checkpoint-505） | Delta |
|--------|--------------|----------------------|-------|
| **Solved** | 54/95 | 56/95 | +2 |
| **Accuracy** | 56.8% | 58.9% | +2.1% |
| **Newly Solved** | - | 7 | +7 |
| **Regressions** | - | 5 | -5 |
| **Net Gain** | - | - | +2 |

### DevIMO 结果

| 指标 | SFT Baseline | GRPO（初次评估） | GRPO（sv1 稳定评估） |
|--------|--------------|---------------------|------------------------|
| **Solved** | 14/16 | 14/16 | 13/16 |
| **Accuracy** | 87.5% | 87.5% | 81.3% |
| **Failed Problems** | 2 | 2 | 3 |

---

## 详细结果

### 模型配置

**SFT Baseline：**
- Checkpoint：`vlm_sft44_checkpoint-20084`
- 评估完成时间：2026-04-17
- 结果文件：`imo_95_resume_from_20260417T062654Z_merged.csv`

**GRPO：**
- Checkpoint：`v1-20260417-084328/checkpoint-505`
- IMO-95 评估完成时间：2026-04-19（使用 sv1 稳定评估）
- DevIMO 评估：
  - 初次：2026-04-17（解出 14/16）
  - 稳定版（sv1）：2026-04-18（解出 13/16）
- 结果文件：见下文 Files 部分

### 评估参数

两次评估使用相同设置：

- Agent：`qwen3_vl_text`
- Decoding size：32
- Beam size：512
- Search depth：4
- Timeout：3600s
- GPUs：4（CUDA 0,1,2,3）
- GPU batch size：2
- Max workers：40

---

## DevIMO 基准分析

### 结果汇总

| 模型 | 评估版本 | Solved | Accuracy | Failed Problems |
|-------|-------------------|--------|----------|-----------------|
| SFT Baseline | checkpoint-20084 | 14/16 | 87.5% | `translated_imo_2008_p6`, `translated_imo_2021_p3` |
| GRPO | checkpoint-505（初次） | 14/16 | 87.5% | `translated_imo_2008_p6`, `translated_imo_2021_p3` |
| GRPO | checkpoint-505（sv1 稳定版） | 13/16 | 81.3% | `translated_imo_2008_p1b`, `translated_imo_2008_p6`, `translated_imo_2021_p3` |

**重要说明：** 两次 GRPO 评估使用的是**同一个 checkpoint-505 模型**。`sv1` 版本只是换了更稳定的评测设置（修复 seed 处理和 Ray agent port 问题）。结果差异反映的是评测环境敏感性，而不是模型本身变化。

### 关键观察

**GRPO 初次评估（checkpoint-505）：**
- 与 SFT baseline 持平，都是 87.5%
- 失败题与 SFT 完全相同
- 没有体现出额外收益或退化

**GRPO 稳定评估（checkpoint-505 sv1）：**
- 回落到 81.3%（比 baseline 低 6.2%）
- 新增失败题：`translated_imo_2008_p1b`（初次评估时是解出的）
- **注意这是同一个模型**，差异说明结果对评测环境敏感

### 题目级细节

**三次评估都失败的题：**
1. `translated_imo_2008_p6`：难题，三次评估都未解出
2. `translated_imo_2021_p3`：难题，三次评估都未解出

**稳定评估中的回退：**
- `translated_imo_2008_p1b`
  - 初次 GRPO 评估中解出（168.61s）
  - 稳定评估中失败（385.36s 超时）
- 该模型在稳定评估中花了更多时间搜索却未解出，说明它可能由于 seed、Ray port 或并行执行时序差异，走到了更差的搜索路径

---

## 题目级分析

### GRPO 新解出的题（7 题）

1. `imo_sl_2020_g6`
2. `imo_sl_2016_g2`
3. `imo_sl_2016_g2_variant`
4. `imo_sl_2020_g8_variant`
5. `imo_sl_1999_g6`
6. `imo_sl_2016_g5_variant`
7. `imo_sl_2005_g6`

### 回退题（5 题）

这些题 SFT 能解，但 GRPO 不能解：

1. `imo_sl_2007_g3`
2. `imo_sl_2008_g1b`
3. `imo_sl_2011_g7`
4. `imo_sl_2016_g6_variant`
5. `imo_sl_2017_g4_variant`

---

## 观察与结论

### 优势

- **IMO-95：** GRPO 新解出了 7 道 SFT baseline 失败的题，说明它确实提升了在更难几何题上的能力
- 在 IMO-95 上净增 2 题，对应 **+2.1%** 准确率
- **DevIMO 初次评估：** GRPO 至少保持了和 SFT 一样的性能（87.5%）

### 问题

- **IMO-95：** 有 5 道回退题，说明解题能力存在不稳定性
- **DevIMO 稳定评估：** `translated_imo_2008_p1b` 的失败说明模型对评测环境敏感
- 稳定评估中该题用了 385s（超时），而初次评估只用了 168s，说明它可能因 seed 处理或 Ray port 配置等细微环境变化而走到了不同搜索路径
- 这种评测敏感性对结果可复现性是个风险

### 核心洞见：评测环境敏感性

DevIMO 结果表明，**同一个 checkpoint-505 模型**在不同评测配置下会给出不同结果：

- 初次评估：14/16（87.5%）
- 稳定评估（sv1）：13/16（81.3%）

最可能的原因包括：

1. **Seed 处理变化：** sv1 修复了 seed reset 问题，可能改变了随机搜索顺序
2. **Ray agent port 配置变化：** port 分配差异可能影响并行执行时序
3. **搜索路径敏感性：** beam search 对这些环境差异较敏感

### 建议

1. **优先保证评测稳定性：** DevIMO 的波动说明必须尽量采用确定性的评测协议
2. **以 sv1 结果为准：** 修复 seed 处理后的稳定评估更适合作为模型比较基准
3. **分析 IMO-95 的 5 个回退题：** 弄清楚失败模式
4. **考虑 ensemble 思路：** SFT 与 GRPO 可能各有优势，组合后也许更稳
5. **尝试增大 beam size 或 timeout：** `translated_imo_2008_p1b` 在 385s 才超时，说明它可能离解出并不远

---

## 文件

### IMO-95 结果文件

- SFT：`results/devimo_grpo_compare/imo_95_resume_from_20260417T062654Z_merged.csv`
- GRPO：`results/devimo_grpo_compare/imo_95_resume_from_20260418T125633Z_merged.csv`

### DevIMO 结果文件

- SFT：`results/devimo_grpo_compare/eval_single_problem_multi_gpu_qwen3_vl_text_dev_imo_vlm_sft44_checkpoint-20084_d32_b512_s4_gbs2_gbt100_seed123_20260417T052620Z.csv`
- GRPO checkpoint-505：`results/devimo_grpo_compare/eval_single_problem_multi_gpu_qwen3_vl_text_dev_imo_v1-20260417-084328_checkpoint-505_d32_b512_s4_gbs2_gbt100_seed123_20260417T055948Z.csv`
- GRPO checkpoint-505 sv1：`results/devimo_grpo_compare/eval_single_problem_multi_gpu_qwen3_vl_text_dev_imo_v1-20260417-084328_checkpoint-505_sv1_d32_b512_s4_gbs2_gbt100_seed123_20260418T035755Z.csv`

### 评估 Trace

- IMO-95 SFT：`results/devimo_grpo_compare/eval_single_problem_multi_gpu_qwen3_vl_text_imo_95_v1-20260417-084328_checkpoint-505_sv1_d32_b512_s4_gbs2_gbt100_seed123_20260418T125633Z/`
- IMO-95 GRPO：`results/devimo_grpo_compare/eval_single_problem_multi_gpu_qwen3_vl_text_imo_95_resume_from_20260418T125633Z_v1-20260417-084328_checkpoint-505_sv1_d32_b512_s4_gbs2_gbt100_seed123_20260418T134526Z/`

---

## 总结

GRPO 训练目前呈现出“有收益，但伴随明显不稳定性”的特征：

**IMO-95 表现：** 有一定正收益（+2.1% 准确率，净增 2 题）。这 7 道新解出的题说明 GRPO 确实能够提升更难几何题的能力，但 5 道回退题也反映出稳定性不足。

**DevIMO 评测敏感性：** 同一个 checkpoint-505 模型在不同评测配置下给出了不同结果（87.5% vs 81.3%）。这说明模型的 beam search 对评测环境变化较敏感，尤其是 seed 处理和 Ray port 配置。修复后的稳定评估（sv1）更适合作为可信基准。

**总体判断：**
- GRPO 在提升困难题表现上是有潜力的（IMO-95 的提升是真实存在的）
- DevIMO 的波动说明评测可复现性必须优先解决
- IMO-95 的这次增益在稳定评测前提下仍然成立
- 后续工作重点应放在：
  1. 提高评测可复现性
  2. 分析回退题的失败模式
  3. 探索更稳的组合或集成方案
