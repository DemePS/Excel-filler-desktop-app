// Excel filler gateway on Azure API Management: the only way the desktop app reaches Claude.
//
// Creates (or reuses) an API Management instance and adds:
// - the "excel-filler" API: POST /v1/messages (to Claude on Foundry) and GET /settings (the apps'
//   central settings), with their policies (policies/*.xml; api.xml checks the sign-in token and its
//   Excel.Filler.User role on Claude calls -- the role is already in the token: no extra lookup);
// - named values: what IT changes without touching the PCs (deployment, minimum version, notice,
//   per-user limits);
// - the backend (the Foundry endpoint) and the gateway identity's access to the Foundry resource;
// - optionally, logs and metrics in Application Insights / Log Analytics (no request content).
//
// Deploy: see infra/README.md. Run infra/scripts/entra-setup.ps1 first (app registrations).

targetScope = 'resourceGroup'

@description('API Management instance name (new or existing).')
param apimName string

@description('true: create the API Management instance; false: use an existing one in this resource group (it must have a system-assigned managed identity).')
param createApim bool = false

@description('For a new instance: pricing tier.')
@allowed(['Developer', 'BasicV2', 'StandardV2', 'Basic', 'Standard', 'Premium'])
param apimSku string = 'BasicV2'

@description('For a new instance: publisher e-mail (API Management notifications).')
param publisherEmail string = ''

@description('For a new instance: publisher (organization) name.')
param publisherName string = ''

param location string = resourceGroup().location

@description('Resource ID of the Foundry (Azure AI Services) resource hosting the Claude deployment.')
param foundryResourceId string

@description('Its Claude endpoint, e.g. https://<resource>.services.ai.azure.com/anthropic')
param foundryEndpoint string

@description('Token audience for Foundry (the same as the app uses without a gateway).')
param foundryTokenResource string = 'https://ai.azure.com'

@description('Role given to the gateway identity on the Foundry resource. Default: Cognitive Services User.')
param foundryRoleDefinitionId string = 'a97b65f3-24c7-4388-baec-2e87135dc908'

@description('The Claude deployment the apps use (named value; change it later without redeploying the apps).')
param deployment string

@description('Oldest app version allowed to run.')
param minimumAppVersion string = '0.1.0'

@description('A message shown at the top of every window (empty: none).')
param notice string = ''

@description('Entra ID tenant ID.')
param tenantId string = tenant().tenantId

@description('Application (client) ID of the gateway API registration (entra-setup.ps1 prints it).')
param apiAppId string

@description('Application (client) ID of the desktop app registration (entra-setup.ps1 prints it).')
param clientAppId string

@description('Per-user limit: calls to Claude per minute (one filling job makes several calls).')
param callsPerMinute int = 20

@description('Per-user limit: calls to Claude per day.')
param callsPerDay int = 2000

@description('Optional: Application Insights resource ID, for request logs and per-user metrics.')
param appInsightsResourceId string = ''

@description('Optional: Log Analytics workspace ID, for the gateway\'s resource logs (GatewayLogs).')
param logAnalyticsWorkspaceId string = ''

resource newApim 'Microsoft.ApiManagement/service@2024-05-01' = if (createApim) {
  name: apimName
  location: location
  sku: {
    name: apimSku
    capacity: 1
  }
  identity: {
    type: 'SystemAssigned'
  }
  properties: {
    publisherEmail: publisherEmail
    publisherName: publisherName
  }
}

resource apim 'Microsoft.ApiManagement/service@2024-05-01' existing = {
  name: apimName
  dependsOn: [newApim]
}

// --- Named values: the settings IT changes (API Management > Named values)
var namedValues = {
  'excel-filler-tenant-id': tenantId
  'excel-filler-api-app-id': apiAppId
  'excel-filler-client-app-id': clientAppId
  'excel-filler-foundry-token-resource': foundryTokenResource
  'excel-filler-calls-per-minute': string(callsPerMinute)
  'excel-filler-calls-per-day': string(callsPerDay)
  'excel-filler-settings': string({
    deployment: deployment
    minimum_version: minimumAppVersion
    notice: notice
  })
}

resource values 'Microsoft.ApiManagement/service/namedValues@2024-05-01' = [for item in items(namedValues): {
  parent: apim
  name: item.key
  properties: {
    displayName: item.key
    value: item.value
    secret: false
  }
}]

// --- Backend: Claude on Foundry
resource backend 'Microsoft.ApiManagement/service/backends@2024-05-01' = {
  parent: apim
  name: 'excel-filler-foundry'
  properties: {
    description: 'Claude on Microsoft Foundry'
    protocol: 'http'
    url: foundryEndpoint
  }
}

