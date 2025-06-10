from anthropic import Anthropic
import os
from dotenv import load_dotenv

load_dotenv()

anthropic_client = Anthropic()

def create_message(content: str, role: str = "user") -> dict:
    """Create a properly formatted message for Anthropic API"""
    return {
        "role": role,
        "content": content
    }

async def call_anthropic(messages: list, 
                         available_tools: list = None, 
                         max_tokens: int = 1000, 
                         model: str = "claude-3-5-sonnet-20241022") -> object:
    """Make a call to Anthropic API with given parameters"""
    return anthropic_client.messages.create(
        model=model,
        max_tokens=max_tokens,
        messages=messages,
        tools=available_tools if available_tools else []
    )

def extract_response_text(response) -> str:
    """Extract text content from Anthropic API response"""
    response_text = ""
    if response.content and len(response.content) > 0:
        for content_block in response.content:
            if hasattr(content_block, 'text'):
                response_text += content_block.text
            elif hasattr(content_block, 'type') and content_block.type == 'text':
                response_text += str(content_block)
    return response_text

async def get_database_schema(session) -> str:
    """Get database schema from MCP session"""
    try:
        context_response = await session.read_resource("postgres://schema")
        if context_response.contents and len(context_response.contents) > 0:
            first_content = context_response.contents[0]
            if hasattr(first_content, 'text'):
                return str(first_content.text)
            else:
                return str(first_content)
        return ""
    except Exception as e:
        print(f"Warning: Could not read schema resource: {e}")
        return ""

async def get_available_tools(session) -> list:
    """Get available tools from MCP session"""
    tools_call = await session.list_tools()
    return [{
        "name": tool.name,
        "description": tool.description,
        "input_schema": tool.inputSchema
    } for tool in tools_call.tools]

async def planning_phase(prompt: str, context: str) -> str:
    """Phase 1: Generate execution plan"""
    planning_prompt = f"""You are a SQL query planner. Analyze the user's request and create a detailed execution plan.
                            User Request: {prompt}
                            Available Database Schema: {context}

                            Create a comprehensive plan in this EXACT format:

                            # CONTEXT:
                            [Elaborate on what the user is asking for - be specific about the data they want]

                            # OBJECTIVE:
                            [Clear statement of what needs to be accomplished, including specific table names and data points needed]

                            # INSTRUCTIONS:
                            [Step-by-step execution plan that includes:
                            1. Which table schemas to fetch (use postgres://<tablename>/schema)
                            2. What specific data to query for
                            3. How to structure the final response]

                            # EXAMPLE:
                            [Show an example of what the final answer should look like]

                            Make sure to complete ALL sections fully."""

    messages = [create_message(planning_prompt)]
    
    try:
        response = await call_anthropic(messages, max_tokens=1500)
        planning_text = extract_response_text(response)
        
        # Save planning output
        os.makedirs('data', exist_ok=True)
        with open('data/planning_log.txt', 'w+') as f:
            f.write(planning_text)
        
        return planning_text
        
    except Exception as e:
        raise Exception(f"Error in planning phase: {str(e)}")

async def execution_phase(prompt: str, planning_text: str, session, available_tools: list) -> str:
    """Phase 2: Execute the plan using tools"""
    
    execution_prompt = f"""You are a SQL execution assistant. Use the provided plan to complete the user's request.
                            ORIGINAL USER REQUEST: {prompt}

                            EXECUTION PLAN:
                            {planning_text}

                            Now execute this plan step by step:
                            1. Use the tools available to gather the required data
                            2. Follow the instructions from the plan
                            3. Provide a complete answer in the format specified in the EXAMPLE section

                            Begin execution now."""

    messages = [create_message(execution_prompt)]
    
    try:
        # Keep making API calls until no more tool calls are needed
        max_iterations = 10
        iteration = 0
        
        while iteration < max_iterations:
            iteration += 1
            
            # Make Claude API call
            response = await call_anthropic(messages, available_tools, max_tokens=2000)
            
            # Add assistant's response to conversation
            messages.append({
                "role": "assistant",
                "content": response.content
            })
            
            # Check if there are any tool calls to execute
            tool_calls_made = False
            tool_results = []
            
            for content in response.content:
                if hasattr(content, 'type') and content.type == 'tool_use':
                    tool_calls_made = True
                    tool_name = content.name
                    tool_args = content.input
                    
                    print(f"Calling tool: {tool_name} with args: {tool_args}")
                    
                    # Execute tool call
                    try:
                        result = await session.call_tool(tool_name, tool_args)
                        tool_results.append({
                            "type": "tool_result",
                            "tool_use_id": content.id,
                            "content": str(result.content) if hasattr(result, 'content') else str(result)
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
        
        # Extract final response
        final_response = extract_response_text(response)
        
        # Save execution log
        with open('data/execution_log.txt', 'w+') as f:
            f.write(final_response)
        
        return final_response
        
    except Exception as e:
        raise Exception(f"Error in execution phase: {str(e)}")

async def process_prompt(session, prompt: str) -> str:
    """Main function: Two-step process with planning and execution"""
    try:
        # Get prerequisites
        context = await get_database_schema(session)
        available_tools = await get_available_tools(session)
        
        planning_text = await planning_phase(prompt, context)
        
        final_result = await execution_phase(prompt, planning_text, session, available_tools)
        
        return final_result
        
    except Exception as e:
        error_msg = f"Error in process_prompt: {str(e)}"
        print(error_msg)
        return error_msg