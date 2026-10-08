#!/usr/bin/env bash
# Delete everything the stack created (instance, disk, CloudFront distribution, role, security group).
set -euo pipefail

STACK=${STACK:-changeguard}
REGION=${AWS_REGION:-${AWS_DEFAULT_REGION:-us-east-1}}

aws cloudformation delete-stack --region "$REGION" --stack-name "$STACK"
echo "Deleting $STACK. Removing a CloudFront distribution can take 15 minutes or more."
aws cloudformation wait stack-delete-complete --region "$REGION" --stack-name "$STACK"
echo "Deleted. Nothing from this stack remains in the account."
