param(
  [string]$StackName = "bugsnap",
  [string]$Region = "us-east-1"
)
$ErrorActionPreference = "Stop"
$account = aws sts get-caller-identity --query Account --output text

function Get-Out($key) {
  aws cloudformation describe-stacks --stack-name $StackName --region $Region `
    --query "Stacks[0].Outputs[?OutputKey=='$key'].OutputValue" --output text 2>&1 | Where-Object { $_ -is [string] }
}
# Empty the stack's buckets (CloudFormation cannot delete non-empty buckets)
foreach ($k in "FrontendBucketName", "AttachmentBucketName") {
  $b = Get-Out $k
  if ($b) { Write-Host "Emptying $b"; aws s3 rm "s3://$b" --recursive --region $Region | Out-Null }
}

aws cloudformation delete-stack --stack-name $StackName --region $Region
aws cloudformation wait stack-delete-complete --stack-name $StackName --region $Region
Write-Host "Stack deleted."

# Remove the artifact bucket created by deploy.ps1
$artifactBucket = "$StackName-artifacts-$account-$Region"
$exists = aws s3api list-buckets --query "Buckets[?Name=='$artifactBucket'].Name" --output text
if ($exists) {
  aws s3 rb "s3://$artifactBucket" --force --region $Region
  Write-Host "Artifact bucket removed."
}
