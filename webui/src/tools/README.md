# WebUI Tools - 前端工具调用处理

## 概述

WebUI Tools 模块允许后端通过 WebSocket 向前端发送工具调用请求,前端执行后返回结果。这种机制使得 AI Agent 可以调用浏览器端的能力,如摄像头拍照、文件选择等。

## 架构

```
Backend (Python)                    Frontend (TypeScript)
     |                                      |
     |  1. WebSocket connects               |
     |  2. Send "ready" event               |
     |------------------------------------->|
     |                                      |
     |  3. Auto-register tools              |
     |<-------------------------------------|
     |   (register_extern_tools command)    |
     |                                      |
     |  4. Send tool_call event             |
     |------------------------------------->|
     |                                      |
     |                          5. Execute tool (e.g., camera)
     |                                      |
     |                          6. Send tool_call_result
     |<-------------------------------------|
     |                                      |
     |  7. Process result in agent loop     |
```

## 文件结构

```
webui/src/tools/
├── webui-tools.ts          # 工具调用处理逻辑
├── webui-tools.json        # 可用工具定义
└── README.md               # 本文档
```

## 自动工具注册

当 WebSocket 连接建立后,前端会自动向后端发送工具注册请求。

**注册流程:**
1. WebSocket 连接打开 (`handleOpen`)
2. 调用 `registerWebUITools()` 方法
3. 发送 `/register_extern_tools` 命令到后端
4. 后端接收并注册可用工具列表

**代码位置:**
- `nanobot-client.ts` 中的 `handleOpen()` 方法
- `nanobot-client.ts` 中的 `registerWebUITools()` 方法

**注意事项:**
- 工具注册在每次连接建立时自动执行
- 包括重连后也会重新注册
- 确保后端支持 `/register_extern_tools` 命令

## 添加工具

### 1. 在 `webui-tools.json` 中定义工具

```json
{
  "name": "camera_take_photo",
  "description": "Take a photo using the device's camera...",
  "inputSchema": {
    "type": "object",
    "properties": {
      "question": {
        "type": "string",
        "description": "Optional question to guide the photo analysis"
      }
    },
    "required": []
  }
}
```

### 2. 在 `webui-tools.ts` 中实现工具

```typescript
export async function executeWebUITool(
  toolName: string,
  toolArgs: Record<string, any>
): Promise<ToolCallResult> {
  if (toolName === 'camera_take_photo') {
    return await captureAndSendPhoto(toolArgs);
  }
  
  // 其他工具...
}
```

### 3. 后端发送工具调用

后端可以通过 WebSocket 发送以下格式的消息:

```python
{
    "event": "tool_call",
    "chat_id": "websocket:abc123",
    "name": "camera_take_photo",
    "kwargs": {
        "question": "describe what you see"
    }
}
```

### 4. 前端自动处理并返回结果

前端会自动:
1. 接收 `tool_call` 事件
2. 执行对应的工具函数
3. 将结果通过 `tool_call_result` 发送回后端

```python
{
    "type": "tool_call_result",
    "name": "camera_take_photo",
    "kwargs": {"question": "describe what you see"},
    "result": {
        "success": true,
        "image_data": "data:image/jpeg;base64,...",
        "width": 1920,
        "height": 1080
    }
}
```

## 内置工具

### camera_take_photo

使用设备摄像头拍照并返回图片数据。

**参数:**
- `question` (可选): 引导照片分析的问题

**返回:**
```typescript
{
  success: boolean;
  image_data: string;  // base64 data URL
  width: number;
  height: number;
}
```

**使用示例:**

用户说: "拍张照片看看你看到了什么"

AI 会:
1. 调用 `camera_take_photo` 工具
2. 获取照片数据
3. 分析照片内容并回复用户

## 扩展新工具

### 示例: 添加文件选择器

1. **定义工具** (`webui-tools.json`):
```json
{
  "name": "file_picker",
  "description": "Open a file picker dialog and return selected file",
  "inputSchema": {
    "type": "object",
    "properties": {
      "accept": {
        "type": "string",
        "description": "Accepted file types, e.g., 'image/*,.pdf'"
      }
    }
  }
}
```

2. **实现工具** (`webui-tools.ts`):
```typescript
async function pickFile(kwargs: Record<string, any>): Promise<ToolCallResult> {
  return new Promise((resolve, reject) => {
    const input = document.createElement('input');
    input.type = 'file';
    input.accept = kwargs.accept || '*';
    
    input.onchange = async (e) => {
      const file = (e.target as HTMLInputElement).files?.[0];
      if (!file) {
        resolve({ success: false, error: 'No file selected' });
        return;
      }
      
      const reader = new FileReader();
      reader.onload = () => {
        resolve({
          success: true,
          file_name: file.name,
          file_type: file.type,
          file_size: file.size,
          data_url: reader.result as string
        });
      };
      reader.readAsDataURL(file);
    };
    
    input.click();
  });
}
```

3. **注册工具**:
```typescript
if (toolName === 'file_picker') {
  return await pickFile(toolArgs);
}
```

## 调试

启用 WebSocket 调试日志:

```javascript
localStorage.setItem('nanobot_debug_ws', '1');
```

查看控制台输出:
```
[NanobotClient] 🛠️ Received tool call: { event: "tool_call", name: "camera_take_photo", ... }
[WebUITools] 🔧 Tool call: camera_take_photo { question: "describe what you see" }
[WebUITools] 📸 Photo captured successfully
[WebUITools] 📤 Sending tool call result: { type: "tool_call_result", ... }
```

## 注意事项

1. **权限**: 某些工具(如摄像头)需要用户授权
2. **异步**: 所有工具都是异步执行的
3. **错误处理**: 工具执行失败时会返回错误信息
4. **安全性**: 工具在前端沙箱环境中运行,无法访问系统资源

## 与 nanobot_bak 的对比

| 特性 | nanobot_bak | nanobot (当前) |
|------|-------------|----------------|
| 工具定义 | JSON 文件 | JSON 文件 |
| 消息类型 | `tool_call` | `tool_call` |
| 响应类型 | `tool_call` | `tool_call_result` |
| 集成方式 | Chat.vue 手动处理 | NanobotClient 自动处理 |
| 可扩展性 | 需要在 Vue 组件中添加 | 只需修改 webui-tools.ts |

当前实现更加模块化,工具逻辑与 UI 组件分离,便于维护和扩展。
