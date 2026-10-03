@description('Container App resource name.')
param appName string

@description('Immutable ACR image reference containing @sha256:.')
param containerImage string

@description('ACA environment resource ID.')
param environmentId string

@description('Registry hostname.')
param registryServer string

@description('User-assigned identity resource ID for registry pulls and A2A.')
param identityResourceId string

@description('Container port.')
param targetPort int

@description('Non-secret runtime environment values.')
param environmentVariables array

resource app 'Microsoft.App/containerApps@2024-03-01' = {
  name: appName
  location: resourceGroup().location
  identity: {
    type: 'UserAssigned'
    userAssignedIdentities: {
      '${identityResourceId}': {}
    }
  }
  properties: {
    managedEnvironmentId: environmentId
    configuration: {
      activeRevisionsMode: 'Single'
      ingress: {
        external: false
        targetPort: targetPort
        transport: 'auto'
        allowInsecure: false
      }
      registries: [
        {
          server: registryServer
          identity: identityResourceId
        }
      ]
    }
    template: {
      containers: [
        {
          name: appName
          image: containerImage
          env: environmentVariables
          resources: {
            cpu: json('0.5')
            memory: '1Gi'
          }
        }
      ]
      scale: {
        minReplicas: 0
        maxReplicas: 3
      }
    }
  }
}
