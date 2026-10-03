@description('Container App resource name.')
param appName string

@description('Immutable ACR image reference containing @sha256:.')
param containerImage string

@description('ACA environment resource ID.')
param environmentId string

@description('Registry hostname.')
param registryServer string

@description('User-assigned identity resource ID for registry pulls and Key Vault.')
param identityResourceId string

@description('Non-secret runtime environment values.')
param environmentVariables array

@description('Full Key Vault secret URI for the OpenAI key.')
param openAiSecretUri string

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
        external: true
        targetPort: 8080
        transport: 'auto'
        allowInsecure: false
      }
      registries: [
        {
          server: registryServer
          identity: identityResourceId
        }
      ]
      secrets: [
        {
          name: 'openai-api-key'
          keyVaultUrl: openAiSecretUri
          identity: identityResourceId
        }
      ]
    }
    template: {
      containers: [
        {
          name: appName
          image: containerImage
          env: concat(environmentVariables, [
            {
              name: 'OPENAI_API_KEY'
              secretRef: 'openai-api-key'
            }
          ])
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
