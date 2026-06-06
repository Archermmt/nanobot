/**
 * WebUI Tools 单元测试
 */

import { describe, it, expect, vi } from 'vitest';
import { getWebUITools, executeWebUITool, handleToolCallMessage } from '../tools/webui-tools';

describe('WebUI Tools', () => {
  describe('getWebUITools', () => {
    it('should return array of tool definitions', () => {
      const tools = getWebUITools();
      expect(Array.isArray(tools)).toBe(true);
      expect(tools.length).toBeGreaterThan(0);
    });

    it('should include webui_camera_take_photo tool', () => {
      const tools = getWebUITools();
      const cameraTool = tools.find((t: any) => t.name === 'webui_camera_take_photo');
      expect(cameraTool).toBeDefined();
      expect(cameraTool?.description).toContain('camera');
    });
  });

  describe('executeWebUITool', () => {
    it('should throw error for unknown tool', async () => {
      await expect(executeWebUITool('unknown_tool', {}))
        .rejects
        .toThrow('Unknown tool: unknown_tool');
    });

    it('should execute webui_camera_take_photo tool', async () => {
      // Mock getUserMedia
      const mockStream = {
        getTracks: vi.fn(() => [{ stop: vi.fn() }])
      };
      
      Object.defineProperty(global.navigator, 'mediaDevices', {
        value: {
          getUserMedia: vi.fn().mockResolvedValue(mockStream)
        },
        writable: true,
        configurable: true
      });

      // Mock HTMLMediaElement
      const mockVideo = {
        play: vi.fn().mockResolvedValue(undefined),
        videoWidth: 1920,
        videoHeight: 1080,
        srcObject: null
      };
      
      const originalCreateElement = document.createElement.bind(document);
      document.createElement = vi.fn((tag: string) => {
        if (tag === 'video') return mockVideo as any;
        if (tag === 'canvas') {
          return {
            width: 0,
            height: 0,
            getContext: vi.fn(() => ({
              drawImage: vi.fn()
            })),
            toDataURL: vi.fn(() => 'data:image/jpeg;base64,mock')
          } as any;
        }
        return originalCreateElement(tag);
      });

      const result = await executeWebUITool('webui_camera_take_photo', { question: 'test' });
      
      expect(result.success).toBe(true);
      expect(result.image_data).toContain('data:image/jpeg;base64');
      expect(result.width).toBe(1920);
      expect(result.height).toBe(1080);
    });
  });

  describe('handleToolCallMessage', () => {
    it('should handle successful tool execution', async () => {
      const mockSendMessage = vi.fn();
      const message = {
        type: 'tool_call' as const,
        name: 'webui_camera_take_photo',
        kwargs: { question: 'test' }
      };

      // Mock the tool execution
      Object.defineProperty(global.navigator, 'mediaDevices', {
        value: {
          getUserMedia: vi.fn().mockResolvedValue({
            getTracks: vi.fn(() => [{ stop: vi.fn() }])
          })
        },
        writable: true,
        configurable: true
      });

      await handleToolCallMessage(message, mockSendMessage);

      expect(mockSendMessage).toHaveBeenCalled();
      const response = mockSendMessage.mock.calls[0][0];
      expect(response.type).toBe('tool_call_result');
      expect(response.name).toBe('webui_camera_take_photo');
      expect(response.result.success).toBe(true);
    });

    it('should handle tool execution errors', async () => {
      const mockSendMessage = vi.fn();
      const message = {
        type: 'tool_call' as const,
        name: 'unknown_tool',
        kwargs: {}
      };

      await handleToolCallMessage(message, mockSendMessage);

      expect(mockSendMessage).toHaveBeenCalled();
      const response = mockSendMessage.mock.calls[0][0];
      expect(response.type).toBe('tool_call_result');
      expect(response.result.success).toBe(false);
      expect(response.result.error).toContain('Unknown tool');
    });
  });
});
