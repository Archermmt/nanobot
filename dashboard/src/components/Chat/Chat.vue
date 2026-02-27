<script setup lang="ts">
import { ref, onMounted, onUnmounted } from 'vue'
import MessageList from './MessageList.vue'
import ChatInput from './ChatInput.vue'

interface Message {
  role: 'user' | 'assistant' | 'system'
  content: string
  timestamp: number
  imageUrl?: string
  audioUrl?: string
}

const messages = ref<Message[]>([])
const isLoading = ref(false)
const sessionId = ref(`session_${Date.now()}`)
const currentAudio = ref<HTMLAudioElement | null>(null)

let ws: WebSocket | null = null

const connectWebSocket = () => {
  // 连接到 WebSocketChannel 服务器地址
  const wsUrl = `ws://localhost:8765/ws`
  ws = new WebSocket(wsUrl)
  
  ws.onopen = () => {
    console.log('✅ WebSocket connected to WebSocketChannel')
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
    setTimeout(connectWebSocket, 2000)
  }
  
  ws.onerror = (error) => {
    console.error('WebSocket error:', error)
  }
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
      content: 'WebSocket not connected. Please wait for reconnection.',
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

onMounted(() => {
  connectWebSocket()
})

onUnmounted(() => {
  ws?.close()
  stopAudio()
})
</script>

<template>
  <div class="flex flex-col h-full">
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
      @send="sendMessage"
      @upload-image="handleImageUpload"
      @upload-audio="handleAudioUpload"
    />
  </div>
</template>
