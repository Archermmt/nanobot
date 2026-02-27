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
  const wsUrl = `ws://localhost:8000/ws/chat/${sessionId.value}`
  ws = new WebSocket(wsUrl)
  
  ws.onopen = () => {
    console.log('WebSocket connected')
  }
  
  ws.onmessage = (event) => {
    const data = JSON.parse(event.data)
    
    if (data.type === 'thought') {
      // Could show thinking indicator
      console.log('Thinking:', data.data)
    } else if (data.type === 'response') {
      messages.value.push({
        role: 'assistant',
        content: data.data,
        timestamp: Date.now()
      })
      isLoading.value = false
    } else if (data.type === 'error') {
      messages.value.push({
        role: 'system',
        content: `Error: ${data.data}`,
        timestamp: Date.now()
      })
      isLoading.value = false
    } else if (data.type === 'done') {
      // Conversation complete
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
  
  // Check if user is asking for image generation
  const isImageRequest = messageText.toLowerCase().includes('generate') && 
                         (messageText.toLowerCase().includes('image') ||
                          messageText.toLowerCase().includes('picture') ||
                          messageText.toLowerCase().includes('draw'))
  
  if (isImageRequest && ws && ws.readyState === WebSocket.OPEN) {
    // Send via WebSocket
    ws.send(JSON.stringify({
      message: messageText,
      session_id: sessionId.value
    }))
  } else if (ws && ws.readyState === WebSocket.OPEN) {
    ws.send(JSON.stringify({
      message: messageText,
      session_id: sessionId.value
    }))
  } else {
    // Fallback to REST API
    try {
      const response = await fetch('http://localhost:8000/api/chat', {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({
          message: messageText,
          session_id: sessionId.value
        })
      })
      
      const data = await response.json()
      messages.value.push({
        role: 'assistant',
        content: data.response,
        timestamp: Date.now()
      })
    } catch (error) {
      messages.value.push({
        role: 'system',
        content: `Error: Failed to send message - ${error}`,
        timestamp: Date.now()
      })
    } finally {
      isLoading.value = false
    }
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
