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

const emit = defineEmits(['send', 'upload-image', 'upload-audio', 'ws-status-change'])

const messages = ref<Message[]>([])
const isLoading = ref(false)
const sessionId = ref(`session_${Date.now()}`)
const currentAudio = ref<HTMLAudioElement | null>(null)

// WebSocket 连接相关状态
const wsUrl = ref('ws://localhost:8765')
const isConnected = ref(false)
const isConnecting = ref(false)
const connectionError = ref<string | null>(null)

let ws: WebSocket | null = null

// 计算属性：连接状态文本
const connectionStatus = computed(() => {
  if (isConnecting.value) return '正在连接...'
  if (isConnected.value) return '已连接'
  if (connectionError.value) return `连接失败: ${connectionError.value}`
  return '未连接'
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
  }
  
  ws.onmessage = (event) => {
    try {
      const data = JSON.parse(event.data)
      console.log('📥 Received message:', data)
      
      if (data.type === 'message') {
        messages.value.push({
          role: 'assistant',
          content: data.content || 'Received message',
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
    connectionError.value = '连接错误'
    
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
  
  // 通过 WebSocketChannel 发送消息
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
    
    // 设置超时处理
    setTimeout(() => {
      if (isLoading.value) {
        isLoading.value = false
        messages.value.push({
          role: 'system',
          content: 'Message sent but no response received',
          timestamp: Date.now()
        })
      }
    }, 10000)
  
  } else {
    // WebSocket未连接时的错误提示
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

// 不再在 mounted 时自动连接
onMounted(() => {
  // 初始化时不自动连接
})

onUnmounted(() => {
  ws?.close()
  stopAudio()
})
</script>

<template>
  <div class="flex flex-col h-full">
    <!-- WebSocket 连接控制面板 -->
    <div class="border-b bg-white p-4">
      <div class="flex flex-col space-y-3">
        <div class="flex items-center space-x-3">
          <label class="text-sm font-medium text-gray-700 whitespace-nowrap">WebSocket URL:</label>
          <input
            v-model="wsUrl"
            type="text"
            :disabled="isConnecting || isConnected"
            class="flex-1 px-3 py-2 border border-gray-300 rounded-md text-sm focus:outline-none focus:ring-2 focus:ring-blue-500 focus:border-blue-500 disabled:bg-gray-100 disabled:text-gray-500"
            placeholder="请输入 WebSocket 地址，例如: ws://localhost:8765/ws"
          />
        </div>
        
        <div class="flex items-center space-x-3">
          <button
            v-if="!isConnected"
            @click="connectWebSocket"
            :disabled="isConnecting || !wsUrl.trim()"
            class="px-4 py-2 bg-blue-600 text-white rounded-md hover:bg-blue-700 focus:outline-none focus:ring-2 focus:ring-blue-500 focus:ring-offset-2 disabled:bg-gray-400 disabled:cursor-not-allowed transition-colors"
          >
            {{ isConnecting ? '连接中...' : '连接' }}
          </button>
          
          <button
            v-if="isConnected"
            @click="disconnectWebSocket"
            class="px-4 py-2 bg-red-600 text-white rounded-md hover:bg-red-700 focus:outline-none focus:ring-2 focus:ring-red-500 focus:ring-offset-2 transition-colors"
          >
            断开连接
          </button>
          
          <div class="flex items-center space-x-2">
            <div 
              class="w-3 h-3 rounded-full" 
              :class="{
                'bg-yellow-500': isConnecting,
                'bg-green-500': isConnected,
                'bg-red-500': connectionError,
                'bg-gray-400': !isConnecting && !isConnected && !connectionError
              }"
            ></div>
            <span 
              class="text-sm" 
              :class="{
                'text-yellow-600': isConnecting,
                'text-green-600': isConnected,
                'text-red-600': connectionError,
                'text-gray-500': !isConnecting && !isConnected && !connectionError
              }"
            >
              {{ connectionStatus }}
            </span>
          </div>
        </div>
        
        <div v-if="connectionError" class="text-sm text-red-600">
          错误: {{ connectionError }}
        </div>
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
      @upload-image="handleImageUpload"
      @upload-audio="handleAudioUpload"
    />
  </div>
</template>
