@description('Short, globally unique resource name prefix.')
@minLength(3)
@maxLength(10)
param namePrefix string

@description('Globally unique ACR name.')
@minLength(5)
@maxLength(50)
param acrName string

@description('Log Analytics workspace retention in days.')
@minValue(30)
@maxValue(90)
param logRetentionDays int = 30

resource logAnalytics 'Microsoft.OperationalInsights/workspaces@2023-09-01' = {
  name: '${namePrefix}-logs'
  location: resourceGroup().location
  properties: {
    retentionInDays: logRetentionDays
    sku: {
      name: 'PerGB2018'
    }
  }
}

resource registry 'Microsoft.ContainerRegistry/registries@2023-07-01' = {
  name: acrName
  location: resourceGroup().location
  sku: {
    name: 'Standard'
  }
  properties: {
    adminUserEnabled: false
    publicNetworkAccess: 'Enabled'
  }
}

resource environment 'Microsoft.App/managedEnvironments@2024-03-01' = {
  name: '${namePrefix}-aca'
  location: resourceGroup().location
  properties: {
    appLogsConfiguration: {
      destination: 'log-analytics'
      logAnalyticsConfiguration: {
        customerId: logAnalytics.properties.customerId
        sharedKey: logAnalytics.listKeys().primarySharedKey
      }
    }
    zoneRedundant: false
  }
}

output acrName string = registry.name
output registryLoginServer string = registry.properties.loginServer
output managedEnvironmentName string = environment.name
output logAnalyticsName string = logAnalytics.name
