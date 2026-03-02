<script setup lang="ts">
import { ref } from 'vue'

interface Props {
  isActive: boolean
}

defineProps<Props>()
const emit = defineEmits(['toggle', 'navigate'])

const activeSection = ref('chat')

const menuItems = [
  { id: 'chat', icon: '💬', label: 'Chat' },
  { id: 'settings', icon: '⚙️', label: 'Settings' },
  { id: 'logs', icon: '📋', label: 'Logs' },
  { id: 'memory', icon: '🧠', label: 'Memory' }
]

const navigate = (section: string) => {
  activeSection.value = section
  emit('navigate', section)
}
</script>

<template>
  <aside 
    class="w-16 bg-gray-800 text-white flex flex-col items-center py-4 transition-all duration-300 border-r-4 border-gray-600"
    :class="{ 'w-64': isActive }"
  >
    <!-- Logo -->
    <div class="mb-8 px-3">
      <div class="flex items-center" :class="{ 'justify-center': !isActive }">
        <span class="text-2xl">🤖</span>
        <span v-if="isActive" class="ml-3 font-bold text-lg whitespace-nowrap">NanoBot</span>
      </div>
    </div>

    <!-- Navigation -->
    <nav class="flex-1 w-full space-y-2">
      <button
        v-for="item in menuItems"
        :key="item.id"
        @click="navigate(item.id)"
        class="w-full flex items-center px-3 py-3 hover:bg-gray-700 transition-colors"
        :class="{ 'bg-gray-700': activeSection === item.id }"
      >
        <span class="text-xl min-w-[1.5rem] text-center">{{ item.icon }}</span>
        <span v-if="isActive" class="ml-3 whitespace-nowrap">{{ item.label }}</span>
      </button>
    </nav>

    <!-- Toggle Button -->
    <button
      @click="$emit('toggle')"
      class="mt-4 p-2 hover:bg-gray-700 rounded-lg transition-colors"
    >
      <span class="text-xl">{{ isActive ? '◀' : '▶' }}</span>
    </button>
  </aside>
</template>
