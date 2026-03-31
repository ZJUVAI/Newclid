# 在仓库根目录执行（或自行 cd 到对应位置）
set -euo pipefail

HEADER="src/newclid/default_configs/rules.txt"
SPLIT_SRC="datasets/extracted_rules/c10s200k/rules_folded.txt"
OUTDIR="src/newclid/default_configs/candidate_rules_c10s200k_folded"

mkdir -p "$OUTDIR"
rm -f "$OUTDIR"/rules_*.txt

# 先按每 100 行切分到临时目录
TMPDIR="$(mktemp -d)"
split -d -a 3 -l 100 --additional-suffix=.part "$SPLIT_SRC" "$TMPDIR/part_"

# 逐个生成 candidate_rules_XXX.txt：= rules.txt(头部) + 该段100行(切分片段)
i=1
for part in "$TMPDIR"/part_*.part; do
  printf -v id "%03d" "$i"
  out="$OUTDIR/rules_${id}.txt"
  cat "$HEADER" "$part" > "$out"
  i=$((i+1))
done

rm -rf "$TMPDIR"

echo "Done. Generated $((i-1)) files in $OUTDIR"
ls -1 "$OUTDIR"/rules_*.txt | head