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

    // Automatically send /status command after successful connection
    if (chatComponentRef.value && chatComponentRef.value.handleSendStatus) {
      chatComponentRef.value.handleSendStatus()
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
          <label class="text-xs font-bold text-gray-300 whitespace-nowrap">WebSocket url:</label>
          <input v-model="wsUrl" type="text" :disabled="isConnecting || isConnected"
            class="nes-input flex-1 min-w-[200px] max-w-[400px] text-xs py-1 px-2 border-2 border-gray-600 bg-gray-900 text-gray-300 disabled:bg-gray-700 disabled:text-gray-500"
            placeholder="ws://localhost:8765" />

          <button v-if="!isConnected" @click="connectWebSocket" :disabled="isConnecting || !wsUrl.trim()"
            class="nes-btn is-primary text-xs px-3 py-1">
            {{ isConnecting ? 'Connecting...' : 'Connect' }}
          </button>

          <button v-if="isConnected" @click="disconnectWebSocket" class="nes-btn is-danger text-xs px-3 py-1">
            Disconnect
          </button>
        </div>

        <div v-if="connectionError" class="text-xs text-red-500">
          Error: {{ connectionError }}
        </div>
      </div>

      <!-- Content Area -->
      <main class="flex-1 overflow-hidden bg-gray-900">
        <Chat ref="chatComponentRef" v-show="currentSection === 'chat'" @status-update="handleStatusUpdate"
          @ws-status-change="handleWsStatusChange" />
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
  font-family: 'Press Start 2P', 'Courier New', monospace;
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
</style>
