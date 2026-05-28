import unittest

import httpx

from data_discovery.client import CollateAIClient, _parse_mcp_response


class FakeMCP:
    def __init__(self):
        self.called_with = None

    def call_tool(self, name, arguments):
        self.called_with = (name, arguments)
        return {"results": []}


class FakeSdkClient:
    def __init__(self):
        self.mcp = FakeMCP()


class ClientTests(unittest.TestCase):
    def test_converts_string_tool_name_to_sdk_enum(self):
        sdk = FakeSdkClient()
        client = CollateAIClient(sdk)
        client.call_tool("search_metadata", {"query": "s18"})

        tool_name, arguments = sdk.mcp.called_with
        self.assertEqual(tool_name.value, "search_metadata")
        self.assertEqual(arguments, {"query": "s18"})

    def test_parses_sse_jsonrpc_response(self):
        response = httpx.Response(
            200,
            headers={"content-type": "text/event-stream;charset=utf-8"},
            text='data: {"jsonrpc":"2.0","id":"1","result":{"tools":[]}}\n\n',
        )
        self.assertEqual(_parse_mcp_response(response), {"jsonrpc": "2.0", "id": "1", "result": {"tools": []}})


if __name__ == "__main__":
    unittest.main()
