{
  "name": "medix_fluxo",
  "nodes": [
    {
      "parameters": {
        "httpMethod": "POST",
        "path": "medix",
        "respond": true,
        "responseData": "{ \"status\": \"success\", \"message\": \"Dados recebidos com sucesso!\" }"
      },
      "name": "Webhook",
      "type": "n8n-nodes-base.webhook",
      "typeVersion": 1,
      "position": [400, 300]
    },
    {
      "parameters": {
        "operation": "append",
        "spreadsheetId": "PASTE_YOUR_SPREADSHEET_ID",
        "sheetName": "Vendas",
        "data": "={{ $json }}",
        "options": {}
      },
      "name": "Google Sheets",
      "type": "n8n-nodes-base.googleSheets",
      "typeVersion": 1,
      "position": [600, 300],
      "credentials": {
        "googleSheetsOAuth2Api": {
          "id": "PASTE_YOUR_CREDENTIAL_ID",
          "name": "Google Sheets OAuth2 API"
        }
      }
    },
    {
      "parameters": {
        "responseData": "{ \"status\": \"success\", \"message\": \"Dados salvos com sucesso!\" }",
        "responseCode": 200
      },
      "name": "Respond to Webhook",
      "type": "n8n-nodes-base.respondToWebhook",
      "typeVersion": 1,
      "position": [800, 300]
    }
  ],
  "connections": {
    "Webhook": {
      "main": [
        [
          {
            "node": "Google Sheets",
            "type": "main",
            "index": 0
          }
        ]
      ]
    },
    "Google Sheets": {
      "main": [
        [
          {
            "node": "Respond to Webhook",
            "type": "main",
            "index": 0
          }
        ]
      ]
    }
  }
}
