<script setup lang="ts">
import { ref, onMounted, onUnmounted, watch } from 'vue'
import Sidebar from './components/Sidebar/Sidebar.vue'
import StatusBar from './components/StatusBar/StatusBar.vue'
import Chat from './components/Chat/Chat.vue'
import { mdiPhone, mdiWebcam, mdiMicrophone, mdiVolumeHigh, mdiEyeOff } from '@mdi/js'
import { getAudioPlayer } from './components/Media/audio/player.js'
import { checkOpusLoaded, initOpusEncoder } from './components/Media/audio/opus-codec.js';
import { getAudioRecorder } from './components/Media/audio/recorder.js';

// Audio player instance
let audioPlayer: any = null
// Audio recorder instance
let audioRecorder: any = null

// WebSocket connection state
const wsUrl = ref('ws://localhost:8765')
const isConnected = ref(false)
const isConnecting = ref(false)
const connectionError = ref<string | null>(null)
let ws: WebSocket | null = null

// Other states
const wsConnectionStatus = ref({
  isConnected: false,
  isConnecting: false,
  url: ''
})

const sidebarExpanded = ref(true)
const currentSection = ref('chat')
const chatComponentRef = ref<any>(null)
const statusBarComponentRef = ref<any>(null)
const hideProgress = ref(false)
const isCameraOn = ref(false)
const isOnlineChatOn = ref(false)
const enableAudio = ref(false) // Track if audio input handler is enabled
const enableSpeak = ref(false) // Track if speech output is enabled
const enableTTS = ref(false) // Track if TTS is available
const videoStream = ref<MediaStream | null>(null)
const audioStream = ref<MediaStream | null>(null)
const videoElement = ref<HTMLVideoElement | null>(null)

// Draggable camera window state
const cameraWindowPos = ref({ x: 100, y: 100 })
const isDraggingCamera = ref(false)
const dragOffset = ref({ x: 0, y: 0 })

// WebSocket connection methods
const connectWebSocket = () => {
  if (isConnecting.value || isConnected.value) return

  isConnecting.value = true
  connectionError.value = null

  // Update status for header display
  wsConnectionStatus.value = {
    isConnected: false,
    isConnecting: true,
    url: wsUrl.value
  }

  ws = new WebSocket(wsUrl.value)

  ws.onopen = () => {
    console.log('✅ WebSocket connected to WebSocketChannel')
    isConnecting.value = false
    isConnected.value = true
    connectionError.value = null

    // Update status for header display
    wsConnectionStatus.value = {
      isConnected: true,
      isConnecting: false,
      url: wsUrl.value
    }

    // Send auth message
    if (ws) {
      const authMsg = {
        type: 'auth',
        token: 'your_auth_token_here'
      }
      ws.send(JSON.stringify(authMsg))
    }

    // Notify Chat component
    if (chatComponentRef.value && chatComponentRef.value.setWebSocket) {
      chatComponentRef.value.setWebSocket(ws)
    }

    // Initialize connection: send /status and /history commands (hidden from chat)
    if (chatComponentRef.value && chatComponentRef.value.handleConnected) {
      chatComponentRef.value.handleConnected()
    }
  }

  ws.onmessage = (event) => {
    // Forward messages to Chat component
    if (chatComponentRef.value && chatComponentRef.value.handleWebSocketMessage) {
      chatComponentRef.value.handleWebSocketMessage(event)
    }
  }

  ws.onclose = () => {
    console.log('WebSocket disconnected')
    isConnecting.value = false
    isConnected.value = false

    wsConnectionStatus.value = {
      isConnected: false,
      isConnecting: false,
      url: wsUrl.value
    }
  }

  ws.onerror = (error) => {
    console.error('WebSocket error:', error)
    isConnecting.value = false
    isConnected.value = false
    connectionError.value = 'Connection error'

    wsConnectionStatus.value = {
      isConnected: false,
      isConnecting: false,
      url: wsUrl.value
    }
  }
}

const disconnectWebSocket = () => {
  if (ws) {
    ws.close()
    ws = null
  }
  isConnected.value = false
  isConnecting.value = false

  wsConnectionStatus.value = {
    isConnected: false,
    isConnecting: false,
    url: wsUrl.value
  }

  // Notify Chat component
  if (chatComponentRef.value && chatComponentRef.value.setWebSocket) {
    chatComponentRef.value.setWebSocket(null)
  }
}

let thinkingInterval: number | null = null

// Initialize application (similar to xiaozhi-esp32-server app.js init)
const initApp = async () => {
  console.debug('正在初始化应用...')

  try {
    // 检查Opus库
    checkOpusLoaded();
    // 初始化Opus编码器
    initOpusEncoder();
    // Initialize audio player
    audioPlayer = getAudioPlayer()
    await audioPlayer.start()
    console.log('应用初始化完成')
  } catch (error) {
    console.error('应用初始化失败:', error)
  }
}

