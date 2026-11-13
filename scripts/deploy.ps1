param(
  [string]$StackName = "bugsnap",
  [string]$Region = "us-east-1"
)
$ErrorActionPreference = "Stop"
$root = Split-Path -Parent $PSScriptRoot
$account = aws sts get-caller-identity --query Account --output text
$artifactBucket = "$StackName-artifacts-$account-$Region"

# 1. Artifact bucket for Lambda code (created once, outside the stack)
$exists = aws s3api list-buckets --query "Buckets[?Name=='$artifactBucket'].Name" --output text
if (-not $exists) {
  Write-Host "Creating artifact bucket $artifactBucket"
  aws s3api create-bucket --bucket $artifactBucket --region $Region | Out-Null
  aws s3api put-public-access-block --bucket $artifactBucket --public-access-block-configuration BlockPublicAcls=true,IgnorePublicAcls=true,BlockPublicPolicy=true,RestrictPublicBuckets=true
}

# 2. Package + deploy
$packaged = Join-Path $root "infra\packaged.yaml"
aws cloudformation package --template-file (Join-Path $root "infra\template.yaml") `
  --s3-bucket $artifactBucket --output-template-file $packaged --region $Region
if ($LASTEXITCODE -ne 0) { throw "package failed" }

# CloudFormation does not redeploy an API Gateway Deployment when only the methods change.
# Suffix its logical ID with a hash of the template so any change publishes a new deployment.
$content = Get-Content $packaged -Raw
$sha = [BitConverter]::ToString([Security.Cryptography.SHA256]::Create().ComputeHash([Text.Encoding]::UTF8.GetBytes($content))).Replace("-", "").Substring(0, 10)
$content = $content -replace '\bApiDeployment\b', "ApiDeployment$sha"
[IO.File]::WriteAllText($packaged, $content, (New-Object Text.UTF8Encoding $false))

aws cloudformation deploy --template-file $packaged --stack-name $StackName `
  --capabilities CAPABILITY_IAM --region $Region --no-fail-on-empty-changeset
if ($LASTEXITCODE -ne 0) { throw "deploy failed" }

# 3. Read outputs
function Get-Out($key) {
  aws cloudformation describe-stacks --stack-name $StackName --region $Region `
    --query "Stacks[0].Outputs[?OutputKey=='$key'].OutputValue" --output text
}
$apiUrl = Get-Out "ApiUrl"
$site = Get-Out "WebsiteUrl"
$bucket = Get-Out "FrontendBucketName"

# 4. Publish frontend with the real API URL
$stage = Join-Path $env:TEMP "bugsnap-frontend"
if (Test-Path $stage) { Remove-Item -Recurse -Force $stage }
Copy-Item -Recurse (Join-Path $root "frontend") $stage
$distId = Get-Out "DistributionId"
$cfg = "window.BUGSNAP_CONFIG = { apiUrl: `"$apiUrl`" };"
[IO.File]::WriteAllText((Join-Path $stage "config.js"), $cfg, (New-Object Text.UTF8Encoding $false))
aws s3 sync $stage "s3://$bucket" --delete --region $Region --cache-control "no-cache"
if ($LASTEXITCODE -ne 0) { throw "frontend upload failed" }

aws cloudfront create-invalidation --distribution-id $distId --paths "/*" --query "Invalidation.Status" --output text

Write-Host ""
Write-Host "API URL : $apiUrl"
Write-Host "Website : $site"
