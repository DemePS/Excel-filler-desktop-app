<#
.SYNOPSIS
  Entra ID setup for Excel filler (run once, by an Entra ID administrator, with the Azure CLI signed in:
  `az login`). Windows PowerShell 5.1 or PowerShell 7.

.DESCRIPTION
  Creates:
  1. "<Prefix> gateway API": the app registration the sign-in tokens are for. It has the role
     Excel.Filler.User, and "assignment required": Entra ID only gives a token to people assigned to
     it, so only they can use Excel filler.
  2. The "Excel filler users" group assigned to that role (group-based assignment needs Entra ID P1).
  3. "<Prefix> desktop": the app registration people sign in with (a public client: no secret),
     allowed to ask for tokens for the gateway API without a consent prompt.
  4. Optionally, a shorter lifetime for these tokens (-TokenLifetimeMinutes), so that removing someone
     from the group takes effect sooner (by default, a token already issued stays valid 60-90 min).

  Prints the values for infra/main.bicep and for the repository's Actions variables (the build puts
  them into the downloadable app).

.EXAMPLE
  ./entra-setup.ps1 -UsersGroup "Excel filler users"
  ./entra-setup.ps1 -UsersGroup 0f1e2d3c-... -TokenLifetimeMinutes 15
#>
param(
  [Parameter(Mandatory)] [string] $UsersGroup,  # the group's display name or object ID
  [string] $Prefix = "Excel filler",
  [ValidateRange(0, 1440)] [int] $TokenLifetimeMinutes = 0  # 0: Entra ID's default; otherwise 10 or more
)
$ErrorActionPreference = "Stop"
$graph = "https://graph.microsoft.com/v1.0"

function Invoke-Graph([string] $Method, [string] $Uri, $Body = $null) {
  $arguments = @("rest", "--method", $Method, "--uri", $Uri)
  $file = $null
  if ($null -ne $Body) {
    $file = New-TemporaryFile
    # UTF-8 without BOM (Windows PowerShell 5.1 would add one with Set-Content -Encoding utf8).
    [System.IO.File]::WriteAllText($file, ($Body | ConvertTo-Json -Depth 20), (New-Object System.Text.UTF8Encoding $false))
    $arguments += @("--headers", "Content-Type=application/json", "--body", "@$file")
  }
  try {
    $output = & az @arguments
    if ($LASTEXITCODE -ne 0) { throw "Microsoft Graph call failed: $Method $Uri" }
    if ($output) { return ($output | Out-String | ConvertFrom-Json) }
  } finally {
    if ($file) { Remove-Item $file -ErrorAction SilentlyContinue }
  }
}

if ($TokenLifetimeMinutes -ne 0 -and $TokenLifetimeMinutes -lt 10) { throw "-TokenLifetimeMinutes: 10 minutes at least." }
$tenantId = (az account show --query tenantId -o tsv)
if (-not $tenantId) { throw "Sign in first: az login" }

$groupId = if ($UsersGroup -match '^[0-9a-fA-F-]{36}$') { $UsersGroup } else {
  (az ad group show --group $UsersGroup --query id -o tsv)
}
if (-not $groupId) { throw "Group not found: $UsersGroup" }

# 1. The gateway API: what the tokens are for, with the role people need.
$roleId = [guid]::NewGuid().ToString()
$scopeId = [guid]::NewGuid().ToString()
$api = Invoke-Graph POST "$graph/applications" @{ displayName = "$Prefix gateway API"; signInAudience = "AzureADMyOrg" }
$apiSettings = @{
  requestedAccessTokenVersion = 2
  oauth2PermissionScopes = @(@{
    id = $scopeId; value = "access_as_user"; type = "User"; isEnabled = $true
    adminConsentDisplayName = "Use Excel filler"
    adminConsentDescription = "Lets the Excel filler desktop app call Claude through the organization's gateway for the signed-in user."
    userConsentDisplayName = "Use Excel filler"
    userConsentDescription = "Lets Excel filler call Claude for you."
  })
}
Invoke-Graph PATCH "$graph/applications/$($api.id)" @{
  identifierUris = @("api://$($api.appId)")
  appRoles = @(@{
    id = $roleId; value = "Excel.Filler.User"; isEnabled = $true; allowedMemberTypes = @("User")
    displayName = "Excel filler user"; description = "Can use the Excel filler desktop app."
  })
  api = $apiSettings
} | Out-Null
$apiSp = Invoke-Graph POST "$graph/servicePrincipals" @{ appId = $api.appId; appRoleAssignmentRequired = $true }

# 2. The users group gets the role.
Invoke-Graph POST "$graph/servicePrincipals/$($apiSp.id)/appRoleAssignedTo" @{
  principalId = $groupId; resourceId = $apiSp.id; appRoleId = $roleId
} | Out-Null

# 3. The desktop app people sign in with (public client: the browser page and the Windows account).
$desktop = Invoke-Graph POST "$graph/applications" @{
  displayName = "$Prefix desktop"; signInAudience = "AzureADMyOrg"; isFallbackPublicClient = $true
  publicClient = @{ redirectUris = @("http://localhost") }
  requiredResourceAccess = @(@{ resourceAppId = $api.appId; resourceAccess = @(@{ id = $scopeId; type = "Scope" }) })
}
Invoke-Graph PATCH "$graph/applications/$($desktop.id)" @{
  publicClient = @{ redirectUris = @("http://localhost", "ms-appx-web://Microsoft.AAD.BrokerPlugin/$($desktop.appId)") }
} | Out-Null
Invoke-Graph POST "$graph/servicePrincipals" @{ appId = $desktop.appId } | Out-Null
# The desktop app may ask for gateway API tokens without a consent prompt.
$apiSettings.preAuthorizedApplications = @(@{ appId = $desktop.appId; delegatedPermissionIds = @($scopeId) })
Invoke-Graph PATCH "$graph/applications/$($api.id)" @{ api = $apiSettings } | Out-Null

# 4. Optional: shorter tokens for the gateway API (removals take effect sooner).
if ($TokenLifetimeMinutes -gt 0) {
  $lifetime = [TimeSpan]::FromMinutes($TokenLifetimeMinutes).ToString("hh\:mm\:ss")
  $policy = Invoke-Graph POST "$graph/policies/tokenLifetimePolicies" @{
    displayName = "$Prefix access tokens ($TokenLifetimeMinutes min)"; isOrganizationDefault = $false
    definition = @("{`"TokenLifetimePolicy`":{`"Version`":1,`"AccessTokenLifetime`":`"$lifetime`"}}")
  }
  Invoke-Graph POST "$graph/servicePrincipals/$($apiSp.id)/tokenLifetimePolicies/`$ref" @{
    "@odata.id" = "$graph/policies/tokenLifetimePolicies/$($policy.id)"
  } | Out-Null
}

Write-Host ""
Write-Host "Done. Values to use:" -ForegroundColor Green
Write-Host "  infra/main.bicep:  tenantId=$tenantId  apiAppId=$($api.appId)  clientAppId=$($desktop.appId)"
Write-Host "  Repository Actions variables (Settings > Secrets and variables > Actions > Variables):"
Write-Host "    EXCEL_FILLER_API_SCOPE = api://$($api.appId)/.default"
Write-Host "    EXCEL_FILLER_CLIENT_ID = $($desktop.appId)"
Write-Host "    EXCEL_FILLER_TENANT_ID = $tenantId"
Write-Host "    EXCEL_FILLER_GATEWAY   = (the gatewayUrl output of main.bicep)"
Write-Host "  People to give access to: add them to the group '$UsersGroup'."