onMounted(() => {
  // Initialize audio player and other components
  initApp()
})

const handleThinkingChange = (isThinkingState: boolean) => {
  if (isThinkingState) {
    // Start blinking effect
    let dots = 0
    thinkingInterval = window.setInterval(() => {
      dots = (dots + 1) % 4
      document.title = 'Thinking ' + '.'.repeat(dots)
    }, 500)
  } else {
    // Stop blinking effect and reset title
    if (thinkingInterval) {
      clearInterval(thinkingInterval)
      thinkingInterval = null
    }
    document.title = 'NanoBoard'
  }
}

onUnmounted(() => {
  if (ws) {
    ws.close()
  }

  // Clean up media streams
  if (videoStream.value) {
    videoStream.value.getTracks().forEach(track => track.stop())
  }

  // Clean up audio player and recorder
  if (audioPlayer) {
    audioPlayer.clearAllAudio()
  }
  if (audioRecorder && audioRecorder.isRecording) {
    audioRecorder.stop()
  }

  // Remove global event listeners for drag
  document.removeEventListener('mousemove', dragCamera)
  document.removeEventListener('mouseup', stopDragCamera)
})

const handleNavigate = (section: string) => {
  currentSection.value = section
}

const handleOpenLLMSettings = () => {
  // Could open a modal or navigate to settings
  console.log('Open LLM settings')
}

// Handle status refresh from StatusBar
const handleSendStatus = () => {
  console.log('🔄 Status refresh requested from StatusBar')
  // Trigger the Chat component to send /status command
  if (chatComponentRef.value && chatComponentRef.value.handleSendStatus) {
    chatComponentRef.value.handleSendStatus()
  }
}

// Handle status update from Chat component
const handleStatusUpdate = (data: any) => {
  console.log('📊 Status update received in App.vue:', data)
  // Update global enable_audio and enable_tts state
  if (data.enable_audio !== undefined) {
    enableAudio.value = data.enable_audio
  }
  if (data.enable_tts !== undefined) {
    enableTTS.value = data.enable_tts
  }
  // Pass the status data to StatusBar via a custom event or prop
  // We'll use a ref to call StatusBar's method
  if (statusBarComponentRef.value && statusBarComponentRef.value.handleStatusUpdate) {
    statusBarComponentRef.value.handleStatusUpdate(data)
  }
}

// Handle WebSocket status change from Chat component (no longer needed, managed in App.vue)
const handleWsStatusChange = (data: any) => {
  // This is now managed directly in App.vue
  console.log('🔌 WebSocket status change (managed in App.vue):', data)
}

// Camera and microphone controls
const toggleCamera = async () => {
  if (isCameraOn.value) {
    // Turn off camera
    if (videoStream.value) {
      videoStream.value.getTracks().forEach(track => track.stop())
      videoStream.value = null
    }
    isCameraOn.value = false
    console.log('Camera disabled')
  } else {
    // Turn on camera
    try {
      const stream = await navigator.mediaDevices.getUserMedia({
        video: {
          width: { ideal: 1280 },
          height: { ideal: 720 },
          facingMode: 'user'
        }
      })
      videoStream.value = stream
      isCameraOn.value = true

      // Set video element srcObject
      setTimeout(() => {
        if (videoElement.value) {
          videoElement.value.srcObject = stream
        }
      }, 100)

      console.log('Camera enabled')
    } catch (error) {
      console.error('Error accessing camera:', error)
      alert('无法访问摄像头，请确保已授予权限')
    }
  }
}

const startOnlineChat = async () => {
  if (isOnlineChatOn.value) {
    // Turn off online chat
    if (audioRecorder && audioRecorder.isRecording) {
      audioRecorder.stop()
    }
    isOnlineChatOn.value = false
    console.log('Online chat disabled')
  } else {
    // Turn on online chat
    try {
      isOnlineChatOn.value = true
      // Initialize and start audio recorder
      audioRecorder = getAudioRecorder()
      if (audioRecorder && ws) {
        audioRecorder.setWebSocket(ws)
        await audioRecorder.start()
      }
      console.log('Online chat enabled')
    } catch (error) {
      console.error('Error accessing microphone:', error)
      alert('无法访问麦克风，请确保已授予权限')
    }
  }
}

// Camera window drag functions
const startDragCamera = (event: MouseEvent) => {
  isDraggingCamera.value = true
  const rect = (event.target as HTMLElement).getBoundingClientRect()
  dragOffset.value = {
    x: event.clientX - rect.left,
    y: event.clientY - rect.top
  }
}