// --- The API: https://<apim>.azure-api.net/excel-filler
resource api 'Microsoft.ApiManagement/service/apis@2024-05-01' = {
  parent: apim
  name: 'excel-filler'
  properties: {
    displayName: 'Excel filler'
    description: 'Claude for the Excel filler desktop app (sign-in with the work account).'
    path: 'excel-filler'
    protocols: ['https']
    subscriptionRequired: false // access is checked with the employee's Entra ID token
    serviceUrl: foundryEndpoint
  }
}

// Claude calls (<base />): the sign-in token, its Excel.Filler.User role, per-user limits.
resource apiPolicy 'Microsoft.ApiManagement/service/apis/policies@2024-05-01' = {
  parent: api
  name: 'policy'
  properties: {
    format: 'rawxml'
    value: loadTextContent('policies/api.xml')
  }
  dependsOn: [values]
}

resource messages 'Microsoft.ApiManagement/service/apis/operations@2024-05-01' = {
  parent: api
  name: 'messages'
  properties: {
    displayName: 'Claude messages'
    method: 'POST'
    urlTemplate: '/v1/messages'
  }
}

resource messagesPolicy 'Microsoft.ApiManagement/service/apis/operations/policies@2024-05-01' = {
  parent: messages
  name: 'policy'
  properties: {
    format: 'rawxml'
    value: loadTextContent('policies/messages.xml')
  }
  dependsOn: [apiPolicy, backend]
}

resource settings 'Microsoft.ApiManagement/service/apis/operations@2024-05-01' = {
  parent: api
  name: 'settings'
  properties: {
    displayName: 'App settings'
    method: 'GET'
    urlTemplate: '/settings'
  }
}

resource settingsPolicy 'Microsoft.ApiManagement/service/apis/operations/policies@2024-05-01' = {
  parent: settings
  name: 'policy'
  properties: {
    format: 'rawxml'
    value: loadTextContent('policies/settings.xml')
  }
  dependsOn: [values]
}

// --- The gateway identity may call the Foundry resource (it can be in another resource group)
var foundryParts = split(foundryResourceId, '/')

module foundryAccess 'modules/foundry-access.bicep' = {
  name: 'excel-filler-foundry-access'
  scope: resourceGroup(foundryParts[2], foundryParts[4])
  params: {
    foundryAccountName: last(foundryParts)
    principalId: apim.identity.principalId
    roleDefinitionId: foundryRoleDefinitionId
  }
}

// --- Optional: Application Insights (requests, errors, per-user metrics; never bodies)
resource appInsights 'Microsoft.Insights/components@2020-02-02' existing = if (!empty(appInsightsResourceId)) {
  name: last(split(appInsightsResourceId, '/'))
  scope: resourceGroup(split(appInsightsResourceId, '/')[2], split(appInsightsResourceId, '/')[4])
}

resource logger 'Microsoft.ApiManagement/service/loggers@2024-05-01' = if (!empty(appInsightsResourceId)) {
  parent: apim
  name: 'excel-filler-appinsights'
  properties: {
    loggerType: 'applicationInsights'
    resourceId: appInsightsResourceId
    credentials: {
      connectionString: appInsights!.properties.ConnectionString
    }
  }
}

resource diagnostics 'Microsoft.ApiManagement/service/apis/diagnostics@2024-05-01' = if (!empty(appInsightsResourceId)) {
  parent: api
  name: 'applicationinsights'
  properties: {
    loggerId: logger.id
    alwaysLog: 'allErrors'
    sampling: {
      samplingType: 'fixed'
      percentage: 100
    }
    verbosity: 'information' // includes the policies' <trace> (user, app version)
    logClientIp: false
    metrics: true // the policies' <emit-metric> (requests per user and app version)
    // Headers only; 0 body bytes: document contents and answers are never logged.
    frontend: {
      request: { headers: ['x-app-version'], body: { bytes: 0 } }
      response: { headers: [], body: { bytes: 0 } }
    }
    backend: {
      request: { headers: [], body: { bytes: 0 } }
      response: { headers: [], body: { bytes: 0 } }
    }
  }
}

// --- Optional: the gateway's resource logs in Log Analytics
resource gatewayLogs 'Microsoft.Insights/diagnosticSettings@2021-05-01-preview' = if (!empty(logAnalyticsWorkspaceId)) {
  name: 'excel-filler-gateway-logs'
  scope: apim
  properties: {
    workspaceId: logAnalyticsWorkspaceId
    logs: [{ category: 'GatewayLogs', enabled: true }]
    metrics: [{ category: 'AllMetrics', enabled: true }]
  }
}

@description('What the PCs need (infra/scripts/set-pc-settings.ps1): the gateway URL.')
output gatewayUrl string = '${apim.properties.gatewayUrl}/excel-filler'

@description('The gateway identity (it was given access to the Foundry resource).')
output gatewayPrincipalId string = apim.identity.principalId
