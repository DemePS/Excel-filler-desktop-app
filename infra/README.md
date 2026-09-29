# Deploying the Excel filler gateway (for IT)

The `api-management` version of Excel filler reaches Claude only through your organization's Azure
API Management gateway. Employees sign in with their work account; the gateway lets through only
people in the "Excel filler users" group, applies per-user limits, and calls Claude on Foundry with
its own identity. No key is ever stored on a PC.

```
Desktop app ──(employee's Entra ID token)──> API Management ──(gateway's managed identity)──> Claude on Foundry
                                               checks the token and the Excel.Filler.User role,
                                               per-user limits, logs (never document content)
```

Do these steps once, in this order.

## What you need

- An Azure subscription with a Foundry (Azure AI Services) resource and a Claude deployment.
- Rights to create app registrations and assign app roles in Entra ID (e.g. Application
  Administrator), and Owner or User Access Administrator on the Foundry resource (the deployment
  gives the gateway access to it).
- Entra ID P1 or higher, to give access through a group.
- Azure CLI (`az`), signed in: `az login`. PowerShell 5.1 or 7 for the setup script.

## 1. The users group

Create a security group in Entra ID, e.g. **Excel filler users**, and add the first people. Later,
giving or removing access is only adding or removing people from this group.

## 2. The app registrations

```powershell
./infra/scripts/entra-setup.ps1 -UsersGroup "Excel filler users"
# Shorter tokens, so that a removal takes effect within 15 minutes instead of 60-90:
./infra/scripts/entra-setup.ps1 -UsersGroup "Excel filler users" -TokenLifetimeMinutes 15
```

It creates the **Excel filler gateway API** (with the `Excel.Filler.User` role, assigned to the group)
and **Excel filler desktop** (what people sign in with), then prints the values used below:
`tenantId`, `apiAppId`, `clientAppId`, and the `EXCEL_FILLER_*` values.

## 3. The gateway

Deploy `main.bicep` to a resource group. Either reuse an API Management instance you already have
(it needs a system-assigned managed identity), or let the template create one (`createApim=true`).

```bash
az deployment group create \
  --resource-group <resource group> \
  --template-file infra/main.bicep \
  --parameters \
    apimName=<API Management name> \
    createApim=true publisherEmail=it@example.com publisherName="Example Corp" \
    foundryResourceId=/subscriptions/<sub>/resourceGroups/<rg>/providers/Microsoft.CognitiveServices/accounts/<foundry> \
    foundryEndpoint=https://<foundry>.services.ai.azure.com/anthropic \
    deployment=<Claude deployment name> \
    apiAppId=<apiAppId from step 2> \
    clientAppId=<clientAppId from step 2>
```

Creating a new instance takes from a few minutes (v2 tiers) up to about an hour (classic tiers).

| Parameter | Default | Meaning |
|---|---|---|
| `apimName` | (required) | API Management instance, new or existing |
| `createApim` | `false` | `true` creates the instance (`apimSku`, `publisherEmail`, `publisherName`) |
| `apimSku` | `BasicV2` | `Developer`, `BasicV2`, `StandardV2`, `Basic`, `Standard`, `Premium` |
| `foundryResourceId` | (required) | resource ID of the Foundry resource (it can be in another resource group) |
| `foundryEndpoint` | (required) | `https://<resource>.services.ai.azure.com/anthropic` |
| `deployment` | (required) | the Claude deployment the apps use |
| `apiAppId`, `clientAppId` | (required) | printed by `entra-setup.ps1` |
| `tenantId` | the deployment's tenant | Entra ID tenant |
| `callsPerMinute`, `callsPerDay` | `20`, `2000` | per-user limits (one filling job makes several calls) |
| `minimumAppVersion` | `0.1.0` | older app versions refuse to start and ask for the latest one |
| `notice` | empty | a message shown at the top of every window |
| `appInsightsResourceId` | empty | Application Insights: requests, errors, requests per user and app version |
| `logAnalyticsWorkspaceId` | empty | Log Analytics: the gateway's resource logs |
| `foundryRoleDefinitionId` | Cognitive Services User | the gateway identity's role on the Foundry resource |

The deployment's output **`gatewayUrl`** (`https://<apim>.azure-api.net/excel-filler`) is what the
app calls:

```bash
az deployment group show -g <resource group> -n main --query properties.outputs.gatewayUrl.value -o tsv
```

### Check it

```powershell
# The central settings (no sign-in needed): the deployment, minimum version and notice.
Invoke-RestMethod <gatewayUrl>/settings
# A Claude call without a token must be refused (401).
Invoke-WebRequest <gatewayUrl>/v1/messages -Method Post -Body '{}' -ContentType application/json
```

## 4. Build the app for your organization

In the GitHub repository: **Settings > Secrets and variables > Actions > Variables**, add:

| Variable | Value |
|---|---|
| `EXCEL_FILLER_GATEWAY` | `gatewayUrl` from step 3 |
| `EXCEL_FILLER_API_SCOPE` | `api://<apiAppId>/.default` |
| `EXCEL_FILLER_CLIENT_ID` | `clientAppId` |
| `EXCEL_FILLER_TENANT_ID` | `tenantId` |

Optionally, the `SIGNING_*` variables too, so that Windows trusts the app (see
`docs/code-signing.md`).

Then push to the `api-management` branch, or push a tag `vX.Y.Z` to also publish a GitHub Release.
The build writes these values into the app (`organization.json`), tests it on Windows, signs it when
configured, and publishes the zip that employees download.

## Day to day

- **Give or remove access:** add or remove people from the group. Someone removed can finish the
  token they already hold (up to its lifetime, see `-TokenLifetimeMinutes`); the app checks access
  again at each start.
- **Change the model, limits, notice or minimum version:** API Management > Named values
  (`excel-filler-settings`, `excel-filler-calls-per-minute`, `excel-filler-calls-per-day`), or deploy
  `main.bicep` again with new parameters. The PCs pick it up at their next start; nothing to reinstall.
- **See who uses it:** with Application Insights, the metric `Requests` (namespace `excel-filler`) by
  `User` (Entra object ID) and `App version`. Request and answer contents are never logged.
