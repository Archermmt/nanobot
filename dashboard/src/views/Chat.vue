<script setup lang="ts">
import { ref, onMounted, onUnmounted } from 'vue'
import { marked } from 'marked'

interface Message {
  role: 'user' | 'assistant' | 'system'
  content: string
  timestamp: number
  imageUrl?: string
}

const messages = ref<Message[]>([])
const input = ref('')
const isLoading = ref(false)
const sessionId = ref(`session_${Date.now()}`)

let ws: WebSocket | null = null

const connectWebSocket = () => {
  // Connect to WebSocketChannel server address
  const wsUrl = `ws://localhost:18790/ws`
  ws = new WebSocket(wsUrl)
  
  ws.onopen = () => {
    console.log('✅ WebSocket connected to WebSocketChannel')
    // 发送认证信息（如果需要）
    if (ws) {
      const authMsg = {
        type: 'auth',
        token: 'your_auth_token_here'  // 根据实际配置调整
      }
      ws.send(JSON.stringify(authMsg))
    }
  }
  
  ws.onmessage = (event) => {
    try {
      const data = JSON.parse(event.data)
      console.log('📥 Received message:', data)
      
      if (data.type === 'message') {
        // Handle messages from WebSocketChannel
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
    // Reconnect after 2 seconds
    setTimeout(connectWebSocket, 2000)
  }
  
  ws.onerror = (error) => {
    console.error('WebSocket error:', error)
  }
}

const sendMessage = async () => {
  if (!input.value.trim() || isLoading.value) return
  
  const userMessage: Message = {
    role: 'user',
    content: input.value,
    timestamp: Date.now()
  }
  
  messages.value.push(userMessage)
  const messageText = input.value
  input.value = ''
  isLoading.value = true
  
  // Send message through WebSocketChannel
  if (ws && ws.readyState === WebSocket.OPEN) {
    const messageData = {
      type: 'message',
      message_id: `msg_${Date.now()}_${Math.random().toString(36).substr(2, 9)}`,
      sender_id: 'web_user',  // 前端用户标识
      chat_id: 'default_room',  // 聊天室ID
      content: messageText,
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
    }, 10000) // 10秒超时
  
  } else {
    // Error prompt when WebSocket is not connected
    messages.value.push({
      role: 'system',
      content: 'WebSocket not connected. Please wait for reconnection.',
      timestamp: Date.now()
    })
    isLoading.value = false
  }
}

const renderMarkdown = (text: string) => {
  return marked.parse(text)
}

onMounted(() => {
  connectWebSocket()
})

onUnmounted(() => {
  ws?.close()
})
</script>

<template>
  <div class="flex flex-col h-screen max-w-4xl mx-auto">
    <!-- Header -->
    <header class="bg-white shadow-sm border-b px-6 py-4">
      <h1 class="text-xl font-semibold text-gray-800">🤖 NanoBot Board</h1>
      <p class="text-sm text-gray-500 mt-1">AI Agent Control Panel</p>
    </header>
    
    <!-- Messages -->
    <div class="flex-1 overflow-y-auto p-6 space-y-4">
      <div
        v-for="(msg, index) in messages"
        :key="index"
        class="flex"
        :class="msg.role === 'user' ? 'justify-end' : 'justify-start'"
      >
        <div
          class="max-w-[80%] rounded-2xl px-4 py-3"
          :class="{
            'bg-blue-500 text-white': msg.role === 'user',
            'bg-white border border-gray-200 text-gray-800': msg.role === 'assistant',
            'bg-red-50 border border-red-200 text-red-800': msg.role === 'system'
          }"
        >
          <div class="prose prose-sm" v-html="renderMarkdown(msg.content)"></div>
          <div class="text-xs mt-2 opacity-70">
            {{ new Date(msg.timestamp).toLocaleTimeString() }}
          </div>
        </div>
      </div>
      
      <!-- Loading indicator -->
      <div v-if="isLoading" class="flex justify-start">
        <div class="bg-white border border-gray-200 rounded-2xl px-4 py-3">
          <div class="flex space-x-2">
            <div class="w-2 h-2 bg-gray-400 rounded-full animate-bounce" style="animation-delay: 0ms"></div>
            <div class="w-2 h-2 bg-gray-400 rounded-full animate-bounce" style="animation-delay: 150ms"></div>
            <div class="w-2 h-2 bg-gray-400 rounded-full animate-bounce" style="animation-delay: 300ms"></div>
          </div>
        </div>
      </div>
    </div>
    
    <!-- Input -->
    <div class="border-t bg-white p-4">
      <form @submit.prevent="sendMessage" class="flex space-x-3">
        <input
          v-model="input"
          type="text"
          placeholder="Type a message... (try 'generate an image of a cat')"
          class="flex-1 border border-gray-300 rounded-xl px-4 py-3 focus:outline-none focus:ring-2 focus:ring-blue-500"
          :disabled="isLoading"
        />
        <button
          type="submit"
          class="bg-blue-500 hover:bg-blue-600 text-white px-6 py-3 rounded-xl font-medium transition-colors disabled:opacity-50"
          :disabled="isLoading || !input.trim()"
        >
          Send
        </button>
      </form>
    </div>
  </div>
</template>
