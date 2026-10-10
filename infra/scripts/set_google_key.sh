#!/usr/bin/env bash
# Store P2's Google API key as an SSM SecureString (CloudFormation can't create SecureStrings, so this is a script).
# The key is read from the terminal, never passed on the command line or written to git.
set -euo pipefail
read -r -s -p "Google API key: " key; echo
aws ssm put-parameter --region ap-south-1 --name /solarrooftop/google_api_key --type SecureString \
  --value "$key" --overwrite > /dev/null
echo "stored /solarrooftop/google_api_key"
