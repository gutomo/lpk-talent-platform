#!/usr/bin/env bash
# 本番（ACA）への seed 投入。seed ジョブを起動し、完了を待ってデモアカウント出力を表示する。
#
# 使い方:
#   scripts/seed/seed_remote.sh <resource_group> [seed_job_name]
#   値は infra/terraform で `terraform output -raw resource_group_name` / `seed_job_name`。
#   事前に az login が必要。
#
# 注意: ジョブは seed_demo.py --reset を実行する。全行を削除して架空デモデータを再投入する
# （PoC の DB は全て架空データ。CLAUDE.md の PII 方針）。デモ直前の状態リセットにも使う。
set -euo pipefail

RG="${1:?usage: seed_remote.sh <resource_group> [seed_job_name]}"
JOB="${2:-lpk-poc-seed}"

exec_name=$(az containerapp job start -g "$RG" -n "$JOB" --query name -o tsv)
echo "started execution: $exec_name"

for _ in $(seq 1 90); do
  status=$(az containerapp job execution show -g "$RG" -n "$JOB" \
    --job-execution-name "$exec_name" --query properties.status -o tsv)
  echo "seed status: $status"
  case "$status" in
    Succeeded)
      echo "--- seed output (demo accounts) ---"
      az containerapp job logs show -g "$RG" -n "$JOB" \
        --execution "$exec_name" --container seed --format text | tail -20 || true
      exit 0
      ;;
    Failed | Stopped)
      echo "seed job failed. logs:"
      az containerapp job logs show -g "$RG" -n "$JOB" \
        --execution "$exec_name" --container seed --format text | tail -40 || true
      exit 1
      ;;
  esac
  sleep 10
done

echo "seed timed out after 15 minutes"
exit 1
