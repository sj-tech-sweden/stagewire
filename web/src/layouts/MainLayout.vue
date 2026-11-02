<template>
  <q-layout view="hHh Lpr lff">
    <q-header
      elevated
      class="bg-primary text-white"
    >
      <q-toolbar>
        <q-btn
          flat
          dense
          round
          icon="menu"
          aria-label="Menu"
          @click="leftDrawerOpen = !leftDrawerOpen"
        />

        <q-toolbar-title class="row items-center no-wrap">
          <img
            src="/logo.png"
            alt="Stagewire"
            class="sw-logo q-mr-xs"
          >
          <span class="ellipsis">{{ t('app.name') }}</span>
        </q-toolbar-title>

        <q-space />

        <!-- Desktop: inline actions -->
        <div class="gt-xs row items-center no-wrap">
          <q-btn-dropdown
            flat
            dense
            no-caps
            :icon="themeIcon"
            :label="t(`app.theme.${mode}.short`)"
            content-class="theme-menu"
          >
            <q-list dense>
              <q-item
                v-for="m in modes"
                :key="m"
                v-close-popup
                clickable
                :active="mode === m"
                active-class="text-primary"
                @click="setMode(m)"
              >
                <q-item-section
                  avatar
                  style="min-width: 32px"
                >
                  <q-icon :name="m === 'light' ? 'light_mode' : m === 'dark' ? 'dark_mode' : 'brightness_auto'" />
                </q-item-section>
                <q-item-section>{{ t(`app.theme.${m}.label`) }}</q-item-section>
                <q-item-section
                  v-if="mode === m"
                  side
                >
                  <q-icon
                    name="check"
                    color="primary"
                  />
                </q-item-section>
              </q-item>
            </q-list>
          </q-btn-dropdown>
          <q-btn-dropdown
            flat
            dense
            icon="language"
            :label="t(`app.language.${locale}`)"
          >
            <q-list>
              <q-item
                v-for="l in locales"
                :key="l"
                v-close-popup
                clickable
                @click="switchLocale(l)"
              >
                <q-item-section>{{ t(`app.language.${l}`) }}</q-item-section>
              </q-item>
            </q-list>
          </q-btn-dropdown>
          <q-btn-dropdown
            flat
            dense
            icon="account_circle"
            :label="userLabel"
          >
            <q-list>
              <q-item
                v-close-popup
                clickable
                @click="logout"
              >
                <q-item-section avatar>
                  <q-icon name="logout" />
                </q-item-section>
                <q-item-section>{{ t('app.actions.logout') }}</q-item-section>
              </q-item>
            </q-list>
          </q-btn-dropdown>
        </div>

        <!-- Mobile: collapsed kebab menu -->
        <div class="lt-sm">
          <q-btn-dropdown
            flat
            dense
            round
            icon="more_vert"
          >
            <q-list>
              <q-item
                v-if="isAdmin"
                v-ripple
                clickable
                to="/reports"
                @click="leftDrawerOpen = false"
              >
                <q-item-section avatar>
                  <q-icon name="description" />
                </q-item-section>
                <q-item-section>{{ t('reports.title') }}</q-item-section>
              </q-item>
              <q-item
                v-if="isAdmin"
                v-close-popup
                clickable
                @click="goSettings"
              >
                <q-item-section avatar>
                  <q-icon name="settings" />
                </q-item-section>
                <q-item-section>{{ t('settings.title') }}</q-item-section>
              </q-item>
              <q-item-label header>
                {{ t('app.theme.label') }}
              </q-item-label>
              <q-item
                v-for="m in modes"
                :key="m"
                v-close-popup
                clickable
                :active="mode === m"
                active-class="text-primary"
                @click="setMode(m)"
              >
                <q-item-section avatar>
                  <q-icon :name="m === 'light' ? 'light_mode' : m === 'dark' ? 'dark_mode' : 'brightness_auto'" />
                </q-item-section>
                <q-item-section>{{ t(`app.theme.${m}.label`) }}</q-item-section>
                <q-item-section
                  v-if="mode === m"
                  side
                >
                  <q-icon
                    name="check"
                    color="primary"
                  />
                </q-item-section>
              </q-item>
              <q-item
                v-for="l in locales"
                :key="l"
                v-close-popup
                clickable
                @click="switchLocale(l)"
              >
                <q-item-section avatar>
                  <q-icon name="language" />
                </q-item-section>
                <q-item-section>{{ t(`app.language.${l}`) }}</q-item-section>
              </q-item>
              <q-item
                v-close-popup
                clickable
                @click="logout"
              >
                <q-item-section avatar>
                  <q-icon name="logout" />
                </q-item-section>
                <q-item-section>{{ t('app.actions.logout') }}</q-item-section>
              </q-item>
            </q-list>
          </q-btn-dropdown>
        </div>
      </q-toolbar>
    </q-header>

    <q-drawer
      v-model="leftDrawerOpen"
      :width="220"
      bordered
      class="bg-dark text-white"
    >
      <q-list padding>
        <q-item-label
          header
          class="text-grey-5"
        >
          {{ t('app.navigation') }}
        </q-item-label>
        <q-item
          v-ripple
          clickable
          to="/"
          exact
          @click="leftDrawerOpen = false"
        >
          <q-item-section avatar>
            <q-icon name="event_note" />
          </q-item-section>
          <q-item-section>{{ t('app.nav.jobs') }}</q-item-section>
        </q-item>
        <q-item
          v-ripple
          clickable
          to="/venues"
          @click="leftDrawerOpen = false"
        >
          <q-item-section avatar>
            <q-icon name="meeting_room" />
          </q-item-section>
          <q-item-section>{{ t('app.nav.venues') }}</q-item-section>
        </q-item>
        <q-item
          v-if="isAdmin"
          v-ripple
          clickable
          to="/reports"
          @click="leftDrawerOpen = false"
        >
          <q-item-section avatar>
            <q-icon name="description" />
          </q-item-section>
          <q-item-section>{{ t('reports.title') }}</q-item-section>
        </q-item>
        <q-item
          v-if="isAdmin"
          v-ripple
          clickable
          to="/settings"
          @click="leftDrawerOpen = false"
        >
          <q-item-section avatar>
            <q-icon name="settings" />
          </q-item-section>
          <q-item-section>{{ t('settings.title') }}</q-item-section>
        </q-item>
      </q-list>
    </q-drawer>

    <q-page-container>
      <router-view />
    </q-page-container>
  </q-layout>
