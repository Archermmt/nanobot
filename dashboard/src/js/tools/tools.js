// Tools manager for handling tool call messages
import defaultTools from './default-mcp-tools.json'

/**
 * Get all available tools
 * @returns {Array} List of tools
 */
export function getMcpTools() {
  return defaultTools
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
  const tool = defaultTools.find(t => t.name === toolName)

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
 * Handle tool call messages from the backend
 * @param {Object} message - Tool call message object
 * @param {WebSocket} websocket - WebSocket instance to send responses
 */
export async function handleToolCallMessage(message, websocket) {
  console.log('📥 Tool call message received:', JSON.stringify(message))

  // Extract tool name and kwargs from message
  const toolName = message.name
  const toolKwargs = message.kwargs || {}

  console.log(`🔧 Tool call: ${toolName}`, toolKwargs)

  try {
    let result

    // Handle specific tools
    if (toolName === 'self_camera_take_photo') {
      // Capture photo from camera and get result
      result = await captureAndSendPhoto(toolKwargs)
    } else {
      // For other tools, execute normally
      result = await executeMcpTool(toolName, toolKwargs)
    }

    // Send success result
    const replyMessage = JSON.stringify({
      type: 'tool_call',
      name: toolName,
      kwargs: toolKwargs,
      result: result
    })

    console.log('📤 Sending tool call result:', replyMessage)
    websocket.send(replyMessage)
    console.log('✅ Tool result sent')

  } catch (error) {
    console.error('❌ Tool execution failed:', error)

    // Send error result
    const errorReply = JSON.stringify({
      type: 'tool_call',
      name: toolName,
      kwargs: toolKwargs,
      result: {
        error: error.message
      }
    })

    console.log('📤 Sending tool call error:', errorReply)
    websocket.send(errorReply)
  }
}

/**
 * Capture photo from camera and return result
 * @param {Object} kwargs - Tool arguments
 * @returns {Promise<Object>} Photo data with image_data, width, height
 */
async function captureAndSendPhoto(kwargs) {
  try {
    // Request camera access
    const stream = await navigator.mediaDevices.getUserMedia({
      video: { facingMode: 'user' },
      audio: false
    })

    // Create video element to capture frame
    const video = document.createElement('video')
    video.srcObject = stream
    await video.play()

    // Create canvas to capture image
    const canvas = document.createElement('canvas')
    canvas.width = video.videoWidth
    canvas.height = video.videoHeight
    const ctx = canvas.getContext('2d')
    ctx.drawImage(video, 0, 0)

    // Get image data as base64
    const imageData = canvas.toDataURL('image/jpeg', 0.95)

    // Stop camera stream
    stream.getTracks().forEach(track => track.stop())

    console.log('📸 Photo captured successfully')

    // Return photo data
    return {
      image_data: imageData,
      width: canvas.width,
      height: canvas.height
    }

  } catch (error) {
    console.error('❌ Failed to capture photo:', error)
    throw error
  }
}
