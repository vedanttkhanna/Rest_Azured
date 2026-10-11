#!/usr/bin/env bash
# Delete everything SolarRooftop created (run after judging). Buckets are emptied by CDK (auto_delete_objects).
set -euo pipefail
source "$(dirname "$0")/env.sh"
cd "$SOLAR_REPO/infra"

cdk destroy --all --force

echo "--- leftovers check (all should be empty) ---"
echo "SageMaker endpoints:";   aws sagemaker list-endpoints --query 'Endpoints[].EndpointName' --output text
echo "SageMaker notebooks:";   aws sagemaker list-notebook-instances --query 'NotebookInstances[].NotebookInstanceName' --output text
echo "S3 buckets:";            aws s3api list-buckets --query "Buckets[?starts_with(Name, 'solarrooftop')].Name" --output text
echo "Log groups:";            aws logs describe-log-groups --query "logGroups[?contains(logGroupName, 'Solar') || contains(logGroupName, 'solarrooftop')].logGroupName" --output text
echo "Running EC2:";           aws ec2 describe-instances --filters Name=instance-state-name,Values=running --query 'Reservations[].Instances[].InstanceId' --output text
echo "NAT gateways:";          aws ec2 describe-nat-gateways --filter Name=state,Values=available --query 'NatGateways[].NatGatewayId' --output text
echo "CDK bootstrap (CDKToolkit stack, ECR image cache) is kept; delete it in CloudFormation if the account is done."
