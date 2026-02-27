<script setup lang="ts">
import { ref } from 'vue'
import Sidebar from './components/Sidebar/Sidebar.vue'
import StatusBar from './components/StatusBar/StatusBar.vue'
import Chat from './components/Chat/Chat.vue'

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
  <div class="flex h-screen bg-gray-50">
    <!-- Sidebar -->
    <Sidebar
      :is-active="sidebarExpanded"
      @toggle="sidebarExpanded = !sidebarExpanded"
      @navigate="handleNavigate"
    />

    <!-- Main Content -->
    <div class="flex-1 flex flex-col overflow-hidden">
      <!-- Header -->
      <header class="bg-white shadow-sm border-b px-6 py-4 flex-shrink-0">
        <div class="flex items-center justify-between">
          <div>
            <h1 class="text-xl font-semibold text-gray-800">
              {{ currentSection === 'chat' && '💬 Chat' }}
              {{ currentSection === 'settings' && '⚙️ Settings' }}
              {{ currentSection === 'logs' && '📋 Logs' }}
              {{ currentSection === 'memory' && '🧠 Memory' }}
            </h1>
            <p class="text-sm text-gray-500 mt-1">NanoBot Board - AI Agent Dashboard</p>
          </div>
        </div>
      </header>

      <!-- Content Area -->
      <main class="flex-1 overflow-hidden">
        <Chat v-if="currentSection === 'chat'" />
        <div v-else class="p-6 text-gray-500 text-center">
          <p class="text-lg">Section under construction</p>
          <p class="text-sm mt-2">{{ currentSection }} view coming soon...</p>
        </div>
      </main>

      <!-- Status Bar -->
      <StatusBar @open-llm-settings="handleOpenLLMSettings" />
    </div>
  </div>
</template>

<style>
/* Global styles */
body {
  margin: 0;
  font-family: -apple-system, BlinkMacSystemFont, 'Segoe UI', Roboto, Oxygen, Ubuntu, sans-serif;
}
</style>