const dragCamera = (event: MouseEvent) => {
  if (!isDraggingCamera.value) return
  event.preventDefault()
  cameraWindowPos.value = {
    x: event.clientX - dragOffset.value.x,
    y: event.clientY - dragOffset.value.y
  }
}

const stopDragCamera = () => {
  isDraggingCamera.value = false
}

// Add global event listeners for drag
document.addEventListener('mousemove', dragCamera)
document.addEventListener('mouseup', stopDragCamera)
</script>

<template>
  <div class="flex h-screen">
    <!-- Sidebar -->
    <Sidebar :is-active="sidebarExpanded" @toggle="sidebarExpanded = !sidebarExpanded" @navigate="handleNavigate" />

    <!-- Main Content -->
    <div class="flex-1 flex flex-col overflow-hidden">
      <!-- WebSocket Connection Control Panel -->
      <div class="border-b-4 border-gray-700 bg-gray-800 p-3 pixel-font">
        <div class="flex items-center space-x-3 flex-wrap gap-2">
          <div class="nes-field is-inline">
            <label class="text-xs font-bold text-gray-300 whitespace-nowrap">WS-URL</label>
            <input v-model="wsUrl" type="text" :disabled="isConnecting || isConnected"
              class="nes-input flex-1 min-w-[200px] max-w-[400px] text-xs py-1 px-2 border-2 border-gray-600 bg-gray-900 text-gray-300 disabled:bg-gray-700 disabled:text-gray-500"
              placeholder="ws://localhost:8765" />
          </div>

          <button v-if="!isConnected" @click="connectWebSocket" :disabled="isConnecting || !wsUrl.trim()"
            class="nes-btn" title="连接">
            <svg class="btn-icon" viewBox="0 0 24 24" fill="currentColor">
              <path :d="mdiPhone" />
            </svg>
          </button>

          <button v-if="isConnected" @click="disconnectWebSocket" class="nes-btn is-success" title="断开连接">
            <svg class="btn-icon" viewBox="0 0 24 24" fill="currentColor">
              <path :d="mdiPhone" />
            </svg>
          </button>

          <button @click="toggleCamera" class="nes-btn"
            :class="{ 'is-success': isCameraOn, 'is-disabled': !isConnected }" :title="isCameraOn ? '关闭摄像头' : '开启摄像头'">
            <svg class="btn-icon" viewBox="0 0 24 24" fill="currentColor">
              <path :d="mdiWebcam" />
            </svg>
          </button>

          <button @click="startOnlineChat" class="nes-btn"
            :class="{ 'is-success': isOnlineChatOn, 'is-disabled': !isConnected }"
            :title="isOnlineChatOn ? '关闭在线聊天' : '开启在线聊天'">
            <svg class="btn-icon" viewBox="0 0 24 24" fill="currentColor">
              <path :d="mdiMicrophone" />
            </svg>
          </button>

          <button @click="enableSpeak = !enableSpeak" class="nes-btn"
            :class="{ 'is-success': enableSpeak, 'is-disabled': !isConnected || !enableTTS }"
            :title="enableSpeak ? '关闭语音输出' : '开启语音输出'">
            <svg class="btn-icon" viewBox="0 0 24 24" fill="currentColor">
              <path :d="mdiVolumeHigh" />
            </svg>
          </button>

          <button @click="hideProgress = !hideProgress" class="nes-btn"
            :class="{ 'is-success': hideProgress, 'is-disabled': !isConnected }"
            :title="hideProgress ? '开启思考模式' : '关闭思考模式'">
            <svg class="btn-icon" viewBox="0 0 24 24" fill="currentColor">
              <path :d="mdiEyeOff" />
            </svg>
          </button>
        </div>

        <div v-if="connectionError" class="text-xs text-red-500">
          Error: {{ connectionError }}
        </div>
      </div>

      <!-- Content Area -->
      <main class="flex-1 overflow-hidden bg-gray-900">
        <Chat ref="chatComponentRef" v-show="currentSection === 'chat'" @status-update="handleStatusUpdate"
          @ws-status-change="handleWsStatusChange" @thinking-change="handleThinkingChange"
          :show-progress-messages="!hideProgress" :is-online-chat-on="isOnlineChatOn" :enable-audio="enableAudio"
          :enable-tts="enableTTS" :enable-speak="enableSpeak" />
        <div v-show="currentSection !== 'chat'" class="p-6 text-gray-500 text-center">
          <p class="text-lg">Section under construction</p>
          <p class="text-sm mt-2">{{ currentSection }} view coming soon...</p>
        </div>
      </main>

      <!-- Status Bar -->
      <StatusBar ref="statusBarComponentRef" @open-llm-settings="handleOpenLLMSettings" @send-status="handleSendStatus"
        :ws-status="wsConnectionStatus" />
    </div>

    <!-- Draggable Camera Window -->
    <div v-if="isCameraOn" class="camera-window"
      :style="{ left: cameraWindowPos.x + 'px', top: cameraWindowPos.y + 'px' }">
      <div class="camera-header" @mousedown="startDragCamera">
        <span class="camera-title">📹 摄像头</span>
        <button @click="toggleCamera" class="camera-close-btn">&times;</button>
      </div>
      <div class="camera-content">
        <video ref="videoElement" autoplay playsinline muted class="camera-video"></video>
      </div>
    </div>
  </div>
