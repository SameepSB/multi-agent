@description('Short, globally unique resource name prefix.')
@minLength(3)
@maxLength(10)
param namePrefix string

@description('Immutable image reference for the API and private workers (must use @sha256 digest).')
param containerImage string


@description('Existing Key Vault name containing the OpenAI API key secret.')
param keyVaultName string

@description('Versioned full URI of the OpenAI key secret in Key Vault.')
param openAiSecretUri string

@description('OIDC issuer used by API callers and worker tokens.')
param oidcIssuer string

@description('OIDC JWKS endpoint, served over HTTPS.')
param oidcJwksUrl string

@description('NWS application User-Agent with an operator contact; required in live-weather mode.')
param nwsUserAgent string

@description('Audience required for user API access tokens.')
param userApiAudience string

@description('Audience requested for the Weather Agent managed identity token.')
param weatherA2AAudience string

@description('Audience requested for the Travel Advisor managed identity token.')
param travelA2AAudience string

@description('Existing Azure Container Registry name.')
param acrName string

@description('Existing ACA managed environment name.')
param environmentName string

var apiName = '${namePrefix}-api'
var weatherName = '${namePrefix}-weather'
var travelName = '${namePrefix}-travel'
var apiIdentityName = '${namePrefix}-api-id'
var weatherIdentityName = '${namePrefix}-weather-id'
var travelIdentityName = '${namePrefix}-travel-id'
var workerBaseEnvironment = [
  {
    name: 'APP_ENV'
    value: 'production'
  }
  {
    name: 'LOG_LEVEL'
    value: 'INFO'
  }
  {
    name: 'REQUEST_TIMEOUT_SECONDS'
    value: '30'
  }
  {
    name: 'MAX_CITIES'
    value: '4'
  }
  {
    name: 'STUB_PROVIDERS'
    value: 'false'
  }
  {
    name: 'NWS_USER_AGENT'
    value: nwsUserAgent
  }
  {
    name: 'OIDC_ISSUER'
    value: oidcIssuer
  }
  {
    name: 'OIDC_JWKS_URL'
    value: oidcJwksUrl
  }
]

resource environment 'Microsoft.App/managedEnvironments@2024-03-01' existing = {
  name: environmentName
}

resource registry 'Microsoft.ContainerRegistry/registries@2023-07-01' existing = {
  name: acrName
}

resource keyVault 'Microsoft.KeyVault/vaults@2023-07-01' existing = {
  name: keyVaultName
}

resource apiIdentity 'Microsoft.ManagedIdentity/userAssignedIdentities@2023-01-31' = {
  name: apiIdentityName
  location: resourceGroup().location
}

resource weatherIdentity 'Microsoft.ManagedIdentity/userAssignedIdentities@2023-01-31' = {
  name: weatherIdentityName
  location: resourceGroup().location
}

resource travelIdentity 'Microsoft.ManagedIdentity/userAssignedIdentities@2023-01-31' = {
  name: travelIdentityName
  location: resourceGroup().location
}

resource apiAcrPull 'Microsoft.Authorization/roleAssignments@2022-04-01' = {
  name: guid(registry.id, apiIdentity.id, '7f951dda-4ed3-4680-a7ca-43fe172d538d')
  scope: registry
  properties: {
    roleDefinitionId: subscriptionResourceId(
      'Microsoft.Authorization/roleDefinitions',
      '7f951dda-4ed3-4680-a7ca-43fe172d538d'
    )
    principalId: apiIdentity.properties.principalId
    principalType: 'ServicePrincipal'
  }
}

resource weatherAcrPull 'Microsoft.Authorization/roleAssignments@2022-04-01' = {
  name: guid(
    registry.id,
    weatherIdentity.id,
    '7f951dda-4ed3-4680-a7ca-43fe172d538d'
  )
  scope: registry
  properties: {
    roleDefinitionId: subscriptionResourceId(
      'Microsoft.Authorization/roleDefinitions',
      '7f951dda-4ed3-4680-a7ca-43fe172d538d'
    )
    principalId: weatherIdentity.properties.principalId
    principalType: 'ServicePrincipal'
  }
}