</template>

<script setup>
import { computed, ref } from 'vue'
import { useI18n } from 'vue-i18n'
import { useRouter } from 'vue-router'
import { SUPPORTED_LOCALES, setLocale } from '../i18n'
import { useAuthStore } from '@/stores/auth'
import { useThemeStore } from '@/stores/theme'
import { modeIcon } from '@/utils/theme'

const { t, locale } = useI18n({ useScope: 'global' })
const router = useRouter()
const authStore = useAuthStore()
const themeStore = useThemeStore()

const locales = SUPPORTED_LOCALES
const leftDrawerOpen = ref(false)
const isAdmin = computed(() => authStore.user?.role === 'admin')
const userLabel = computed(() => authStore.user?.email || t('app.actions.login'))

const modes = computed(() => themeStore.modes)
const mode = computed(() => themeStore.mode)
const themeIcon = computed(() => modeIcon(themeStore.mode))

function setMode(m) {
  themeStore.setMode(m)
}

function goSettings() {
  router.push('/settings')
}

async function switchLocale(l) {
  setLocale(l)
  locale.value = l
  await authStore.setLanguage(l)
}

function logout() {
  authStore.logout()
  router.replace('/login')
}
</script>

<style scoped>
.sw-logo {
  height: 28px;
  width: auto;
  object-fit: contain;
}
</style>
