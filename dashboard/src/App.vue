<script setup lang="ts">
import { ref, getCurrentInstance, onUnmounted } from 'vue'
import Sidebar from './components/Sidebar/Sidebar.vue'
import StatusBar from './components/StatusBar/StatusBar.vue'
import Chat from './components/Chat/Chat.vue'

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
const showProgressMessages = ref(true)

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

onUnmounted(() => {
  if (ws) {
    ws.close()
  }
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
          <label class="text-xs font-bold text-gray-300 whitespace-nowrap">WS-URL</label>
          <input v-model="wsUrl" type="text" :disabled="isConnecting || isConnected"
            class="nes-input flex-1 min-w-[200px] max-w-[400px] text-xs py-1 px-2 border-2 border-gray-600 bg-gray-900 text-gray-300 disabled:bg-gray-700 disabled:text-gray-500"
            placeholder="ws://localhost:8765" />

          <button v-if="!isConnected" @click="connectWebSocket" :disabled="isConnecting || !wsUrl.trim()"
            class="nes-btn" title="连接">
            <svg class="btn-icon" viewBox="0 0 24 24" fill="currentColor">
              <path
                d="M6.62,10.79C8.06,13.62 10.38,15.94 13.21,17.38L15.41,15.18C15.69,14.9 16.08,14.82 16.43,14.93C17.55,15.3 18.75,15.5 20,15.5A1,1 0 0,1 21,16.5V20A1,1 0 0,1 20,21A17,17 0 0,1 3,4A1,1 0 0,1 4,3H7.5A1,1 0 0,1 8.5,4C8.5,5.25 8.7,6.45 9.07,7.57C9.18,7.92 9.1,8.31 8.82,8.59L6.62,10.79Z" />
            </svg>
          </button>

          <button v-if="isConnected" @click="disconnectWebSocket" class="nes-btn is-error" title="断开连接">
            <svg class="btn-icon" viewBox="0 0 24 24" fill="currentColor">
              <path
                d="M6.62,10.79C8.06,13.62 10.38,15.94 13.21,17.38L15.41,15.18C15.69,14.9 16.08,14.82 16.43,14.93C17.55,15.3 18.75,15.5 20,15.5A1,1 0 0,1 21,16.5V20A1,1 0 0,1 20,21A17,17 0 0,1 3,4A1,1 0 0,1 4,3H7.5A1,1 0 0,1 8.5,4C8.5,5.25 8.7,6.45 9.07,7.57C9.18,7.92 9.1,8.31 8.82,8.59L6.62,10.79Z" />
            </svg>
          </button>

          <button @click="showProgressMessages = !showProgressMessages" class="nes-btn"
            :class="{ 'is-error': showProgressMessages }" :title="showProgressMessages ? '关闭进度消息' : '开启进度消息'">
            <svg class="btn-icon" viewBox="0 0 24 24" fill="currentColor">
              <path
                d="M12,9A3,3 0 0,0 9,12A3,3 0 0,0 12,15A3,3 0 0,0 15,12A3,3 0 0,0 12,9M12,17A5,5 0 0,1 7,12A5,5 0 0,1 12,7A5,5 0 0,1 17,12A5,5 0 0,1 12,17M12,4.5C7,4.5 2.73,7.61 1,12C2.73,16.39 7,19.5 12,19.5C17,19.5 21.27,16.39 23,12C21.27,7.61 17,4.5 12,4.5Z" />
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
          @ws-status-change="handleWsStatusChange" :show-progress-messages="showProgressMessages" />
        <div v-show="currentSection !== 'chat'" class="p-6 text-gray-500 text-center">
          <p class="text-lg">Section under construction</p>
          <p class="text-sm mt-2">{{ currentSection }} view coming soon...</p>
        </div>
      </main>

      <!-- Status Bar -->
      <StatusBar ref="statusBarComponentRef" @open-llm-settings="handleOpenLLMSettings" @send-status="handleSendStatus"
        :ws-status="wsConnectionStatus" />
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
</style>
