# evaluation v1/v2 search version

`scripts/evaluation.py` 现在支持：

- `--search_version v1`
- `--search_version v2`

默认值是 `v1`，用于保持当前评估行为不变。

## v1

- 每一层请求都使用当前 frontier 的 DSL 作为 `query`
- `response_prefix` 固定为 `<aux> x00`
- 行为与当前工作区原有评估一致

## v2

- `query` 固定为根问题的 DSL
- beam state 会累计历史 `<aux>` 前缀
- 下一层请求使用 `"<aux>" + aux_prefix + " x00"` 续写
- 对 VLM 来说，图像仍然使用当前 frontier 的图形渲染

## Example

```bash
python scripts/evaluation.py \
  --problems_path benchmarks/imo_2000_p6.txt \
  --model_path models/sft34/checkpoint-25750 \
  --agent lm \
  --search_version v2
```
