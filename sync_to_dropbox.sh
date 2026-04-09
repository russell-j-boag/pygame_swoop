#!/usr/bin/env bash

set -euo pipefail

repo_dir="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
repo_name="$(basename "$repo_dir")"
dropbox_path="dropbox:${repo_name}"
common_args=(
  --exclude ".DS_Store"
  --exclude ".git/**"
  --exclude ".Rproj.user/**"
  --exclude ".Rhistory"
  --exclude ".RData"
  --exclude ".Ruserdata"
  --exclude "__pycache__/**"
  --exclude "*.py[cod]"
  --exclude "output/*.csv"
  -P
)

if rclone lsf "$dropbox_path" >/dev/null 2>&1; then
  echo "Remote directory exists; running sync to $dropbox_path"
  rclone sync "$repo_dir" "$dropbox_path" "${common_args[@]}"
else
  echo "Remote directory does not exist; running copy to $dropbox_path"
  rclone copy "$repo_dir" "$dropbox_path" "${common_args[@]}"
fi
