#!/usr/bin/env sh
set -eu

runtime_api_base_url="${API_BASE_URL:-}"

trimmed="$(printf '%s' "${runtime_api_base_url}" | sed 's:/*$::')"

escaped="$(printf '%s' "${trimmed}" | awk '{
  gsub(/\\/, "\\\\")
  gsub(/"/, "\\\"")
  gsub(/\r/, "\\r")
  printf "%s", $0
}')"

cat > /usr/share/nginx/html/env-config.js <<EOF
window.__APP_CONFIG__ = Object.assign(
  { API_BASE_URL: "${escaped}" },
  window.__APP_CONFIG__ || {}
)
EOF
