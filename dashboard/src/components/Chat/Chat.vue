<script setup lang="ts">
import { ref, onMounted, onUnmounted, watch } from 'vue'
import MessageList from './MessageList.vue'
import ChatInput from './ChatInput.vue'
import { getAudioPlayer } from '../../js/audio/player.js'
import { handleToolCallMessage } from '../../js/tools/tools.js'
import WebsocketTools from '../../js/tools/websocket_tools.json'

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
    _task_ref?: string
    _hide_message?: boolean
    _progress?: boolean
    isPlayingOpus?: boolean
  }
}

const props = defineProps<{
  showProgressMessages?: boolean
  isOnlineChatOn?: boolean
  msgHandlers?: string[]
}>()

const emit = defineEmits(['status-update', 'chat-status-change'])
const messages = ref<Message[]>([])
const chatStatus = ref<string>("")
const sessionId = ref(`session_${Date.now()}`)
const senderId = ref('web_user')  // Global sender ID
const chatId = ref('default')  // Global chat ID
const currentAudio = ref<HTMLAudioElement | null>(null)
const currentTimeoutId = ref<number | null>(null)
const chatInputRef = ref<InstanceType<typeof ChatInput> | null>(null)
const pendingCommandsCount = ref(0)  // Track pending commands during connection

// Global audio playing state shared across components
const playingAudioUrl = ref<string | null>(null)

// WebSocket instance (managed by App.vue)
let ws: WebSocket | null = null
const isConnected = ref(false)

// Audio player instance
const audioPlayer = getAudioPlayer()
const ttsSentenceCount = ref(0)

// Method to set WebSocket instance from App.vue
const setWebSocket = (websocket: WebSocket | null) => {
  ws = websocket
  isConnected.value = websocket !== null
}

// Unified function to handle task_ref completion logic
const handleTaskRefCompletion = (taskRef: string) => {
  if (!taskRef) return

  if (pendingCommandsCount.value > 0) {
    pendingCommandsCount.value--
    console.log('⏳ Pending commands:', pendingCommandsCount.value)
    // Clear status when all commands are completed
    if (pendingCommandsCount.value === 0) {
      chatStatus.value = ""
      console.log('✅ All initialization commands completed')
    }
  }
}

