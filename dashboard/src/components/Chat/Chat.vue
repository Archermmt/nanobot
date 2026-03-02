<script setup lang="ts">
import { ref, onMounted, onUnmounted, computed } from 'vue'
import MessageList from './MessageList.vue'
import ChatInput from './ChatInput.vue'

interface Message {
  role: 'user' | 'assistant' | 'system'
  content: string
  timestamp: number
  imageUrl?: string
  audioUrl?: string
}

const emit = defineEmits(['send', 'new-chat', 'clear-chat', 'upload-image', 'upload-audio', 'upload-file', 'ws-status-change', 'send-status', 'status-update'])

const messages = ref<Message[]>([])
const isLoading = ref(false)
const sessionId = ref(`session_${Date.now()}`)
const currentAudio = ref<HTMLAudioElement | null>(null)
const currentTimeoutId = ref<number | null>(null)

// WebSocket connection related state
const wsUrl = ref('ws://localhost:8765')
const isConnected = ref(false)
const isConnecting = ref(false)
const connectionError = ref<string | null>(null)

let ws: WebSocket | null = null

// 计算 property: connection status text
const connectionStatus = computed(() => {
  if (isConnecting.value) return 'Connecting...'
  if (isConnected.value) return 'Connected'
  if (connectionError.value) return `Connection failed: ${connectionError.value}`
  return 'Disconnected'
})

const connectWebSocket = () => {
  if (isConnecting.value || isConnected.value) return

  isConnecting.value = true
  connectionError.value = null

  // 发出状态变化事件
  emit('ws-status-change', {
    isConnected: false,
    isConnecting: true,
    url: wsUrl.value
  })

  ws = new WebSocket(wsUrl.value)

  ws.onopen = () => {
    console.log('✅ WebSocket connected to WebSocketChannel')
    isConnecting.value = false
    isConnected.value = true
    connectionError.value = null

    // 发出状态变化事件
    emit('ws-status-change', {
      isConnected: true,
      isConnecting: false,
      url: wsUrl.value
    })

    // 发送认证信息（如果需要）
    if (ws) {
      const authMsg = {
        type: 'auth',
        token: 'your_auth_token_here'
      }
      ws.send(JSON.stringify(authMsg))
    }

    // 连接成功后自动请求状态
    console.log('🔗 WebSocket connected, requesting status...')
    if (ws) {
      const statusMsg = {
        type: 'message',
        message_id: `msg_${Date.now()}_${Math.random().toString(36).substr(2, 9)}`,
        sender_id: 'web_user',
        chat_id: 'default_room',
        content: '/status',
        media: [],
        metadata: {
          source: 'web_dashboard',
          timestamp: Date.now(),
          session_id: sessionId.value
        }
      }
      ws.send(JSON.stringify(statusMsg))
    }
  }

  ws.onmessage = (event) => {
    try {
      const data = JSON.parse(event.data)
      console.log('📥 Received message:', data)

      // Clear timeout when receiving any message
      if (currentTimeoutId.value) {
        clearTimeout(currentTimeoutId.value)
        currentTimeoutId.value = null
      }

      if (data.type === 'message') {
        // Check if this is a status response
        if (data.content && data.content.includes('mode') && data.content.includes('price')) {
          // This looks like a status update, emit it for StatusBar
          try {
            const statusData = JSON.parse(data.content)
            emit('status-update', statusData)
          } catch (e) {
            console.log('Status message content:', data.content)
          }
        }

        messages.value.push({
          role: 'assistant',
          content: data.content || 'Message received',
          timestamp: Date.now()
        })
        isLoading.value = false
      } else if (data.type === 'heartbeat') {
        // 回复心跳
        if (ws) {
          const heartbeatResponse = {
            type: 'heartbeat_response',
            timestamp: Date.now()
          }
          ws.send(JSON.stringify(heartbeatResponse))
        }
      } else if (data.type === 'error') {
        messages.value.push({
          role: 'system',
          content: `Error: ${data.message || data.data}`,
          timestamp: Date.now()
        })
        isLoading.value = false
      }
    } catch (e) {
      console.error('Failed to parse message:', e)
    }
  }

  ws.onclose = () => {
    console.log('WebSocket disconnected')
    isConnecting.value = false
    isConnected.value = false

    // 发出状态变化事件
    emit('ws-status-change', {
      isConnected: false,
      isConnecting: false,
      url: wsUrl.value
    })

    // 不再自动重连，让用户手动控制
  }

  ws.onerror = (error) => {
    console.error('WebSocket error:', error)
    isConnecting.value = false
    isConnected.value = false
    connectionError.value = 'Connection error'

    // 发出状态变化事件
    emit('ws-status-change', {
      isConnected: false,
      isConnecting: false,
      url: wsUrl.value
    })
  }
}

