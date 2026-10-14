#!/usr/bin/env bash
# 推送带重试（v101.55）：页面（记账、登记推送设备）和别的任务可能在本任务运行期间往同一分支提交过，
# 原来的“pull --rebase || true; push”只试一次，撞上就整次失败、这一轮抓到的数据白丢。
# 冲突时以远端为准（-X ours 在 rebase 里表示“保留上游”）：浏览器写的账户/持仓/设备登记不能被任务覆盖；
# 任务自己写的文件（latest.json、prices.json 等）只有任务在写，不会冲突。
set -u
branch="${GITHUB_REF_NAME:-main}"
for i in 1 2 3 4; do
  if ! git pull --rebase -X ours origin "$branch"; then
    git rebase --abort 2>/dev/null || true
  fi
  if git push origin "HEAD:$branch"; then exit 0; fi
  echo "push 第 $i 次失败，稍后重试"; sleep $((i * 4))
done
echo "::error::push 连续 4 次失败，这一轮的数据没有提交"; exit 1
