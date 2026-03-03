<script setup lang="ts">
import { ref, getCurrentInstance } from 'vue'
import Sidebar from './components/Sidebar/Sidebar.vue'
import StatusBar from './components/StatusBar/StatusBar.vue'
import Chat from './components/Chat/Chat.vue'

// WebSocket connection status
const wsConnectionStatus = ref({
  isConnected: false,
  isConnecting: false,
  url: ''
})

const sidebarExpanded = ref(true)
const currentSection = ref('chat')
const chatComponentRef = ref<any>(null)
const statusBarComponentRef = ref<any>(null)

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

// Handle WebSocket status change from Chat component
const handleWsStatusChange = (data: any) => {
  console.log('🔌 WebSocket status change received in App.vue:', data)
  // Update wsConnectionStatus for header display
  wsConnectionStatus.value = {
    isConnected: data.isConnected,
    isConnecting: data.isConnecting,
    url: data.url
  }
  // Pass the status data to StatusBar to update connected state
  if (statusBarComponentRef.value && statusBarComponentRef.value.receiveWsStatusChange) {
    statusBarComponentRef.value.receiveWsStatusChange(data)
  }
}
</script>

<template>
  <div class="flex h-screen">
    <!-- Sidebar -->
    <Sidebar
      :is-active="sidebarExpanded"
      @toggle="sidebarExpanded = !sidebarExpanded"
      @navigate="handleNavigate"
    />

    <!-- Main Content -->
    <div class="flex-1 flex flex-col overflow-hidden">
      <!-- Header -->
      <header class="bg-gradient-to-r from-red-500 to-pink-500 px-6 py-4 flex-shrink-0 border-b-4 border-gray-800 shadow-[inset_0_4px_0_rgba(255,255,255,0.3),inset_0_-4px_0_rgba(0,0,0,0.3)]">
        <div class="flex items-center justify-between">
          <div>
            <h1 class="text-white text-lg font-bold drop-shadow-[2px_2px_0_rgba(0,0,0,0.5)]">
              <template v-if="currentSection === 'chat'">💬 CHAT</template>
              <template v-else-if="currentSection === 'settings'">⚙️ SETTINGS</template>
              <template v-else-if="currentSection === 'logs'">📋 LOGS</template>
              <template v-else-if="currentSection === 'memory'">🧠 MEMORY</template>
            </h1>
            <p class="text-gray-200 text-xs mt-1">NanoBot Board - AI Agent Dashboard</p>
          </div>
        </div>
      </header>

      <!-- Content Area -->
      <main class="flex-1 overflow-hidden bg-gray-900">
        <Chat
          ref="chatComponentRef"
          v-if="currentSection === 'chat'"
          @status-update="handleStatusUpdate"
          @ws-status-change="handleWsStatusChange"
        />
        <div v-else class="p-6 text-gray-500 text-center">
          <p class="text-lg">Section under construction</p>
          <p class="text-sm mt-2">{{ currentSection }} view coming soon...</p>
        </div>
      </main>

      <!-- Status Bar -->
      <StatusBar
        ref="statusBarComponentRef"
        @open-llm-settings="handleOpenLLMSettings"
        @send-status="handleSendStatus"
        :ws-status="wsConnectionStatus"
      />
    </div>
  </div>
</template>

<style>
/* Global styles */
body {
  margin: 0;
  font-family: 'Press Start 2P', 'Courier New', monospace;
}
</style>
