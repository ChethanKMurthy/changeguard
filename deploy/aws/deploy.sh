#!/usr/bin/env bash
# Deploy ChangeGuard to AWS: one EC2 instance behind CloudFront, sized for the AWS Free plan.
#
#   deploy/aws/deploy.sh [--alert-email you@example.com] [--no-cloudfront] [--accept-paid-plan]
#
# Environment: AWS_REGION (default us-east-1), STACK (default changeguard),
# INSTANCE_TYPE (default t3.micro), REPO, BRANCH.
set -euo pipefail

STACK=${STACK:-changeguard}
REGION=${AWS_REGION:-${AWS_DEFAULT_REGION:-us-east-1}}
INSTANCE_TYPE=${INSTANCE_TYPE:-t3.micro}
REPO=${REPO:-https://github.com/ChethanKMurthy/changeguard.git}
BRANCH=${BRANCH:-main}
ALERT_EMAIL=""
CLOUDFRONT=true
ACCEPT_PAID=no

while [ $# -gt 0 ]; do
  case "$1" in
    --alert-email) ALERT_EMAIL="$2"; shift 2 ;;
    --no-cloudfront) CLOUDFRONT=false; shift ;;
    --accept-paid-plan) ACCEPT_PAID=yes; shift ;;
    *) echo "unknown option: $1" >&2; exit 2 ;;
  esac
done

here="$(cd "$(dirname "$0")" && pwd)"
json() { python3 -c "import json,sys; d=json.load(sys.stdin); print($1)"; }

account=$(aws sts get-caller-identity --query Account --output text 2>/dev/null) || {
  echo "The AWS CLI is not signed in. Run 'aws login' (or 'aws configure') and try again." >&2
  exit 1
}
echo "Account $account, region $REGION, stack $STACK."

# 1. Make sure this cannot cost money without an explicit opt-in.
plan=$(aws freetier get-account-plan-state --region us-east-1 --output json 2>/dev/null || echo '{}')
plan_type=$(echo "$plan" | json 'd.get("accountPlanType", "UNKNOWN")')
plan_status=$(echo "$plan" | json 'd.get("accountPlanStatus", "UNKNOWN")')
credits=$(echo "$plan" | json '(d.get("accountPlanRemainingCredits") or {}).get("amount", "unknown")')
expires=$(echo "$plan" | json 'd.get("accountPlanExpirationDate", "unknown")')
if [ "$plan_type" = "FREE" ] && [ "$plan_status" = "ACTIVE" ]; then
  echo "Free plan is active: usage is paid from credits (USD $credits left) and the account cannot be charged."
  echo "The plan ends $expires; the app stops when it does unless you upgrade the account."
else
  echo "This account's plan is $plan_type ($plan_status). Once its credits run out, AWS bills the card on file;"
  echo "this stack costs roughly USD 12-14 per month (instance, public IPv4 address, disk). CloudFront stays free."
  if [ "$ACCEPT_PAID" != "yes" ]; then
    echo "Stopping. Re-run with --accept-paid-plan to deploy anyway." >&2
    exit 1
  fi
fi

# 2. Only CloudFront may reach the instance.
prefix_list=""
if [ "$CLOUDFRONT" = "true" ]; then
  prefix_list=$(aws ec2 describe-managed-prefix-lists --region "$REGION" \
    --filters Name=prefix-list-name,Values=com.amazonaws.global.cloudfront.origin-facing \
    --query 'PrefixLists[0].PrefixListId' --output text)
  [ "$prefix_list" = "None" ] && prefix_list=""
fi

# 3. Optional: email when actual spend goes above one cent.
if [ -n "$ALERT_EMAIL" ]; then
  aws budgets create-budget --account-id "$account" \
    --budget '{"BudgetName":"changeguard-any-spend","BudgetLimit":{"Amount":"0.01","Unit":"USD"},"TimeUnit":"MONTHLY","BudgetType":"COST"}' \
    --notifications-with-subscribers "[{\"Notification\":{\"NotificationType\":\"ACTUAL\",\"ComparisonOperator\":\"GREATER_THAN\",\"Threshold\":0.01,\"ThresholdType\":\"ABSOLUTE_VALUE\"},\"Subscribers\":[{\"SubscriptionType\":\"EMAIL\",\"Address\":\"$ALERT_EMAIL\"}]}]" \
    >/dev/null 2>&1 && echo "Spend alert created for $ALERT_EMAIL." || echo "Spend alert already exists or could not be created; continuing."
fi

# 4. Create or update the stack.
aws cloudformation deploy --region "$REGION" --stack-name "$STACK" \
  --template-file "$here/changeguard.yaml" \
  --capabilities CAPABILITY_IAM \
  --no-fail-on-empty-changeset \
  --parameter-overrides \
    InstanceType="$INSTANCE_TYPE" RepositoryUrl="$REPO" Branch="$BRANCH" \
    CloudFrontPrefixListId="$prefix_list" EnableCloudFront="$CLOUDFRONT"

url=$(aws cloudformation describe-stacks --region "$REGION" --stack-name "$STACK" \
  --query "Stacks[0].Outputs[?OutputKey=='Url'].OutputValue" --output text)

# 5. The instance builds the app on first boot; wait until it answers.
echo "Stack is up. The instance is building the app (usually 10-20 minutes)."
for _ in $(seq 1 80); do
  code=$(curl -s -o /dev/null -w '%{http_code}' --max-time 10 "$url/api/v1/health" || true)
  if [ "$code" = "200" ]; then
    echo "Live: $url"
    exit 0
  fi
  sleep 15
done
echo "Not answering yet. It may still be building; check again shortly: $url"
echo "Build log: aws ssm start-session --target <instance id>, then: sudo tail -f /var/log/changeguard-setup.log"
