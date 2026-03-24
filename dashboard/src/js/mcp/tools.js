// MCP tools manager for handling MCP protocol messages
import defaultMcpTools from '../config/default-mcp-tools.json'

/**
 * Get all available MCP tools
 * @returns {Array} List of MCP tools
 */
export function getMcpTools() {
  return defaultMcpTools
}

/**
 * Execute an MCP tool
 * @param {string} toolName - Name of the tool to execute
 * @param {Object} toolArgs - Arguments for the tool
 * @returns {Promise<Object>} Tool execution result
 */
export async function executeMcpTool(toolName, toolArgs) {
  console.log(`Executing MCP tool: ${toolName}`, toolArgs)
  
  // Find the tool in default tools
  const tool = defaultMcpTools.find(t => t.name === toolName)
  
  if (!tool) {
    throw new Error(`Unknown tool: ${toolName}`)
  }
  
  // For now, return mock response from the tool definition
  if (tool.mockResponse) {
    return tool.mockResponse
  }
  
  // If no mock response, return success with empty result
  return {
    success: true,
    message: `Tool ${toolName} executed successfully`,
    data: null
  }
}

/**
 * Handle MCP messages from the backend
 * @param {Object} message - MCP message object
 * @param {WebSocket} websocket - WebSocket instance to send responses
 */
export function handleMCPMessage(message, websocket) {
  const payload = message.payload || {}
  console.log('📥 MCP message received:', JSON.stringify(message))
  
  if (payload.method === 'tools/list') {
    // Backend is requesting available tools
    const tools = getMcpTools()
    
    const replyMessage = JSON.stringify({
      type: 'mcp',
      message_id: `mcp_reply_${Date.now()}_${Math.random().toString(36).substr(2, 9)}`,
      sender_id: 'web_dashboard',
      chat_id: 'default_room',
      content: 'tools_list_response',
      media: [],
      metadata: {
        source: 'web_dashboard',
        timestamp: Date.now(),
        session_id: message.metadata?.session_id || 'default_session',
        payload: {
          jsonrpc: '2.0',
          id: payload.id,
          result: {
            tools: tools
          }
        }
      }
    })
    
    console.log('📤 Sending MCP tools list response:', replyMessage)
    websocket.send(replyMessage)
    console.log(`✅ Replied with ${tools.length} tools`)
    
  } else if (payload.method === 'tools/call') {
    // Backend is calling a tool
    const toolName = payload.params?.name
    const toolArgs = payload.params?.arguments
    
    console.log(`🔧 Calling tool: ${toolName}`, toolArgs)
    
    executeMcpTool(toolName, toolArgs)
      .then(result => {
        const replyMessage = JSON.stringify({
          type: 'mcp',
          message_id: `mcp_reply_${Date.now()}_${Math.random().toString(36).substr(2, 9)}`,
          sender_id: 'web_dashboard',
          chat_id: 'default_room',
          content: 'tool_call_response',
          media: [],
          metadata: {
            source: 'web_dashboard',
            timestamp: Date.now(),
            session_id: message.metadata?.session_id || 'default_session',
            payload: {
              jsonrpc: '2.0',
              id: payload.id,
              result: {
                content: [
                  {
                    type: 'text',
                    text: JSON.stringify(result)
                  }
                ],
                isError: false
              }
            }
          }
        })
        
        console.log('📤 Sending tool call result:', replyMessage)
        websocket.send(replyMessage)
      })
      .catch(error => {
        console.error('❌ Tool execution failed:', error.message)
        
        const errorReply = JSON.stringify({
          type: 'mcp',
          message_id: `mcp_reply_${Date.now()}_${Math.random().toString(36).substr(2, 9)}`,
          sender_id: 'web_dashboard',
          chat_id: 'default_room',
          content: 'tool_call_error',
          media: [],
          metadata: {
            source: 'web_dashboard',
            timestamp: Date.now(),
            session_id: message.metadata?.session_id || 'default_session',
            payload: {
              jsonrpc: '2.0',
              id: payload.id,
              error: {
                code: -32603,
                message: error.message
              }
            }
          }
        })
        
        console.log('📤 Sending tool call error:', errorReply)
        websocket.send(errorReply)
      })
      
  } else if (payload.method === 'initialize') {
    // Backend initialization request
    console.log('🔄 Received MCP initialize request:', payload.params)
    
    // Save vision analysis config if provided
    const visionConfig = payload?.params?.capabilities?.vision
    if (visionConfig && typeof visionConfig === 'object' && visionConfig.url && visionConfig.token) {
      const visionConfigStr = JSON.stringify(visionConfig)
      localStorage.setItem('mcp_vision_config', visionConfigStr)
      console.log('💾 Saved vision config:', visionConfigStr)
    } else {
      localStorage.removeItem('mcp_vision_config')
    }
    
    // Send initialize response
    const replyMessage = JSON.stringify({
      type: 'mcp',
      message_id: `mcp_reply_${Date.now()}_${Math.random().toString(36).substr(2, 9)}`,
      sender_id: 'web_dashboard',
      chat_id: 'default_room',
      content: 'initialize_response',
      media: [],
      metadata: {
        source: 'web_dashboard',
        timestamp: Date.now(),
        session_id: message.metadata?.session_id || 'default_session',
        payload: {
          jsonrpc: '2.0',
          id: payload.id,
          result: {
            protocolVersion: '2024-11-05',
            capabilities: {
              tools: {}
            },
            serverInfo: {
              name: 'WebDashboard',
              version: '1.0.0'
            }
          }
        }
      }
    })
    
    console.log('📤 Sending MCP initialize response:', replyMessage)
    websocket.send(replyMessage)
    
  } else {
    console.warn('⚠️ Unknown MCP method:', payload.method)
  }
}
