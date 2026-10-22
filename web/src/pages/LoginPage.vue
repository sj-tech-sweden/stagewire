<template>
  <q-layout view="hHh lpR fFf">
    <q-page-container>
      <q-page class="flex flex-center auth-page">
        <q-card
          class="auth-card q-pa-lg"
          style="width: 400px; max-width: 92vw"
        >
          <q-card-section class="text-center">
            <img
              src="/logo.png"
              alt="Stagewire"
              class="sw-logo q-mb-sm"
            >
            <div class="text-h5">
              {{ t('app.name') }}
            </div>
            <div class="text-subtitle2 text-grey-7">
              {{ t('auth.login.subtitle') }}
            </div>
          </q-card-section>

          <q-banner
            v-if="authStore.error"
            class="bg-negative text-white q-mb-md"
          >
            {{ authStore.error }}
          </q-banner>

          <q-form
            class="q-gutter-md"
            @submit.prevent="onSubmit"
          >
            <q-input
              v-model="email"
              :label="t('auth.login.email')"
              type="email"
              autofocus
              :rules="[(v) => !!v || t('auth.login.required')]"
            />
            <q-input
              v-model="password"
              :label="t('auth.login.password')"
              type="password"
              :rules="[(v) => !!v || t('auth.login.required')]"
            />
          </q-form>

          <q-card-actions align="center">
            <q-btn
              color="primary"
              :label="t('auth.login.signIn')"
              :loading="authStore.loading"
              @click="onSubmit"
            />
          </q-card-actions>

          <template v-if="providers.length">
            <q-separator class="q-my-md" />
            <div class="text-center text-caption text-grey-7 q-mb-sm">
              {{ t('auth.login.sso') }}
            </div>
            <q-card-actions
              align="center"
              class="column q-gutter-sm"
            >
              <q-btn
                v-for="p in providers"
                :key="p.provider"
                outline
                color="primary"
                :label="t('auth.login.continueWith', { provider: p.display_name })"
                @click="startSso(p)"
              />
            </q-card-actions>
          </template>
        </q-card>
      </q-page>
    </q-page-container>
  </q-layout>
</template>

<script setup>
import { onMounted, ref } from 'vue'
import { useI18n } from 'vue-i18n'
import { useRoute, useRouter } from 'vue-router'
import { api } from 'boot/api'
import { useAuthStore } from 'stores/auth'
import { getApiBaseUrl } from '../utils/runtime-config'

const { t } = useI18n({ useScope: "global" })
const route = useRoute()
const router = useRouter()
const authStore = useAuthStore()

const email = ref('')
const password = ref('')
const providers = ref([])

const apiBase = getApiBaseUrl()
const frontendRedirect = `${window.location.origin}/login`

async function loadProviders() {
  try {
    const { data } = await api.get('/auth/sso/providers')
    providers.value = Array.isArray(data) ? data : []
  } catch {
    providers.value = []
  }
}

function startSso(provider) {
  sessionStorage.setItem('sso_provider', provider.provider)
  if (provider.kind === 'oidc') {
    window.location.assign(
      `${apiBase}/api/v1/auth/sso/oidc/authorize/${provider.provider}?redirect_uri=${encodeURIComponent(frontendRedirect)}`,
    )
  } else if (provider.kind === 'saml') {
    window.location.assign(`${apiBase}/api/v1/auth/sso/saml/redirect/${provider.provider}`)
  }
}

async function exchangeOidc(code, state, providerKey) {
  try {
    const { data } = await api.post('/auth/sso/oidc/exchange', {
      provider: providerKey,
      code,
      state,
      redirect_uri: frontendRedirect,
    })
    authStore.setSession(data)
    sessionStorage.removeItem('sso_provider')
    await router.replace('/')
  } catch (err) {
    authStore.error = err.response?.data?.detail || t('auth.login.loginFailed')
  }
}

async function onSubmit() {
  try {
    await authStore.login(email.value, password.value)
    await router.replace('/')
  } catch {
    /* error already set in store */
  }
}

onMounted(async () => {
  await loadProviders()
  const code = route.query.code
  const state = route.query.state
  const provider = route.query.provider || sessionStorage.getItem('sso_provider')
  if (code && state && provider) {
    await exchangeOidc(code, state, provider)
  }
})
</script>

<style scoped>
.auth-page {
  background-image:
    linear-gradient(rgba(0, 0, 0, 0.55), rgba(0, 0, 0, 0.55)),
    url('/login-bg.jpeg');
  background-size: cover;
  background-position: center;
  background-repeat: no-repeat;
  background-attachment: fixed;
}

.sw-logo {
  height: 56px;
  width: auto;
  object-fit: contain;
}
</style>
