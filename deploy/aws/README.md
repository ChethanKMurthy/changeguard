# Deploy on AWS (Free plan)

One EC2 instance runs the engine and the web app in Docker; CloudFront puts an
HTTPS link in front of it (`https://<id>.cloudfront.net`). Everything is created
by one CloudFormation stack and removed by deleting it.

```
browser ──HTTPS──▶ CloudFront ──HTTP, CloudFront addresses only──▶ EC2 :80 ── web (Next.js) ──▶ engine (FastAPI)
```

## Cost

| Resource | Monthly usage | Covered by |
|----------|---------------|------------|
| EC2 `t3.micro` (2 vCPU, 1 GB RAM + 2 GB swap) | 730 hours | Free plan credits (about USD 7.60 of them) |
| Public IPv4 address | 730 hours | Free plan credits (about USD 3.65) |
| EBS gp3, 20 GB | 20 GB | Free plan credits (about USD 1.60) |
| CloudFront | well under 1 TB and 10 million requests | Always-free allowance |
| Systems Manager, CloudFormation, IAM | n/a | Free |

On the **Free plan** (accounts created since July 2025 that have not upgraded),
AWS cannot charge you: usage is deducted from your credits, and when the plan
ends (six months after sign-up, or earlier if credits run out) the account is
closed unless you upgrade. The link stops working at that point. `deploy.sh`
checks the plan and refuses to deploy on a paid plan unless you pass
`--accept-paid-plan`; on a paid plan this stack costs about USD 13 a month once
credits are gone.

## Deploy

```bash
aws login                      # or: aws configure (access key of an IAM user)
deploy/aws/deploy.sh           # optional: --alert-email you@example.com
```

The script checks the account plan, finds CloudFront's address list for the
security group, creates the stack, and waits until the app answers. The
instance builds both images on first boot, which takes 10–20 minutes on a
`t3.micro`. It prints the link when the app is live.

If CloudFormation reports that the account cannot create CloudFront
distributions yet (some new accounts need verification first), deploy with
`--no-cloudfront`. The link is then the instance's `http://` address.

## Update after a push

```bash
deploy/aws/redeploy.sh         # pulls the latest commit on main and rebuilds on the instance
```

## Inspect

```bash
aws ssm start-session --target <InstanceId>      # shell without SSH
sudo tail -f /var/log/changeguard-setup.log       # first-boot log
sudo docker logs -f web; sudo docker logs -f engine
```

Session Manager needs the AWS CLI's Session Manager plugin installed locally.

## Remove

```bash
deploy/aws/destroy.sh
```

This deletes the instance, its disk (and the reports stored on it), the
CloudFront distribution, the role, and the security group.
