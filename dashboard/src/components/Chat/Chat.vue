<script setup lang="ts">
import { ref, onMounted, onUnmounted } from 'vue'
import MessageList from './MessageList.vue'
import ChatInput from './ChatInput.vue'
import { getAudioPlayer } from '../../js/audio/player.js'

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
    need_tts?: boolean
    isPlayingOpus?: boolean
  }
}

const props = defineProps<{
  showProgressMessages?: boolean
  isMicrophoneOn?: boolean
  enableASR?: boolean
  enableSpeak?: boolean
}>()

const emit = defineEmits(['send', 'new-chat', 'clear-chat', 'upload-image', 'upload-audio', 'upload-file', 'ws-status-change', 'send-status', 'status-update', 'thinking-change', 'stop-audio'])

const messages = ref<Message[]>([])
const isLoading = ref(false)
const sessionId = ref(`session_${Date.now()}`)
const currentAudio = ref<HTMLAudioElement | null>(null)
const currentTimeoutId = ref<number | null>(null)
const chatInputRef = ref<InstanceType<typeof ChatInput> | null>(null)
const enableASR = ref(false)
const enableTTS = ref(false)

// Global audio playing state shared across components
const playingAudioUrl = ref<string | null>(null)

// WebSocket instance (managed by App.vue)
let ws: WebSocket | null = null
const isConnected = ref(false)

// Audio player instance
const audioPlayer = getAudioPlayer()
const isRemoteSpeaking = ref(false)
const ttsSentenceCount = ref(0)

// Method to set WebSocket instance from App.vue
const setWebSocket = (websocket: WebSocket | null) => {
  ws = websocket
  isConnected.value = websocket !== null
}