</template>

<style>
/* Global styles */
body {
  margin: 0;
  font-family: 'Noto Sans SC', 'Press Start 2P', 'Courier New', monospace;
  font-size: 10px;
  /* Reduced from default */
}

/* Chat page specific styles */
.chat-container {
  font-size: 12px;
  /* Keep chat page slightly larger for readability */
}

/* Keep input textarea at normal size */
.chat-input-textarea {
  font-size: 18px !important;
}

/* Toggle Switch Styles */
.nes-switch {
  position: relative;
  display: inline-block;
  width: 50px;
  height: 24px;
}

.nes-switch input {
  opacity: 0;
  width: 0;
  height: 0;
}

.nes-switch-slider {
  position: absolute;
  cursor: pointer;
  top: 0;
  left: 0;
  right: 0;
  bottom: 0;
  background-color: #4b5563;
  transition: .3s;
  border: 2px solid #1f2937;
  box-shadow: 2px 2px 0 rgba(0, 0, 0, 0.5);
}

.nes-switch-slider:before {
  position: absolute;
  content: "";
  height: 16px;
  width: 16px;
  left: 2px;
  bottom: 2px;
  background-color: white;
  transition: .3s;
  box-shadow: 1px 1px 0 rgba(0, 0, 0, 0.3);
}

.nes-switch input:checked+.nes-switch-slider {
  background-color: #10b981;
}

.nes-switch input:checked+.nes-switch-slider:before {
  transform: translateX(26px);
  background-color: #f0fdf4;
}

/* Pixel Style Control Buttons */
.control-btn {
  display: flex;
  align-items: center;
  gap: 6px;
  padding: 8px 12px;
  font-size: 12px;
  font-family: 'Press Start 2P', 'Noto Sans SC', monospace;
  background-color: #374151;
  color: #e5e7eb;
  border: 2px solid #1f2937;
  box-shadow: 2px 2px 0 rgba(0, 0, 0, 0.5);
  cursor: pointer;
  transition: all 0.1s ease;
  position: relative;
}

.control-btn:hover {
  background-color: #4b5563;
  transform: translate(-1px, -1px);
  box-shadow: 3px 3px 0 rgba(0, 0, 0, 0.5);
}

.control-btn:active {
  transform: translate(1px, 1px);
  box-shadow: 1px 1px 0 rgba(0, 0, 0, 0.5);
}

.control-btn.is-danger {
  background-color: #dc2626;
  color: white;
}

.control-btn.is-danger:hover {
  background-color: #ef4444;
}

.control-btn.peek-btn.is-active {
  background-color: #10b981;
  color: white;
}

.control-btn.peek-btn.is-active:hover {
  background-color: #34d399;
}

.btn-icon {
  width: 16px;
  height: 16px;
  flex-shrink: 0;
}

.btn-text {
  font-weight: bold;
  letter-spacing: 0.5px;
}

/* Draggable Camera Window */
.camera-window {
  position: fixed;
  width: 320px;
  background-color: #1f2937;
  border: 3px solid #374151;
  box-shadow: 4px 4px 0 rgba(0, 0, 0, 0.8);
  z-index: 9999;
  user-select: none;
}

.camera-header {
  display: flex;
  justify-content: space-between;
  align-items: center;
  padding: 8px 12px;
  background-color: #374151;
  cursor: move;
  border-bottom: 2px solid #1f2937;
}

.camera-title {
  font-size: 12px;
  font-family: 'Press Start 2P', 'Noto Sans SC', monospace;
  color: #e5e7eb;
  font-weight: bold;
}

.camera-close-btn {
  width: 24px;
  height: 24px;
  background-color: #dc2626;
  color: white;
  border: 2px solid #b91c1c;
  font-size: 18px;
  line-height: 1;
  cursor: pointer;
  display: flex;
  align-items: center;
  justify-content: center;
  font-family: 'Press Start 2P', 'Noto Sans SC', monospace;
  transition: all 0.1s ease;
}

.camera-close-btn:hover {
  background-color: #ef4444;
  transform: translate(-1px, -1px);
}

.camera-close-btn:active {
  transform: translate(1px, 1px);
}

.camera-content {
  padding: 8px;
  background-color: #111827;
}

.camera-video {
  width: 100%;
  height: auto;
  border: 2px solid #374151;
  background-color: #000;
  display: block;
}
</style>
