<script setup lang="ts">
import { ref } from 'vue'
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

const handleNavigate = (section: string) => {
  currentSection.value = section
}

const handleOpenLLMSettings = () => {
  // Could open a modal or navigate to settings
  console.log('Open LLM settings')
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
        <Chat v-if="currentSection === 'chat'" />
        <div v-else class="p-6 text-gray-500 text-center">
          <p class="text-lg">Section under construction</p>
          <p class="text-sm mt-2">{{ currentSection }} view coming soon...</p>
        </div>
      </main>

      <!-- Status Bar -->
      <StatusBar
        @open-llm-settings="handleOpenLLMSettings"
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