resource travelAcrPull 'Microsoft.Authorization/roleAssignments@2022-04-01' = {
  name: guid(
    registry.id,
    travelIdentity.id,
    '7f951dda-4ed3-4680-a7ca-43fe172d538d'
  )
  scope: registry
  properties: {
    roleDefinitionId: subscriptionResourceId(
      'Microsoft.Authorization/roleDefinitions',
      '7f951dda-4ed3-4680-a7ca-43fe172d538d'
    )
    principalId: travelIdentity.properties.principalId
    principalType: 'ServicePrincipal'
  }
}

resource apiKeyVaultRead 'Microsoft.Authorization/roleAssignments@2022-04-01' = {
  name: guid(
    keyVault.id,
    apiIdentity.id,
    '4633458b-17de-408a-b874-0445c86b69e6'
  )
  scope: keyVault
  properties: {
    roleDefinitionId: subscriptionResourceId(
      'Microsoft.Authorization/roleDefinitions',
      '4633458b-17de-408a-b874-0445c86b69e6'
    )
    principalId: apiIdentity.properties.principalId
    principalType: 'ServicePrincipal'
  }
}

module weatherApp 'worker-app.bicep' = {
  name: 'weather-container-app'
  params: {
    appName: weatherName
    containerImage: containerImage
    environmentId: environment.id
    registryServer: registry.properties.loginServer
    identityResourceId: weatherIdentity.id
    targetPort: 5001
    environmentVariables: concat(workerBaseEnvironment, [
      {
        name: 'WEATHER_A2A_AUDIENCE'
        value: weatherA2AAudience
      }
      {
        name: 'TRAVEL_A2A_AUDIENCE'
        value: travelA2AAudience
      }
      {
        name: 'TRUSTED_COORDINATOR_OBJECT_ID'
        value: apiIdentity.properties.principalId
      }
      {
        name: 'TRAVEL_DATA_PATH'
        value: '/app/data/travel_data.json'
      }
    ])
  }
  dependsOn: [weatherAcrPull]
}

module travelApp 'worker-app.bicep' = {
  name: 'travel-container-app'
  params: {
    appName: travelName
    containerImage: containerImage
    environmentId: environment.id
    registryServer: registry.properties.loginServer
    identityResourceId: travelIdentity.id
    targetPort: 5003
    environmentVariables: concat(workerBaseEnvironment, [
      {
        name: 'WEATHER_A2A_AUDIENCE'
        value: weatherA2AAudience
      }
      {
        name: 'TRAVEL_A2A_AUDIENCE'
        value: travelA2AAudience
      }
      {
        name: 'TRUSTED_COORDINATOR_OBJECT_ID'
        value: apiIdentity.properties.principalId
      }
      {
        name: 'TRAVEL_DATA_PATH'
        value: '/app/data/travel_data.json'
      }
    ])
  }
  dependsOn: [travelAcrPull]
}

module apiApp 'api-app.bicep' = {
  name: 'api-container-app'
  params: {
    appName: apiName
    containerImage: containerImage
    environmentId: environment.id
    registryServer: registry.properties.loginServer
    identityResourceId: apiIdentity.id
    openAiSecretUri: openAiSecretUri
    environmentVariables: concat(workerBaseEnvironment, [
      {
        name: 'API_PORT'
        value: '8080'
      }
      {
        name: 'OIDC_AUDIENCE'
        value: userApiAudience
      }
      {
        name: 'WEATHER_AGENT_URL'
        value: 'https://${weatherName}.${environment.properties.defaultDomain}'
      }
      {
        name: 'TRAVEL_AGENT_URL'
        value: 'https://${travelName}.${environment.properties.defaultDomain}'
      }
      {
        name: 'WEATHER_A2A_AUDIENCE'
        value: weatherA2AAudience
      }
      {
        name: 'TRAVEL_A2A_AUDIENCE'
        value: travelA2AAudience
      }
      {
        name: 'TRAVEL_DATA_PATH'
        value: '/app/data/travel_data.json'
      }
      {
        name: 'MANAGED_IDENTITY_CLIENT_ID'
        value: apiIdentity.properties.clientId
      }
    ])
  }
  dependsOn: [
    apiAcrPull
    apiKeyVaultRead
  ]
}

output apiName string = apiName
output weatherName string = weatherName
output travelName string = travelName
output coordinatorPrincipalId string = apiIdentity.properties.principalId
output containerRegistryName string = acrName
output secretsVaultName string = keyVaultName
output managedEnvironmentName string = environmentName
output apiIdentityName string = apiIdentityName
output weatherIdentityName string = weatherIdentityName
output travelIdentityName string = travelIdentityName