// Method to handle WebSocket messages from App.vue
const handleWebSocketMessage = (event: MessageEvent) => {
  try {
    // Check if this is binary data (opus audio frame)
    if (event.data instanceof Blob || event.data instanceof ArrayBuffer) {
      handleOpusAudioFrame(event.data)
      return
    }

    const data = JSON.parse(event.data)
    console.log('📥 Received message:', data)

    // Handle TTS messages for opus audio streaming
    if (data.type === 'tts') {
      handleTTSMessage(data)
      return
    }

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
          // Update global audio/tts state
          if (statusData.enable_asr !== undefined) {
            enableASR.value = statusData.enable_asr
          }
          if (statusData.enable_tts !== undefined) {
            enableTTS.value = statusData.enable_tts
          }
          console.log('🔊 ASR enabled:', enableASR.value, 'TTS enabled:', enableTTS.value)
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

      // Handle image and audio messages from media
      let imageUrl: string | undefined
      let audioUrl: string | undefined

      if (data.media && data.media.length > 0) {
        const msgType = data.metadata?.msg_type
        const fileType = data.metadata?.file_type

        // Check if this is an image message
        if (msgType === 'image' || (fileType && fileType.startsWith('image/'))) {
          // Extract image from media data
          const mediaItem = data.media[0]
          if (mediaItem && typeof mediaItem === 'string') {
            imageUrl = mediaItem
          }
        }

        // Check if this is an audio message
        if (msgType === 'audio' || (fileType && fileType.startsWith('audio/'))) {
          // Extract audio from media data
          const mediaItem = data.media[0]
          if (mediaItem && typeof mediaItem === 'string') {
            // Convert base64 to blob URL for playback
            const base64Data = mediaItem
            const byteCharacters = atob(base64Data)
            const byteNumbers = new Array(byteCharacters.length)
            for (let i = 0; i < byteCharacters.length; i++) {
              byteNumbers[i] = byteCharacters.charCodeAt(i)
            }
            const byteArray = new Uint8Array(byteNumbers)
            const blob = new Blob([byteArray], { type: 'audio/mpeg' })
            audioUrl = URL.createObjectURL(blob)
          }
        }
      }

      // Don't display messages marked as hidden (like /history command)
      if (!data.metadata?._hide_from_ui) {
        const newMessage: Message = {
          role: 'assistant',
          content: data.content || 'Message received',
          timestamp: Date.now(),
          imageUrl: imageUrl,
          audioUrl: audioUrl,
          media: data.media,
          metadata: {
            ...data.metadata,
            _progress: data.metadata?._progress
          }
        }
        messages.value.push(newMessage)

        // Auto-play audio if it's an audio message and TTS is enabled
        if (audioUrl && enableTTS.value) {
          playAudio(audioUrl)
        }
      }

      // Check if message contains mode_hint and is not a progress message
      if (data.metadata?.mode_hint && !data.metadata?._progress) {
        // Call handleSendStatus to update status bar
        handleSendStatus()
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

const sendMessage = async (data: string | { text: string; images: Array<{ data: string; type: string; name: string }>; files: Array<{ data: string; type: string; name: string }> }, hideFromUI = false) => {
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

  // Only add message to UI if not hidden
  if (!hideFromUI) {
    messages.value.push(userMessage)
  }

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

    const messageData: {
      type: string
      message_id: string
      sender_id: string
      chat_id: string
      content: string
      media: Array<{ data: string; file_name: string }>
      metadata: {
        source: string
        timestamp: number
        session_id: string
        need_tts?: boolean
        msg_type?: string
        file_type?: string
        _hide_from_ui?: boolean
      }
    } = {
      type: 'message',
      message_id: `msg_${Date.now()}_${Math.random().toString(36).substr(2, 9)}`,
      sender_id: 'web_user',
      chat_id: 'default_room',
      content: text,
      media: mediaItems,
      metadata: {
        source: 'web_dashboard',
        timestamp: Date.now(),
        session_id: sessionId.value,
        need_tts: props.enableSpeak,  // Add need_tts flag based on global enableSpeak
        _hide_from_ui: hideFromUI  // Add hide flag for control commands
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

const handleAudioUpload = async (audioData: { data: string; type: string; isRecording?: boolean; needTts?: boolean }) => {
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
        is_recording: audioData.isRecording,
        need_tts: audioData.needTts || false  // Add need_tts flag
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
        session_id: sessionId.value,
        _hide_from_ui: true
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

const handleThinkingChange = (isThinking: boolean) => {
  emit('thinking-change', isThinking)
}

const playAudio = (audioUrl: string) => {
  if (currentAudio.value) {
    if (currentAudio.value.src === audioUrl && !currentAudio.value.paused) {
      currentAudio.value.pause()
      playingAudioUrl.value = null
      return
    }
    currentAudio.value.pause()
  }

  currentAudio.value = new Audio(audioUrl)
  currentAudio.value.play()
  playingAudioUrl.value = audioUrl

  currentAudio.value.onended = () => {
    playingAudioUrl.value = null
  }
}

const stopAudio = () => {
  if (currentAudio.value) {
    currentAudio.value.pause()
    playingAudioUrl.value = null
    currentAudio.value = null
  }
}

const handleStopAudio = () => {
  // Stop normal audio playback first
  if (currentAudio.value) {
    currentAudio.value.pause()
    playingAudioUrl.value = null
    currentAudio.value = null
  }

  // Stop remote speaking (opus playback)
  if (isRemoteSpeaking.value) {
    // Clear all audio buffers and stop playback
    audioPlayer.clearAllAudio()
    isRemoteSpeaking.value = false
    ttsSentenceCount.value = 0

    // Update message playing state
    messages.value.forEach(msg => {
      if (msg.metadata?.isPlayingOpus) {
        msg.metadata.isPlayingOpus = false
      }
    })
  }

  // Send /stop_audio command to backend
  sendMessage('/stop_audio', true)
}

// Handle TTS message - same as xiaozhi-esp32-server implementation
const handleTTSMessage = async (data: any) => {
  const state = data.state
  console.log('🎵 TTS message:', state, data.text)

  if (state === 'start') {
    console.log('服务器开始发送语音', 'info')
    isRemoteSpeaking.value = true
    ttsSentenceCount.value = 0
  } else if (state === 'sentence_start') {
    console.log(`服务器发送语音段：${data.text}`, 'info')
    ttsSentenceCount.value++
    // Add message to chat immediately
    if (data.text && !data.text.trim().startsWith('/')) {
      messages.value.push({
        role: 'assistant',
        content: data.text,
        timestamp: Date.now(),
        metadata: {
          isPlayingOpus: true
        }
      })
    }
  } else if (state === 'sentence_end') {
    console.log(`语音段结束：${data.text}`, 'info')
    // Don't clear animation at sentence end, wait for next sentence or final stop
  } else if (state === 'stop') {
    // Clear all audio buffers and stop playback
    audioPlayer.clearAllAudio()
    isRemoteSpeaking.value = false
    // Delay stop to let remaining audio play
    setTimeout(() => {
      ttsSentenceCount.value = 0

      // Update the last message's playing state
      if (messages.value.length > 0) {
        const lastMsg = messages.value[messages.value.length - 1]
        if (lastMsg.metadata?.isPlayingOpus !== undefined) {
          lastMsg.metadata.isPlayingOpus = false
        }
      }

      isLoading.value = false
    }, 1000)
  }
}

// Handle opus audio frame - enqueue to player
const handleOpusAudioFrame = async (data: Blob | ArrayBuffer) => {
  if (!isRemoteSpeaking.value) {
    console.warn('⚠️ Received opus frame but not speaking')
    return
  }

  try {
    let opusData: Uint8Array
    if (data instanceof Blob) {
      const arrayBuffer = await data.arrayBuffer()
      opusData = new Uint8Array(arrayBuffer)
    } else {
      opusData = new Uint8Array(data)
    }
    console.debug('📦 Received opus frame, size:', opusData.length, 'bytes')

    // Enqueue to audio player for buffering and playback
    audioPlayer.enqueueAudioData(opusData)
  } catch (error) {
    console.error('❌ Failed to process opus frame:', error)
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

  // Clear all audio when component unmounts
  if (audioPlayer) {
    audioPlayer.clearAllAudio()
  }
})

// Expose reactive state and methods to parent component
defineExpose({
  isLoading,
  isRemoteSpeaking,
  playingAudioUrl,
  setWebSocket,
  handleWebSocketMessage,
  handleSendStatus,
  handleConnected
})
</script>

<template>
  <div class="flex flex-col h-full chat-container">
    <!-- Messages -->
    <MessageList :messages="messages" :isLoading="isLoading" @play-audio="playAudio" @stop-audio="handleStopAudio"
      :show-progress-messages="props.showProgressMessages" :playing-audio-url="playingAudioUrl"
      @thinking-change="handleThinkingChange" />

    <!-- Input -->
    <ChatInput ref="chatInputRef" :isLoading="isLoading" :disabled="!isConnected"
      :is-microphone-on="props.isMicrophoneOn" :enable-audio="props.enableASR" :enable-speak="props.enableSpeak"
      :messages="messages" @send="sendMessage" @new-chat="handleNewChat" @clear-chat="handleClearChat"
      @upload-image="handleImageUpload" @upload-audio="handleAudioUpload" @upload-file="handleFileUpload"
      @send-status="handleSendStatus" @stop-audio="stopAudio" />
  </div>
</template>
