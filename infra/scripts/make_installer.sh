#!/usr/bin/env bash
# Promote a signed-up user to the Installer group. Usage: infra/scripts/make_installer.sh someone@example.com
# The user must sign out and in again (or refresh tokens) for the new group to appear in their JWT.
set -euo pipefail
email="${1:?usage: make_installer.sh <email>}"
pool=$(aws cloudformation describe-stacks --region ap-south-1 --stack-name SolarCore \
  --query "Stacks[0].Outputs[?OutputKey=='UserPoolId'].OutputValue" --output text)
aws cognito-idp admin-add-user-to-group --region ap-south-1 --user-pool-id "$pool" --username "$email" --group-name Installer
echo "$email is now an Installer"