const disconnectWebSocket = () => {
  if (ws) {
    ws.close()
    ws = null
  }
  isConnected.value = false
  isConnecting.value = false

  // 发出状态变化事件
  emit('ws-status-change', {
    isConnected: false,
    isConnecting: false,
    url: wsUrl.value
  })
}

const sendMessage = async (text: string) => {
  const userMessage: Message = {
    role: 'user',
    content: text,
    timestamp: Date.now()
  }

  messages.value.push(userMessage)
  isLoading.value = true

  // Send message through WebSocketChannel
  if (ws && ws.readyState === WebSocket.OPEN) {
    const messageData = {
      type: 'message',
      message_id: `msg_${Date.now()}_${Math.random().toString(36).substr(2, 9)}`,
      sender_id: 'web_user',
      chat_id: 'default_room',
      content: text,
      media: [],
      metadata: {
        source: 'web_dashboard',
        timestamp: Date.now(),
        session_id: sessionId.value
      }
    }

    console.log('📤 Sending message:', messageData)
    ws.send(JSON.stringify(messageData))

    // Set timeout: if no response within 30 seconds, stop loading
    const timeoutId = setTimeout(() => {
      if (isLoading.value) {
        isLoading.value = false
        console.warn('No response received within 30 seconds')
      }
    }, 30000)

    // Store timeout ID in a ref so we can clear it on message receive
    currentTimeoutId.value = timeoutId

  } else {
    // Error prompt when WebSocket is not connected
    messages.value.push({
      role: 'system',
      content: 'WebSocket not connected. Please connect first.',
      timestamp: Date.now()
    })
    isLoading.value = false
  }
}

const handleImageUpload = async (imageData: string) => {
  // Add image to messages
  messages.value.push({
    role: 'user',
    content: 'Uploaded an image',
    timestamp: Date.now(),
    imageUrl: imageData
  })

  // Send to backend (would need backend support for image processing)
  console.log('Image uploaded:', imageData.substring(0, 50) + '...')
}

const handleAudioUpload = async (audioData: { data: string; type: string; isRecording?: boolean }) => {
  // Add audio to messages
  messages.value.push({
    role: 'user',
    content: audioData.isRecording ? 'Recorded voice message' : 'Uploaded audio',
    timestamp: Date.now(),
    audioUrl: audioData.data
  })

  console.log('Audio uploaded:', audioData.type)
}

const handleFileUpload = async (fileData: { data: string; type: string; name: string }) => {
  // Add file to messages
  messages.value.push({
    role: 'user',
    content: `Uploaded file: ${fileData.name}`,
    timestamp: Date.now()
  })

  console.log('File uploaded:', fileData.name)
}

const handleSendStatus = () => {
  const userMessage: Message = {
    role: 'user',
    content: '/status',
    timestamp: Date.now()
  }
  messages.value.push(userMessage)

  if (ws && ws.readyState === WebSocket.OPEN) {
    const statusMsg = {
      type: 'message',
      message_id: `msg_${Date.now()}_${Math.random().toString(36).substr(2, 9)}`,
      sender_id: 'web_user',
      chat_id: 'default_room',
      content: '/status',
      media: [],
      metadata: {
        source: 'web_dashboard',
        timestamp: Date.now(),
        session_id: sessionId.value
      }
    }
    console.log('📤 Sending /status command:', statusMsg)
    ws.send(JSON.stringify(statusMsg))
  } else {
    messages.value.push({
      role: 'system',
      content: 'WebSocket not connected. Please connect first.',
      timestamp: Date.now()
    })
  }
}

// Expose handleSendStatus to parent component
defineExpose({
  handleSendStatus
})

