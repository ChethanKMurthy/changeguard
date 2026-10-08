#!/usr/bin/env bash
# Pull the latest commit on the deployed branch and rebuild on the instance (through Systems Manager).
set -euo pipefail

STACK=${STACK:-changeguard}
REGION=${AWS_REGION:-${AWS_DEFAULT_REGION:-us-east-1}}
BRANCH=${BRANCH:-main}

instance=$(aws cloudformation describe-stacks --region "$REGION" --stack-name "$STACK" \
  --query "Stacks[0].Outputs[?OutputKey=='InstanceId'].OutputValue" --output text)

command_id=$(aws ssm send-command --region "$REGION" --instance-ids "$instance" \
  --document-name AWS-RunShellScript --comment "Redeploy ChangeGuard" \
  --parameters "commands=[\"cd /opt/changeguard && git fetch --depth 1 origin $BRANCH && git reset --hard FETCH_HEAD && bash deploy/aws/start.sh\"]" \
  --timeout-seconds 3600 --query Command.CommandId --output text)

echo "Rebuilding on $instance (command $command_id). This takes a few minutes."
aws ssm wait command-executed --region "$REGION" --command-id "$command_id" --instance-id "$instance" || true
aws ssm get-command-invocation --region "$REGION" --command-id "$command_id" --instance-id "$instance" \
  --query '[Status, StandardOutputContent]' --output text | tail -5
