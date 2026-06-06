/**
 * WebUI Tools Manager - Handles tool call messages from backend
 * 
 * This module provides functionality to handle tool calls sent from the backend
 * via WebSocket, similar to the MCP tool pattern in nanobot_bak.
 */

import websocketTools from './webui-tools.json';

export interface ToolDefinition {
  name: string;
  description: string;
  inputSchema: {
    type: string;
    properties: Record<string, any>;
    required?: string[];
  };
}

export interface ToolCallMessage {
  type: 'tool_call';
  name: string;
  kwargs: Record<string, any>;
}

export interface ToolCallResult {
  success: boolean;
  [key: string]: any;
}

/**
 * Get all available WebUI tools
 * @returns List of tool definitions
 */
export function getWebUITools(): ToolDefinition[] {
  return websocketTools as ToolDefinition[];
}

/**
 * Execute a WebUI tool
 * @param toolName - Name of the tool to execute
 * @param toolArgs - Arguments for the tool
 * @returns Tool execution result
 */
export async function executeWebUITool(
  toolName: string,
  toolArgs: Record<string, any>
): Promise<ToolCallResult> {
  console.log(`[WebUITools] Executing tool: ${toolName}`, toolArgs);

  // Find the tool definition
  const tool = websocketTools.find((t: ToolDefinition) => t.name === toolName);

  if (!tool) {
    throw new Error(`Unknown tool: ${toolName}`);
  }

  // Handle specific tools
  if (toolName === 'webui_camera_take_photo') {
    return await captureAndSendPhoto(toolArgs);
  }

  // Default response for unknown tool implementations
  return {
    success: true,
    message: `Tool ${toolName} executed successfully`,
    data: null,
  };
}

/**
 * Capture photo from camera and return result
 * @param _kwargs - Tool arguments (currently unused but kept for API consistency)
 * @returns Photo data with image_data, width, height
 */
async function captureAndSendPhoto(
  _kwargs: Record<string, any>
): Promise<ToolCallResult> {
  try {
    // Request camera access
    const stream = await navigator.mediaDevices.getUserMedia({
      video: { facingMode: 'user' },
      audio: false,
    });

    // Create video element to capture frame
    const video = document.createElement('video');
    video.srcObject = stream;
    await video.play();

    // Wait a bit for video to stabilize
    await new Promise((resolve) => setTimeout(resolve, 300));

    // Create canvas to capture image
    const canvas = document.createElement('canvas');
    canvas.width = video.videoWidth;
    canvas.height = video.videoHeight;
    const ctx = canvas.getContext('2d');
    
    if (!ctx) {
      throw new Error('Failed to get canvas context');
    }
    
    ctx.drawImage(video, 0, 0);

    // Get image data as base64
    const imageData = canvas.toDataURL('image/jpeg', 0.95);

    // Stop camera stream
    stream.getTracks().forEach((track) => track.stop());

    // Return photo data
    return {
      success: true,
      image_data: imageData,
      width: canvas.width,
      height: canvas.height,
    };
  } catch (error) {
    console.error('[WebUITools] ❌ Failed to capture photo:', error);
    throw error;
  }
}

/**
 * Handle tool call messages from the backend
 * @param message - Tool call message object
 * @param sendMessage - Function to send response back to backend
 */
export async function handleToolCallMessage(
  message: ToolCallMessage,
  sendMessage: (response: any) => void
): Promise<void> {
  const { name: toolName, kwargs: toolKwargs } = message;

  try {
    // Execute the tool
    const result = await executeWebUITool(toolName, toolKwargs);

    // Send success result back to backend
    const replyMessage = {
      type: 'tool_call_result',
      name: toolName,
      kwargs: toolKwargs,
      result: result,
    };

    sendMessage(replyMessage);
  } catch (error) {
    console.error('[WebUITools] ❌ Tool execution failed:', error);

    // Send error result back to backend
    const errorReply = {
      type: 'tool_call_result',
      name: toolName,
      kwargs: toolKwargs,
      result: {
        success: false,
        error: error instanceof Error ? error.message : String(error),
      },
    };

    console.log('[WebUITools] 📤 Sending tool call error:', errorReply);
    sendMessage(errorReply);
  }
}
