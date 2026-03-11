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
    _response_for?: string
    _hide_from_ui?: boolean
    _progress?: boolean
  }
}

const props = defineProps<{
  showProgressMessages?: boolean
}>()

const emit = defineEmits(['send', 'new-chat', 'clear-chat', 'upload-image', 'upload-audio', 'upload-file', 'ws-status-change', 'send-status', 'status-update'])

const messages = ref<Message[]>([])
const isLoading = ref(false)
const sessionId = ref(`session_${Date.now()}`)
const currentAudio = ref<HTMLAudioElement | null>(null)
const currentTimeoutId = ref<number | null>(null)
const chatInputRef = ref<InstanceType<typeof ChatInput> | null>(null)

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
      if (data.content && data.metadata?._response_for === 'status') {
        // This is a status update, emit it for StatusBar
        try {
          const statusData = JSON.parse(data.content)
          emit('status-update', statusData)
        } catch (e) {
          console.log('Status message content:', data.content)
        }
      }

      // Check if this is a history response (JSON array)
      if (data.content && data.metadata?._response_for === 'history') {
        try {
          const historyData = JSON.parse(data.content)
          if (Array.isArray(historyData)) {
            console.log('📚 Loaded history:', historyData.length, 'messages')

            // Extract user messages and emit to ChatInput
            const userMessages = historyData
              .filter((msg: any) => msg.role === 'user' && msg.content && msg.content.trim() && !msg.content.startsWith('/'))
              .map((msg: any) => msg.content)

            console.log('✅ Extracted', userMessages.length, 'user messages for history')
            // Call ChatInput method directly via ref
            if (chatInputRef.value) {
              chatInputRef.value.handleUpdateUserHistory(userMessages)
            }

            // Count messages by role before displaying
            const userMsgCount = historyData.filter((msg: any) => msg.role === 'user').length
            const assistantMsgCount = historyData.filter((msg: any) => msg.role === 'assistant').length
            const systemMsgCount = historyData.filter((msg: any) => msg.role === 'system').length

            // Also display all history messages in the chat window
            historyData.forEach((msg: any) => {
              // Skip messages marked as hidden
              if (msg.metadata?._hide_from_ui) {
                return
              }

              // Handle image messages from media
              let imageUrl: string | undefined
              if (msg.media && msg.media.length > 0) {
                const msgType = msg.metadata?.msg_type
                const fileType = msg.metadata?.file_type

                // Check if this is an image message
                if (msgType === 'image' || (fileType && fileType.startsWith('image/'))) {
                  // Extract image from media data
                  const mediaItem = msg.media[0]
                  if (mediaItem && mediaItem.data) {
                    imageUrl = mediaItem.data
                  }
                }
              }

              messages.value.push({
                role: msg.role || 'assistant',
                content: msg.content || 'Message received',
                timestamp: msg.timestamp || Date.now(),
                imageUrl: imageUrl,
                media: msg.media,
                metadata: msg.metadata
              })
            })

            console.log('✅ Displayed', messages.value.length, 'messages in chat window')

            // Show statistics message
            messages.value.push({
              role: 'assistant',
              content: `📊 History loaded: ${userMsgCount} user messages, ${assistantMsgCount} assistant messages${systemMsgCount > 0 ? `, ${systemMsgCount} system messages` : ''}`,
              timestamp: Date.now()
            })
          }
        } catch (e) {
          console.error('Failed to parse history:', e)
        }
        return  // Don't create duplicate message entry
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

      // Don't display messages marked as hidden (like /history command)
      if (!data.metadata?._hide_from_ui) {
        messages.value.push({
          role: 'assistant',
          content: data.content || 'Message received',
          timestamp: Date.now(),
          imageUrl: imageUrl,
          media: data.media,
          metadata: {
            ...data.metadata,
            _progress: data.metadata?._progress
          }
        })
      }

      // Only set isLoading to false if _progress is not true
      if (!data.metadata?._progress) {
        isLoading.value = false
      }
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

const sendMessage = async (data: string | { text: string; images: Array<{ data: string; type: string; name: string }>; files: Array<{ data: string; type: string; name: string }> }) => {
  // Handle both old string format and new object format
  let text = ''
  let images: Array<{ data: string; type: string; name: string }> = []
  let files: Array<{ data: string; type: string; name: string }> = []

  if (typeof data === 'string') {
    text = data
  } else {
    text = data.text || ''
    images = data.images || []
    files = data.files || []
  }

  const userMessage: Message = {
    role: 'user',
    content: text,
    timestamp: Date.now()
  }

  // Add image preview if there's an image
  if (images.length > 0) {
    userMessage.imageUrl = images[0].data
  }

  messages.value.push(userMessage)

  // Update input history with this message (if it's not a command)
  if (text.trim() && !text.trim().startsWith('/')) {
    if (chatInputRef.value) {
      // Get current history and add new message
      const currentHistory = (chatInputRef.value as any).userHistoryMessages || []
      chatInputRef.value.handleUpdateUserHistory([...currentHistory, text.trim()])
    }
  }

  isLoading.value = true

  // Send message through WebSocketChannel
  if (ws && ws.readyState === WebSocket.OPEN) {
    const mediaItems = [
      ...images.map(img => ({ data: img.data, file_name: img.name })),
      ...files.map(file => ({ data: file.data, file_name: file.name }))
    ]

    const messageData = {
      type: 'message',
      message_id: `msg_${Date.now()}_${Math.random().toString(36).substr(2, 9)}`,
      sender_id: 'web_user',
      chat_id: 'default_room',
      content: text,
      media: mediaItems,
      metadata: {
        source: 'web_dashboard',
        timestamp: Date.now(),
        session_id: sessionId.value
      }
    }

    // Set msg_type based on content
    if (images.length > 0) {
      messageData.metadata.msg_type = 'image'
      messageData.metadata.file_type = images[0].type
    } else if (files.length > 0) {
      messageData.metadata.msg_type = 'file'
      messageData.metadata.file_type = files[0].type
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
  // This is now handled by ChatInput - images are queued and sent with text
  console.log('Image queued for upload:', imageData.name)
}

const handleFileUpload = async (fileData: { data: string; type: string; name: string }) => {
  // This is now handled by ChatInput - files are queued and sent with text
  console.log('File queued for upload:', fileData.name)
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
      media: [{
        data: audioData.data,
        file_name: `audio_${Date.now()}.${audioData.type.split('/').pop()}`
      }],  // Send base64 data as media with filename
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

const handleSendStatus = () => {
  if (ws && ws.readyState === WebSocket.OPEN) {
    const userMessage: Message = {
      role: 'user',
      content: '/status',
      timestamp: Date.now()
    }
    messages.value.push(userMessage)

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

const handleConnected = () => {
  if (!ws || ws.readyState !== WebSocket.OPEN) {
    console.log('⚠️ Cannot send /status: WebSocket not connected')
    messages.value.push({
      role: 'system',
      content: 'WebSocket not connected. Please connect first.',
      timestamp: Date.now()
    })
    return
  }

  // Clear messages on successful connection
  messages.value = []

  // Show connection success message
  messages.value.push({
    role: 'assistant',
    content: '✅ WebSocket connected successfully!',
    timestamp: Date.now()
  })

  // Send /status for initialization (hidden from chat)
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
      session_id: sessionId.value,
      _hide_from_ui: true
    }
  }
  console.log('📤 Sending /status for initialization:', statusMsg)
  ws.send(JSON.stringify(statusMsg))

  // Send /history after 500ms to load history for input cache
  setTimeout(() => {
    if (ws && ws.readyState === WebSocket.OPEN) {
      const historyMsg = {
        type: 'message',
        message_id: `msg_${Date.now()}_${Math.random().toString(36).substr(2, 9)}`,
        sender_id: 'web_user',
        chat_id: 'default_room',
        content: '/history',
        media: [],
        metadata: {
          source: 'web_dashboard',
          timestamp: Date.now(),
          session_id: sessionId.value,
          _hide_from_ui: true
        }
      }
      console.log('📤 Sending /history for initialization:', historyMsg)
      ws.send(JSON.stringify(historyMsg))
    }
  }, 500)
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

    // Clear messages and input history
    messages.value = []
    if (chatInputRef.value) {
      chatInputRef.value.handleUpdateUserHistory([])
    }
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

    // Clear messages and input history
    messages.value = []
    if (chatInputRef.value) {
      chatInputRef.value.handleUpdateUserHistory([])
    }
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
  handleSendStatus,
  handleConnected
})
</script>

<template>
  <div class="flex flex-col h-full chat-container">
    <!-- Messages -->
    <MessageList :messages="messages" :isLoading="isLoading" @play-audio="playAudio" @stop-audio="stopAudio"
      :show-progress-messages="props.showProgressMessages" />

    <!-- Input -->
    <ChatInput ref="chatInputRef" :isLoading="isLoading" :disabled="!isConnected" :messages="messages"
      @send="sendMessage" @new-chat="handleNewChat" @clear-chat="handleClearChat" @upload-image="handleImageUpload"
      @upload-audio="handleAudioUpload" @upload-file="handleFileUpload" @send-status="handleSendStatus" />
  </div>
</template>
