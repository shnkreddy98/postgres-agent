import asyncio
from typing import Optional
from contextlib import AsyncExitStack

from mcp import ClientSession, StdioServerParameters
from mcp.client.stdio import stdio_client

from anthropic import Anthropic
from dotenv import load_dotenv

load_dotenv()

class MCPClient:
    def __init__(self):
        # Initialize session and client objects
        self.session: Optional[ClientSession] = None
        self.exit_stack = AsyncExitStack()
        self.anthropic = Anthropic()

    async def connect_to_server(self, server_script_path: str):
        """Connect to an MCP server
        
        Args:
            server_script_path: Path to the server script (.py or .js)
        """
        is_python = server_script_path.endswith('.py')
        is_js = server_script_path.endswith('.js')
        if not (is_python or is_js):
            raise ValueError("Server script must be a .py or .js file")
            
        command = "python" if is_python else "node"
        server_params = StdioServerParameters(
            command=command,
            args=[server_script_path],
            env=None
        )
        
        stdio_transport = await self.exit_stack.enter_async_context(stdio_client(server_params))
        self.stdio, self.write = stdio_transport
        self.session = await self.exit_stack.enter_async_context(ClientSession(self.stdio, self.write))
        
        await self.session.initialize()
        
        # List available tools
        response = await self.session.list_tools()
        tools = response.tools
        print("\nConnected to server with tools:", [tool.name for tool in tools])

    async def process_query(self, query: str) -> str:
        """Process a query using Claude and available tools"""
        # TODO: hard coded nba_players table for now
        try:
            context_response = await self.session.read_resource("schema://nba_players")
            context = str(context_response.contents[0].text) if context_response.contents else ""
        except Exception as e:
            print(f"Warning: Could not read schema resource: {e}")
            context = ""

        query_with_context = query + "\n\nDatabase schema context:\n" + context

        messages = [
            {
                "role": "user",
                "content": query_with_context
            }
        ]

        response = await self.session.list_tools()
        available_tools = [{ 
            "name": tool.name,
            "description": tool.description,
            "input_schema": tool.inputSchema
        } for tool in response.tools]

        # Keep making Claude API calls until no more tool calls are needed
        max_iterations = 10  # Prevent infinite loops
        iteration = 0
        
        while iteration < max_iterations:
            iteration += 1
            
            # Make Claude API call
            response = self.anthropic.messages.create(
                model="claude-3-5-sonnet-20241022",
                max_tokens=1000,
                messages=messages,
                tools=available_tools
            )

            # Add assistant's response to conversation
            messages.append({
                "role": "assistant",
                "content": response.content
            })

            # Check if there are any tool calls to execute
            tool_calls_made = False
            tool_results = []
            
            for content in response.content:
                if content.type == 'tool_use':
                    tool_calls_made = True
                    tool_name = content.name
                    tool_args = content.input
                    
                    print(f"[Calling tool {tool_name} with args {tool_args}]")
                    
                    # Execute tool call
                    try:
                        result = await self.session.call_tool(tool_name, tool_args)
                        tool_results.append({
                            "type": "tool_result",
                            "tool_use_id": content.id,
                            "content": str(result.content)
                        })
                    except Exception as e:
                        tool_results.append({
                            "type": "tool_result",
                            "tool_use_id": content.id,
                            "content": f"Error: {str(e)}",
                            "is_error": True
                        })

            # If no tool calls were made, we're done
            if not tool_calls_made:
                break
                
            # Add tool results to the conversation
            if tool_results:
                messages.append({
                    "role": "user",
                    "content": tool_results
                })

        # Extract final text response
        final_response = []
        for content in response.content:
            if content.type == 'text':
                final_response.append(content.text)
                
        return "\n".join(final_response) if final_response else "No text response received."

    async def chat_loop(self):
        """Run an interactive chat loop"""
        print("\nMCP Client Started!")
        print("Type your queries or 'quit' to exit.")
        
        while True:
            try:
                query = input("\nQuery: ").strip()
                
                if query.lower() == 'quit':
                    break
                    
                response = await self.process_query(query)
                print("\n" + response)
                    
            except Exception as e:
                print(f"\nError: {str(e)}")
    
    async def cleanup(self):
        """Clean up resources"""
        await self.exit_stack.aclose()

async def main():
    if len(sys.argv) < 2:
        print("Usage: python client.py <path_to_server_script>")
        sys.exit(1)
        
    client = MCPClient()
    try:
        await client.connect_to_server(sys.argv[1])
        await client.chat_loop()
    finally:
        await client.cleanup()

if __name__ == "__main__":
    import sys
    asyncio.run(main())