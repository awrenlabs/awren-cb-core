# Awren Core — SDK Package

Python SDK for external developers to interact with Awren Core.

## Usage
```python
from awren_sdk import AwrenClient

client = AwrenClient("https://api.awren.ai", api_key="your-key")
entity = await client.create_entity("core:Organization", "Acme Corp")
```
