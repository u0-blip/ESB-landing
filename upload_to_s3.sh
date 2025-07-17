#!/bin/bash

# Exit if any command fails
set -e

# --- Configuration ---
FILE_PATH="$1"
BUCKET_NAME="esb-new-landing"
S3_PATH="/"  # can be left empty ""
REGION="ap-southeast-2"

if [[ -z "$FILE_PATH" ]]; then
  echo "Usage: $0 <file-path>"
  exit 1
fi

if [[ ! -f "$FILE_PATH" ]]; then
  echo "Error: File '$FILE_PATH' does not exist."
  exit 1
fi

FILE_NAME=$(basename "$FILE_PATH")
aws s3 cp "$FILE_PATH" "s3://$BUCKET_NAME/$S3_PATH$FILE_NAME" --region "$REGION"

echo "✅ Upload complete: s3://$BUCKET_NAME/$S3_PATH$FILE_NAME"
