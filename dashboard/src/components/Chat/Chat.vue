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
  const wsUrl = `ws://localhost:8000/ws/chat/${sessionId.value}`
  ws = new WebSocket(wsUrl)
  
  ws.onopen = () => {
    console.log('✅ WebSocket connected')
  }
  
  ws.onmessage = (event) => {
    const data = JSON.parse(event.data)
    
    if (data.type === 'thought') {
      // Could show thinking indicator
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
  
  if (ws && ws.readyState === WebSocket.OPEN) {
    ws.send(JSON.stringify({
      message: text,
      session_id: sessionId.value
    }))
  } else {
    // Fallback to REST API
    try {
      const response = await fetch('http://localhost:8000/api/chat', {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({
          message: text,
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
