"""Short names for the official provider icons fetched by tools/fetch_icons.sh.

Templates and course content refer to icons by key ("aws:fsx-windows"), so a renamed
file in a future icon package only needs fixing here.
"""
from pathlib import Path

VENDOR_DIR = Path(__file__).parent / "static" / "vendor"
MISSING = "/static/img/missing-icon.svg"

ICONS = {
    # provider logos
    "aws:logo": "aws/AWS-Cloud-logo_32_Dark.svg",
    "azure:logo": "azure/10018-icon-service-Azure-A.svg",
    "k8s:logo": "k8s/kubernetes-icon-color.svg",
    # Google's icon packs don't include the Google Cloud logo. Drop one at
    # app/static/vendor/gcp/logo.svg and it replaces the placeholder badge.
    "gcp:logo": "gcp/logo.svg",
    # AWS groups (the boxes in a diagram)
    "aws:region": "aws/Region_32.svg",
    "aws:vpc": "aws/Virtual-private-cloud-VPC_32.svg",
    "aws:datacenter": "aws/Corporate-data-center_32.svg",
    # AWS general
    "aws:user": "aws/Res_User_48_Dark.svg",
    "aws:users": "aws/Res_Users_48_Dark.svg",
    "aws:client": "aws/Res_Client_48_Dark.svg",
    # AWS services
    "aws:ec2": "aws/Arch_Amazon-EC2_64.svg",
    "aws:lambda": "aws/Arch_AWS-Lambda_64.svg",
    "aws:eks": "aws/Arch_Amazon-Elastic-Kubernetes-Service_64.svg",
    "aws:s3": "aws/Arch_Amazon-Simple-Storage-Service_64.svg",
    "aws:efs": "aws/Arch_Amazon-EFS_64.svg",
    "aws:fsx-windows": "aws/Arch_Amazon-FSx-for-WFS_64.svg",
    "aws:ebs": "aws/Arch_Amazon-Elastic-Block-Store_64.svg",
    "aws:backup": "aws/Arch_AWS-Backup_64.svg",
    "aws:rds": "aws/Arch_Amazon-RDS_64.svg",
    "aws:aurora": "aws/Arch_Amazon-Aurora_64.svg",
    "aws:dynamodb": "aws/Arch_Amazon-DynamoDB_64.svg",
    "aws:elasticache": "aws/Arch_Amazon-ElastiCache_64.svg",
    "aws:sqs": "aws/Arch_Amazon-Simple-Queue-Service_64.svg",
    "aws:sns": "aws/Arch_Amazon-Simple-Notification-Service_64.svg",
    "aws:kinesis-streams": "aws/Arch_Amazon-Kinesis-Data-Streams_64.svg",
    "aws:elb": "aws/Arch_Elastic-Load-Balancing_64.svg",
    "aws:cloudfront": "aws/Arch_Amazon-CloudFront_64.svg",
    "aws:route53": "aws/Arch_Amazon-Route-53_64.svg",
    "aws:vpc-service": "aws/Arch_Amazon-Virtual-Private-Cloud_64.svg",
    "aws:global-accelerator": "aws/Arch_AWS-Global-Accelerator_64.svg",
    "aws:iam": "aws/Arch_AWS-Identity-and-Access-Management_64.svg",
    "aws:waf": "aws/Arch_AWS-WAF_64.svg",
    "aws:kms": "aws/Arch_AWS-Key-Management-Service_64.svg",
    "aws:directory-service": "aws/Arch_AWS-Directory-Service_64.svg",
    "aws:cloudtrail": "aws/Arch_AWS-CloudTrail_64.svg",
    "aws:cloudwatch": "aws/Arch_Amazon-CloudWatch_64.svg",
    "aws:organizations": "aws/Arch_AWS-Organizations_64.svg",
    "aws:control-tower": "aws/Arch_AWS-Control-Tower_64.svg",
    "aws:cognito": "aws/Arch_Amazon-Cognito_64.svg",
    "aws:secrets-manager": "aws/Arch_AWS-Secrets-Manager_64.svg",
    "aws:shield": "aws/Arch_AWS-Shield_64.svg",
    "aws:guardduty": "aws/Arch_Amazon-GuardDuty_64.svg",
    "aws:macie": "aws/Arch_Amazon-Macie_64.svg",
    "aws:inspector": "aws/Arch_Amazon-Inspector_64.svg",
    "aws:detective": "aws/Arch_Amazon-Detective_64.svg",
    "aws:security-hub": "aws/Arch_AWS-Security-Hub_64.svg",
    "aws:acm": "aws/Arch_AWS-Certificate-Manager_64.svg",
    "aws:systems-manager": "aws/Arch_AWS-Systems-Manager_64.svg",
    "aws:config": "aws/Arch_AWS-Config_64.svg",
    "aws:privatelink": "aws/Arch_AWS-PrivateLink_64.svg",
    "aws:transit-gateway": "aws/Arch_AWS-Transit-Gateway_64.svg",
    "aws:network-firewall": "aws/Arch_AWS-Network-Firewall_64.svg",
    "aws:direct-connect": "aws/Arch_AWS-Direct-Connect_64.svg",
    "aws:site-to-site-vpn": "aws/Arch_AWS-Site-to-Site-VPN_64.svg",
    "aws:auto-scaling": "aws/Arch_Amazon-EC2-Auto-Scaling_64.svg",
    "aws:eventbridge": "aws/Arch_Amazon-EventBridge_64.svg",
    "aws:firehose": "aws/Arch_Amazon-Data-Firehose_64.svg",
    "aws:athena": "aws/Arch_Amazon-Athena_64.svg",
    "aws:redshift": "aws/Arch_Amazon-Redshift_64.svg",
    "aws:neptune": "aws/Arch_Amazon-Neptune_64.svg",
    "aws:timestream": "aws/Arch_Amazon-Timestream_64.svg",
    "aws:documentdb": "aws/Arch_Amazon-DocumentDB_64.svg",
    "aws:snowball": "aws/Arch_AWS-Snowball-Edge_64.svg",
    "aws:datasync": "aws/Arch_AWS-DataSync_64.svg",
    "aws:storage-gateway": "aws/Arch_AWS-Storage-Gateway_64.svg",
    "aws:elastic-dr": "aws/Arch_AWS-Elastic-Disaster-Recovery_64.svg",
    "aws:cost-explorer": "aws/Arch_AWS-Cost-Explorer_64.svg",
    "aws:budgets": "aws/Arch_AWS-Budgets_64.svg",
    "aws:compute-optimizer": "aws/Arch_AWS-Compute-Optimizer_64.svg",
    "aws:savings-plans": "aws/Arch_Savings-Plans_64.svg",
}


# Our own badges, used when there's no official logo we're allowed to use
FALLBACKS = {
    "gcp:logo": "/static/img/gcp-cloud.svg",
    "security:logo": "/static/img/shield.svg",
}


def icon_url(key: str) -> str:
    """URL for an icon key, or a placeholder if the icon packages haven't been fetched."""
    rel = ICONS.get(key)
    if rel and (VENDOR_DIR / rel).is_file():
        return f"/static/vendor/{rel}"
    return FALLBACKS.get(key, MISSING)
