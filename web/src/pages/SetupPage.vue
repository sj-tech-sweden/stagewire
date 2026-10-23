<template>
  <q-layout view="hHh lpR fFf">
    <q-page-container>
      <q-page class="flex flex-center bg-grey-2 auth-page">
        <q-card
          class="auth-card q-pa-lg"
          style="width: 420px; max-width: 92vw"
        >
          <q-card-section class="text-center">
            <img
              src="/logo.png"
              alt="Stagewire"
              class="sw-logo q-mb-sm"
            >
            <div class="text-h5">
              {{ t('auth.setup.title') }}
            </div>
            <div class="text-subtitle2 text-grey-7">
              {{ t('auth.setup.subtitle') }}
            </div>
          </q-card-section>

          <q-banner
            v-if="authStore.error"
            class="bg-negative text-white q-mb-md"
          >
            {{ authStore.error }}
          </q-banner>
          <q-banner
            v-if="alreadySetup"
            class="bg-info text-white q-mb-md"
          >
            {{ t('auth.setup.alreadySetup') }}
            <q-btn
              flat
              :label="t('auth.setup.goToLogin')"
              @click="goLogin"
            />
          </q-banner>

          <q-card-section
            v-if="!alreadySetup"
            class="q-gutter-md"
          >
            <q-input
              v-model="form.email"
              :label="t('auth.setup.email')"
              type="email"
              autofocus
            />
            <div class="row q-gutter-sm">
              <q-input
                v-model="form.first_name"
                class="col"
                :label="t('auth.setup.firstName')"
              />
              <q-input
                v-model="form.last_name"
                class="col"
                :label="t('auth.setup.lastName')"
              />
            </div>
            <q-input
              v-model="form.password"
              :label="t('auth.setup.confirmPassword')"
              type="password"
              :hint="t('auth.setup.minLength')"
            />
            <q-input
              v-model="confirm"
              :label="t('auth.setup.confirmPassword')"
              type="password"
            />
          </q-card-section>

          <q-card-actions
            v-if="!alreadySetup"
            align="center"
          >
            <q-btn
              color="primary"
              :label="t('auth.setup.createAdmin')"
              :loading="authStore.loading"
              :disable="!canSubmit"
              @click="onSubmit"
            />
          </q-card-actions>
        </q-card>
      </q-page>
    </q-page-container>
  </q-layout>
</template>

<script setup>
import { computed, onMounted, ref } from 'vue'
import { useI18n } from 'vue-i18n'
import { useRouter } from 'vue-router'
import { api } from '@/boot/api'
import { useAuthStore } from '@/stores/auth'

const { t } = useI18n({ useScope: "global" })
const router = useRouter()
const authStore = useAuthStore()

const alreadySetup = ref(false)
const confirm = ref('')
const form = ref({ email: '', first_name: '', last_name: '', password: '' })

const canSubmit = computed(
  () =>
    form.value.email &&
    form.value.password &&
    form.value.password === confirm.value,
)

async function checkStatus() {
  try {
    const { data } = await api.get('/auth/bootstrap-status')
    alreadySetup.value = !data.setup_needed
  } catch {
    alreadySetup.value = false
  }
}

function goLogin() {
  router.replace('/login')
}

async function onSubmit() {
  if (!canSubmit.value) return
  try {
    await authStore.setup({ ...form.value })
    await router.replace('/')
  } catch {
    /* error in store */
  }
}

onMounted(checkStatus)
</script>

<style scoped>
.sw-logo {
  height: 56px;
  width: auto;
  object-fit: contain;
}
</style>
