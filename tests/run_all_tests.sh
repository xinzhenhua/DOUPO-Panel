#!/bin/bash
# ============================================================================
# run_all_tests.sh — 一键运行全部前端JS测试
# 用法：cd tests && ./run_all_tests.sh
# 依赖：Node.js（不需要npm install任何东西，纯用Node内置能力）
# ============================================================================
set -e
cd "$(dirname "$0")"

TOTAL_TESTS=0
FAIL_FILES=0
FAILED_NAMES=()

echo "========================================"
echo "  豆粕基本面仪表盘 · 前端测试套件"
echo "========================================"
echo ""

for f in test_*.js; do
  if [ "$f" = "test_helpers.js" ]; then continue; fi
  echo "── $f ──────────────────────────"
  OUTPUT=$(node "$f" 2>&1)
  EXIT_CODE=$?
  echo "$OUTPUT" | tail -3
  echo ""
  N=$(echo "$OUTPUT" | grep -oP '(?<=结果：)\d+(?=项通过)' | tail -1)
  if [ $EXIT_CODE -ne 0 ]; then
    FAIL_FILES=$((FAIL_FILES+1))
    FAILED_NAMES+=("$f")
    echo "❌ $f 执行失败(非测试断言失败，是脚本本身报错，见上方详情)"
    echo ""
  elif [ -n "$N" ]; then
    TOTAL_TESTS=$((TOTAL_TESTS+N))
  fi
done

echo "========================================"
echo "  汇总：共 $TOTAL_TESTS 项测试通过"
if [ $FAIL_FILES -eq 0 ]; then
  echo "  ✅ 全部 $(ls test_*.js | grep -v test_helpers | wc -l) 个测试文件均正常运行"
else
  echo "  ❌ 有 $FAIL_FILES 个测试文件执行失败："
  for name in "${FAILED_NAMES[@]}"; do echo "     - $name"; done
  exit 1
fi
echo "========================================"
