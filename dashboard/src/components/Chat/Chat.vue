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
  media?: Array<{
    data: string
    file_name: string
  }>
  metadata?: {
    msg_type?: string
    file_type?: string
  }
}

const emit = defineEmits(['send', 'new-chat', 'clear-chat', 'upload-image', 'upload-audio', 'upload-file', 'ws-status-change', 'send-status', 'status-update'])

const messages = ref<Message[]>([])
const isLoading = ref(false)
const sessionId = ref(`session_${Date.now()}`)
const currentAudio = ref<HTMLAudioElement | null>(null)
const currentTimeoutId = ref<number | null>(null)

// WebSocket instance (managed by App.vue)
let ws: WebSocket | null = null
const isConnected = ref(false)

// Method to set WebSocket instance from App.vue
const setWebSocket = (websocket: WebSocket | null) => {
  ws = websocket
  isConnected.value = websocket !== null
}

// Method to handle WebSocket messages from App.vue
const handleWebSocketMessage = (event: MessageEvent) => {
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

      // Handle image messages from media
      let imageUrl: string | undefined
      if (data.media && data.media.length > 0) {
        const msgType = data.metadata?.msg_type
        const fileType = data.metadata?.file_type

        // Check if this is an image message
        if (msgType === 'image' || (fileType && fileType.startsWith('image/'))) {
          // Extract image from media data
          const mediaItem = data.media[0]
          if (mediaItem && mediaItem.data) {
            imageUrl = mediaItem.data
          }
        }
      }

      messages.value.push({
        role: 'assistant',
        content: data.content || 'Message received',
        timestamp: Date.now(),
        imageUrl: imageUrl,
        media: data.media,
        metadata: data.metadata
      })
      isLoading.value = false
    } else if (data.type === 'heartbeat') {
      // Reply to heartbeat
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

const handleImageUpload = async (imageData: { data: string; type: string; name: string }) => {
  // Check file size (limit to 20MB)
  const fileSizeInBytes = Math.round((imageData.data.length * 3) / 4) // Approximate size from base64
  const maxSize = 20 * 1024 * 1024 // 20MB

  if (fileSizeInBytes > maxSize) {
    messages.value.push({
      role: 'system',
      content: `Image file is too large. Maximum size is 20MB. Your image is approximately ${(fileSizeInBytes / (1024 * 1024)).toFixed(2)}MB.`,
      timestamp: Date.now()
    })
    return
  }

  // Add image to messages
  messages.value.push({
    role: 'user',
    content: 'Uploaded an image',
    timestamp: Date.now(),
    imageUrl: imageData.data
  })

  // Send image to backend with msg_type
  if (ws && ws.readyState === WebSocket.OPEN) {
    const messageData = {
      type: 'message',
      message_id: `msg_${Date.now()}_${Math.random().toString(36).substr(2, 9)}`,
      sender_id: 'web_user',
      chat_id: 'default_room',
      content: '',  // Empty content for image-only messages
      media: [{
        data: imageData.data,
        file_name: imageData.name
      }],  // Send base64 data as media with filename
      metadata: {
        source: 'web_dashboard',
        timestamp: Date.now(),
        session_id: sessionId.value,
        msg_type: 'image',  // Indicate this is an image message
        file_type: imageData.type
      }
    }

    console.log('📤 Sending image message:', messageData)
    isLoading.value = true
    try {
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
    } catch (error) {
      console.error('Failed to send image:', error)
      messages.value.push({
        role: 'system',
        content: 'Failed to send image. Please try again.',
        timestamp: Date.now()
      })
      isLoading.value = false
    }
  } else {
    messages.value.push({
      role: 'system',
      content: 'WebSocket not connected. Please connect first.',
      timestamp: Date.now()
    })
  }
}

const handleAudioUpload = async (audioData: { data: string; type: string; isRecording?: boolean }) => {
  // Add audio to messages
  messages.value.push({
    role: 'user',
    content: audioData.isRecording ? 'Recorded voice message' : 'Uploaded audio',
    timestamp: Date.now(),
    audioUrl: audioData.data
  })

  // Send audio to backend with msg_type
  if (ws && ws.readyState === WebSocket.OPEN) {
    const messageData = {
      type: 'message',
      message_id: `msg_${Date.now()}_${Math.random().toString(36).substr(2, 9)}`,
      sender_id: 'web_user',
      chat_id: 'default_room',
      content: '',  // Empty content for audio-only messages
      media: [audioData.data],  // Send base64 data as media
      metadata: {
        source: 'web_dashboard',
        timestamp: Date.now(),
        session_id: sessionId.value,
        msg_type: 'audio',  // Indicate this is an audio message
        file_type: audioData.type,
        is_recording: audioData.isRecording
      }
    }

    console.log('📤 Sending audio message:', messageData)
    isLoading.value = true
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
    messages.value.push({
      role: 'system',
      content: 'WebSocket not connected. Please connect first.',
      timestamp: Date.now()
    })
  }
}

const handleFileUpload = async (fileData: { data: string; type: string; name: string }) => {
  // Add file to messages
  messages.value.push({
    role: 'user',
    content: `Uploaded file: ${fileData.name}`,
    timestamp: Date.now()
  })

  // Send file to backend with msg_type
  if (ws && ws.readyState === WebSocket.OPEN) {
    const messageData = {
      type: 'message',
      message_id: `msg_${Date.now()}_${Math.random().toString(36).substr(2, 9)}`,
      sender_id: 'web_user',
      chat_id: 'default_room',
      content: '',  // Empty content for file-only messages
      media: [{
        data: fileData.data,
        file_name: fileData.name
      }],
      metadata: {
        source: 'web_dashboard',
        timestamp: Date.now(),
        session_id: sessionId.value,
        msg_type: 'file',  // Indicate this is a file message
        file_type: fileData.type
      }
    }

    console.log('📤 Sending file message:', messageData)
    isLoading.value = true
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
    messages.value.push({
      role: 'system',
      content: 'WebSocket not connected. Please connect first.',
      timestamp: Date.now()
    })
  }
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
  stopAudio()
})

// Expose methods to App.vue
defineExpose({
  setWebSocket,
  handleWebSocketMessage,
  handleSendStatus
})
</script>

<template>
  <div class="flex flex-col h-full chat-container">
    <!-- Messages -->
    <MessageList :messages="messages" :isLoading="isLoading" @play-audio="playAudio" @stop-audio="stopAudio" />

    <!-- Input -->
    <ChatInput :isLoading="isLoading" :disabled="!isConnected" @send="sendMessage" @new-chat="handleNewChat"
      @clear-chat="handleClearChat" @upload-image="handleImageUpload" @upload-audio="handleAudioUpload"
      @upload-file="handleFileUpload" @send-status="handleSendStatus" />
  </div>
</template>