// Handle WebSocket message parsing and routing
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

    // Handle MCP messages
    if (data.type === 'tool_call') {
      handleToolCallMessage(data, ws)
      return
    }

    // Clear timeout when receiving any message
    if (currentTimeoutId.value) {
      clearTimeout(currentTimeoutId.value)
      currentTimeoutId.value = null
    }

    if (data.type === 'message') {
      // Handle task completion
      handleTaskRefCompletion(data.metadata?._task_ref)

      // Check if this is a status response
      if (data.content && data.metadata?._task_ref === 'status') {
        // This is a status update, emit it for StatusBar and App.vue
        try {
          const statusData = JSON.parse(data.content)
          console.log('🔊 Status update:', statusData)
          // Emit to parent component (App.vue) to update global state
          emit('status-update', statusData)
        } catch (e) {
          console.log('Status message content:', data.content)
        }
      }

      // Check if this is a history response (JSON array)
      if (data.content && data.metadata?._task_ref === 'history') {
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
              if (msg.metadata?._hide_message) {
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
      if (!data.metadata?._hide_message) {
        const newMessage: Message = {
          role: 'assistant',
          content: data.content || 'Message received',
          timestamp: Date.now(),
          imageUrl: imageUrl,
          audioUrl: audioUrl,
          media: data.media,
          metadata: data.metadata
        }
        messages.value.push(newMessage)

        // Auto-play audio if it's an audio message and TTS is enabled
        if (audioUrl) {
          playAudio(audioUrl)
        }
      }

      // Check if message contains _mode_hint and is not a progress message
      if (data.metadata?._trigger_cmd) {
        sendMessage(data.metadata._trigger_cmd, true)
      }

      // Only set chatStatus based on _progress and _as_input
      if (data.metadata?._progress) {
        chatStatus.value = "Thinking"
      } else if (!data.audioUrl) {
        chatStatus.value = ""
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
      chatStatus.value = ""
    }
  } catch (e) {
    console.error('Failed to parse message:', e)
  }
}

// Unified message sending function for all types of messages
const sendMessage = async (
  data: string | { text: string; images?: Array<{ data: string; type: string; name: string }>; files?: Array<{ data: string; type: string; name: string }>; audios?: Array<{ data: string; type: string; name: string }> },
  isCommand: boolean = false,
  extraMetadata?: Record<string, any>
) => {
  // Handle both old string format and new object format
  let text = ''
  let images: Array<{ data: string; type: string; name: string }> = []
  let files: Array<{ data: string; type: string; name: string }> = []
  let audios: Array<{ data: string; type: string; name: string }> = []

  if (typeof data === 'string') {
    text = data
  } else {
    text = data.text || ''
    images = data.images || []
    files = data.files || []
    audios = data.audios || []
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

  // Only add message to UI if not hidden and has text content
  // For audio-only messages, don't show empty user message, only show ASR result
  if (!isCommand && (text.trim() || audios.length === 0)) {
    messages.value.push(userMessage)
  }

  // Clear messages when sending /new or /clear commands
  if (isCommand && (text === '/new' || text === '/clear')) {
    messages.value = []
    if (chatInputRef.value) {
      chatInputRef.value.handleUpdateUserHistory([])
    }
  }

  // Update input history with this message (if it's not a command)
  if (text.trim() && !text.trim().startsWith('/')) {
    if (chatInputRef.value) {
      // Get current history and add new message
      const currentHistory = (chatInputRef.value as any).userHistoryMessages || []
      chatInputRef.value.handleUpdateUserHistory([...currentHistory, text.trim()])
    }
  }

  // Send message through WebSocketChannel
  if (ws && ws.readyState === WebSocket.OPEN) {
    const mediaItems = [
      ...images.map(img => ({ data: img.data, file_name: img.name })),
      ...files.map(file => ({ data: file.data, file_name: file.name })),
      ...audios.map(audio => ({ data: audio.data, file_name: audio.name }))
    ]

    const messageData: {
      type: 'message' | 'mcp'
      message_id: string
      sender_id: string
      chat_id: string
      content: string
      media: Array<{ data: string; file_name: string }>
      metadata: {
        source: string
        timestamp: number
        session_id: string
        msg_type?: string
        file_type?: string
        features?: { need_tts: boolean }
        reset?: boolean
        payload?: any
      } & Record<string, any>
    } = {
      type: "message",
      message_id: `msg_${Date.now()}_${Math.random().toString(36).substr(2, 9)}`,
      sender_id: senderId.value,
      chat_id: chatId.value,
      content: text,
      media: mediaItems,
      metadata: {
        source: 'web_dashboard',
        timestamp: Date.now(),
        session_id: sessionId.value,
        ...extraMetadata
      }
    }

    // Set msg_type based on content
    if (audios.length > 0) {
      messageData.metadata.msg_type = 'audio'
      messageData.metadata.file_type = audios[0].type
    } else if (images.length > 0) {
      messageData.metadata.msg_type = 'image'
      messageData.metadata.file_type = images[0].type
    } else if (files.length > 0) {
      messageData.metadata.msg_type = 'file'
      messageData.metadata.file_type = files[0].type
    }

    console.log('📤 Sending message:', messageData)
    ws.send(JSON.stringify(messageData))
    if (!isCommand) {
      chatStatus.value = "Thinking"
    }

    // Set timeout: if no response within 60 seconds, stop loading
    const timeoutId = setTimeout(() => {
      if (chatStatus.value === "Thinking") {
        chatStatus.value = ""
        console.warn('No response received within 30 seconds')
      }
      // Also handle command timeout
      if (isCommand && pendingCommandsCount.value > 0) {
        pendingCommandsCount.value = 0
        console.warn('⏰ Command timed out, remaining:', pendingCommandsCount.value)
        chatStatus.value = ""
      }
    }, 60000)

    // Store timeout ID in a ref so we can clear it on message receive
    currentTimeoutId.value = timeoutId

  } else {
    // Error prompt when WebSocket is not connected
    messages.value.push({
      role: 'system',
      content: 'WebSocket not connected. Please connect first.',
      timestamp: Date.now()
    })
    chatStatus.value = ""
  }
}

// Removed handleNewChat and handleClearChat - now directly using sendMessage in template

const handleConnected = () => {
  if (!ws || ws.readyState !== WebSocket.OPEN) {
    console.log('⚠️ Cannot send /inspect: WebSocket not connected')
    messages.value.push({
      role: 'system',
      content: 'WebSocket not connected. Please connect first.',
      timestamp: Date.now()
    })
    return
  }

  // Set status to Loading at the beginning
  chatStatus.value = "Loading"

  // Clear messages on successful connection
  messages.value = []

  // Show connection success message
  messages.value.push({
    role: 'assistant',
    content: '✅ WebSocket connected successfully!',
    timestamp: Date.now()
  })

  // Send /inspect for initialization (hidden from chat)
  sendMessage('/inspect', true)
  pendingCommandsCount.value++

  // Send /update_features with reset flag on connection
  sendMessage('/update_features', true, { reset: true })
  pendingCommandsCount.value++

  // Send tools list to backend
  sendMessage('/register_extern_tools', true, { tools: WebsocketTools })
  pendingCommandsCount.value++

  // Send /history after 500ms to load history for input cache
  sendMessage('/history', true)
  pendingCommandsCount.value++
}

const handleRecordingStart = () => {
  chatStatus.value = "Recording"
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
  // Stop normal audio playback first
  if (currentAudio.value) {
    console.log('Stopping normal audio playback')
    currentAudio.value.pause()
    playingAudioUrl.value = null
    currentAudio.value = null
  }

  // Stop remote speaking (opus playback)
  if (chatStatus.value === "Speaking") {
    console.log('Stopping remote speaking (opus playback)')
    // Clear all audio buffers and stop playback
    audioPlayer.clearAllAudio()
    // Delay stop to let remaining audio play
    ttsSentenceCount.value = 0
    // Update the last message's playing state
    if (messages.value.length > 0) {
      const lastMsg = messages.value[messages.value.length - 1]
      if (lastMsg.metadata?.isPlayingOpus !== undefined) {
        lastMsg.metadata.isPlayingOpus = false
      }
    }
  }
  chatStatus.value = ""
}

// Watch for chatStatus changes and emit to parent
watch(chatStatus, (newStatus) => {
  emit('chat-status-change', newStatus)
})

// Watch for playingAudioUrl changes and update chatStatus
watch(playingAudioUrl, (newUrl) => {
  if (newUrl) {
    chatStatus.value = "Speaking"
  } else {
    chatStatus.value = ""
  }
})

// Handle TTS message - same as xiaozhi-esp32-server implementation
const handleTTSMessage = async (data: any) => {
  const state = data.state
  if (state === 'start') {
    console.log('语音段开始')
    ttsSentenceCount.value = 0
    chatStatus.value = "Speaking"
  } else if (state === 'sentence_start') {
    console.debug(`服务器发送语音段：${data.text}`)
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
    console.log(`语音段结束`)
  } else if (state === 'stop') {
    stopAudio()
  }
}

// Handle opus audio frame - enqueue to player
const handleOpusAudioFrame = async (data: Blob | ArrayBuffer) => {
  if (chatStatus.value !== "Speaking") {
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
  chatStatus,
  setWebSocket,
  handleWebSocketMessage,
  handleConnected,
  sendMessage,
})

</script>

<template>
  <div class="flex flex-col h-full chat-container">
    <!-- Messages -->
    <MessageList :messages="messages" :chat-status="chatStatus" @play-audio="playAudio" @stop-audio="stopAudio"
      :show-progress-messages="props.showProgressMessages" :playing-audio-url="playingAudioUrl" />

    <!-- Input -->
    <ChatInput ref="chatInputRef" :chat-status="chatStatus" :disabled="!isConnected"
      :is-online-chat-on="props.isOnlineChatOn" :msg-handlers="props.msgHandlers" :messages="messages"
      @send="sendMessage" @stop-audio="stopAudio" @recording-start="handleRecordingStart" />
  </div>
</template>
