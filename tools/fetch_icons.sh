#!/usr/bin/env bash
# Download the official provider icon packages into app/static/vendor/.
#
# These icons belong to AWS, Microsoft and the CNCF. Their terms allow using them in
# architecture diagrams and training material, so we use them inside the tutor but
# don't commit them to git (app/static/vendor/ is in .gitignore). Run this script on
# any machine that builds the app.
#
# The providers publish new packages every few months. If a download fails, get the
# new link from the pages below and update the URL.
#   AWS:   https://aws.amazon.com/architecture/icons/
#   Azure: https://learn.microsoft.com/en-us/azure/architecture/icons/
set -euo pipefail

AWS_URL="https://d1.awsstatic.com/onedam/marketing-channels/website/public/shared/architecture-icon-release/Icon-package_07312026.5846e92413caa21490223536cc97f1269e44fa92.zip"
AZURE_URL="https://arch-center.azureedge.net/icons/Azure_Public_Service_Icons_V24.zip"
GCP_BASE="https://services.google.com/fh/files/misc"   # from https://cloud.google.com/icons
K8S_URL="https://raw.githubusercontent.com/cncf/artwork/main/projects/kubernetes/icon/color/kubernetes-icon-color.svg"

ROOT="$(cd "$(dirname "$0")/.." && pwd)"
DEST="$ROOT/app/static/vendor"
TMP="$(mktemp -d)"
trap 'rm -rf "$TMP"' EXIT

mkdir -p "$DEST/aws" "$DEST/azure" "$DEST/k8s"

echo "Downloading AWS icons..."
curl -fsSL -o "$TMP/aws.zip" "$AWS_URL"
# -j drops the folder structure, so every icon lands directly in vendor/aws/
unzip -q -o -j "$TMP/aws.zip" \
  'Architecture-Service-Icons_*/*/64/*.svg' \
  'Architecture-Group-Icons_*/*.svg' \
  'Resource-Icons_*/Res_General-Icons/Res_48_Dark/*.svg' \
  -d "$DEST/aws"

echo "Downloading Azure icons..."
curl -fsSL -o "$TMP/azure.zip" "$AZURE_URL"
unzip -q -o -j "$TMP/azure.zip" '*.svg' -d "$DEST/azure"

echo "Downloading Google Cloud icons..."
mkdir -p "$DEST/gcp"
for pack in core-products-icons category-icons; do
  curl -fsSL -o "$TMP/$pack.zip" "$GCP_BASE/$pack.zip"
  unzip -q -o -j "$TMP/$pack.zip" '*.svg' -d "$DEST/gcp"
done

echo "Downloading Kubernetes logo..."
curl -fsSL -o "$DEST/k8s/kubernetes-icon-color.svg" "$K8S_URL"

echo "Done: $(find "$DEST" -name '*.svg' | wc -l) icons in $DEST"