const handleNewChat = () => {
  const userMessage: Message = {
    role: 'user',
    content: '/new',
    timestamp: Date.now()
  }
  messages.value.push(userMessage)

  if (ws && ws.readyState === WebSocket.OPEN) {
    const newChatMsg = {
      type: 'message',
      message_id: `msg_${Date.now()}_${Math.random().toString(36).substr(2, 9)}`,
      sender_id: 'web_user',
      chat_id: 'default_room',
      content: '/new',
      media: [],
      metadata: {
        source: 'web_dashboard',
        timestamp: Date.now(),
        session_id: sessionId.value
      }
    }
    console.log('📤 Sending /new command:', newChatMsg)
    ws.send(JSON.stringify(newChatMsg))
  } else {
    messages.value.push({
      role: 'system',
      content: 'WebSocket not connected. Please connect first.',
      timestamp: Date.now()
    })
  }
}

const handleClearChat = () => {
  const userMessage: Message = {
    role: 'user',
    content: '/clear',
    timestamp: Date.now()
  }
  messages.value.push(userMessage)

  if (ws && ws.readyState === WebSocket.OPEN) {
    const clearMsg = {
      type: 'message',
      message_id: `msg_${Date.now()}_${Math.random().toString(36).substr(2, 9)}`,
      sender_id: 'web_user',
      chat_id: 'default_room',
      content: '/clear',
      media: [],
      metadata: {
        source: 'web_dashboard',
        timestamp: Date.now(),
        session_id: sessionId.value
      }
    }
    console.log('📤 Sending /clear command:', clearMsg)
    ws.send(JSON.stringify(clearMsg))
  } else {
    messages.value.push({
      role: 'system',
      content: 'WebSocket not connected. Please connect first.',
      timestamp: Date.now()
    })
  }
}

const playAudio = (audioUrl: string) => {
  currentAudio.value = new Audio(audioUrl)
  currentAudio.value.play()
}

const stopAudio = () => {
  if (currentAudio.value) {
    currentAudio.value.pause()
    currentAudio.value = null
  }
}

// No longer automatically connect on mounted
onMounted(() => {
  // Don't automatically connect on initialization
})

onUnmounted(() => {
  // Clear any pending timeout
  if (currentTimeoutId.value) {
    clearTimeout(currentTimeoutId.value)
  }
  ws?.close()
  stopAudio()
})
</script>

<template>
  <div class="flex flex-col h-full">
    <!-- WebSocket Connection Control Panel -->
    <div class="border-b-4 border-gray-700 bg-gray-800 p-3 pixel-font">
      <div class="flex items-center space-x-3 flex-wrap gap-2">
        <label class="text-xs font-bold text-gray-300 whitespace-nowrap">WebSocket url:</label>
        <input
          v-model="wsUrl"
          type="text"
          :disabled="isConnecting || isConnected"
          class="nes-input flex-1 min-w-[200px] max-w-[400px] text-xs py-1 px-2 border-2 border-gray-600 bg-gray-900 text-gray-300 disabled:bg-gray-700 disabled:text-gray-500"
          placeholder="ws://localhost:8765"
        />

        <button
          v-if="!isConnected"
          @click="connectWebSocket"
          :disabled="isConnecting || !wsUrl.trim()"
          class="nes-btn is-primary text-xs px-3 py-1"
        >
          {{ isConnecting ? 'Connecting...' : 'Connect' }}
        </button>

        <button
          v-if="isConnected"
          @click="disconnectWebSocket"
          class="nes-btn is-danger text-xs px-3 py-1"
        >
          Disconnect
        </button>
      </div>

        <div v-if="connectionError" class="text-xs text-red-500">
          Error: {{ connectionError }}
        </div>
    </div>

    <!-- Messages -->
    <MessageList
      :messages="messages"
      :isLoading="isLoading"
      @play-audio="playAudio"
      @stop-audio="stopAudio"
    />

    <!-- Input -->
    <ChatInput
      :isLoading="isLoading"
      :disabled="!isConnected"
      @send="sendMessage"
      @new-chat="handleNewChat"
      @clear-chat="handleClearChat"
      @upload-image="handleImageUpload"
      @upload-audio="handleAudioUpload"
      @upload-file="handleFileUpload"
      @send-status="handleSendStatus"
    />
  </div>
</template>
