# fedsrv-cli

# Configuration
  
`config.json` should be stored in the same directory as the executable.

## config.json Contents

```json
{
  "mcp":
  {
    "grok-ai-config":
    {
      "api_key"  :  "<Your API Key>",
      "endpoint" :  "https://api.x.ai/v1",
      "model"    :  "grok-3"
    }
    "mcp-service-config":
    {
      "api_key"  :  "<Your API Key>",
      "endpoint" :  "<Your Endpoint>" 
    }
  }
}
```
 

# Commands

- `help`: Lists all commands and a usage summary of each.
  
- `mcp`: Enters a mode that communicates directly with a FedSrv MCP Service via Natural Language.
  - This is configured via the `fedsrv-mcp-main` section in `config.json`.
  - Anything typed in, when inside this mode, is treated as text sent directly to the MCP Service. Therefore Natural Language should be used.
  - `exit` and `back` are reserved words. If either is entered by itself, `fedsrv-mcp-main` will be exited.
      - *Special Case:* To "escape" either of these words, thereby using just one of them, alone, as a single-word command intended for the MCP service, wrap them in Single or Double Quotes. This will likely be rare.
  - *Usage Example*:
    ```bash
    fedsrv-cli> mcp

    Now entering MCP Mode. In this mode, all text entered will be sent directly to the MCP as-is.

    Connecting to Grok AI Endpoint "Big LLM": SUCCESS
    Connecting to MCP AI Endpoint "Little LLM": SUCCESS

    To leave MCP Mode, type exit or back (as the only thing on a line).

    fedsrv-cli|mcp> How many Wells have Seismic Data created within the past year? Can you List them?

    (MCP Response:) There are 3 wells within the past year that have Seismic Data. They are:
                      WELL-001 with 15 Seismic Data Records
                      WELL-002 with 13 Seismic Data Records
                      WELL-009 with 3 Seismic Data Records

    fedsrv-cli|mcp> exit

    Connection to Grok AI Endpoint "Big LLM" closed.
    Connecting to MCP AI Endpoint "Little LLM" closed.

    fedsrv-cli>
    
    ```

    
  
  
