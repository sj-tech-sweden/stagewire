<template>
  <q-page class="q-pa-md">
    <div
      v-if="!isAdmin"
      class="text-center q-mt-xl text-grey"
    >
      {{ t('common.errorOccurred') }}
    </div>

    <template v-else>
      <div class="text-h5 q-mb-md">
        {{ t('settings.title') }}
      </div>

      <q-tabs
        v-model="tab"
        class="text-primary"
        align="left"
      >
        <q-tab
          name="users"
          :label="t('settings.users.title')"
        />
        <q-tab
          name="sso"
          :label="t('settings.sso.title')"
        />
        <q-tab
          name="company"
          :label="t('settings.company.title')"
        />
        <q-tab
          name="stockwire"
          :label="t('settings.stockwire.title')"
        />
      </q-tabs>
      <q-separator />

      <q-tab-panels
        v-model="tab"
        animated
      >
        <!-- USERS -->
        <q-tab-panel name="users">
          <div class="row items-center q-mb-md">
            <div class="text-subtitle1">
              {{ t('settings.users.title') }}
            </div>
            <q-space />
            <q-btn
              color="primary"
              icon="add"
              :label="t('settings.users.newUser')"
              @click="openCreateUser"
            />
          </div>

          <q-table
            :rows="users"
            :columns="userColumns"
            row-key="id"
            :loading="usersLoading"
            flat
            bordered
          >
            <template #body-cell-active="props">
              <q-td>
                <q-badge :color="props.value ? 'positive' : 'grey'">
                  {{ props.value ? t('settings.users.isActive') : t('settings.users.isInactive') }}
                </q-badge>
              </q-td>
            </template>
            <template #body-cell-actions="props">
              <q-td>
                <q-btn
                  flat
                  dense
                  icon="edit"
                  @click="openEditUser(props.row)"
                />
                <q-btn
                  flat
                  dense
                  icon="delete"
                  color="negative"
                  @click="deleteUser(props.row)"
                />
              </q-td>
            </template>
          </q-table>

          <q-dialog v-model="userDialog">
            <q-card style="min-width: 420px">
              <q-card-section class="text-h6">
                {{ editingUser ? t('settings.users.editUser') : t('settings.users.newUser') }}
              </q-card-section>
              <q-card-section class="q-gutter-md">
                <q-input
                  v-model="userForm.email"
                  :label="t('settings.users.email')"
                  type="email"
                  autofocus
                />
                <div class="row q-gutter-sm">
                  <q-input
                    v-model="userForm.first_name"
                    class="col"
                    :label="t('auth.setup.firstName')"
                  />
                  <q-input
                    v-model="userForm.last_name"
                    class="col"
                    :label="t('auth.setup.lastName')"
                  />
                </div>
                <q-input
                  v-model="userForm.password"
                  :label="editingUser ? t('settings.users.newPasswordOptional') : t('auth.setup.confirmPassword')"
                  type="password"
                />
                <q-select
                  v-model="userForm.role"
                  :options="roleOptions"
                  :label="t('settings.users.role')"
                  emit-value
                  map-options
                />
                <q-select
                  v-model="userForm.preferred_language"
                  :options="languageOptions"
                  :label="t('settings.users.language')"
                  emit-value
                  map-options
                />
                <q-toggle
                  v-model="userForm.is_active"
                  :label="t('settings.users.active')"
                />
              </q-card-section>
              <q-card-actions align="right">
                <q-btn
                  v-close-popup
                  flat
                  :label="t('app.actions.cancel')"
                  color="primary"
                />
                <q-btn
                  flat
                  :label="t('app.actions.save')"
                  color="primary"
                  :loading="savingUser"
                  @click="saveUser"
                />
              </q-card-actions>
            </q-card>
          </q-dialog>
        </q-tab-panel>

        <!-- SSO -->
        <q-tab-panel name="sso">
          <div class="text-subtitle1 q-mb-sm">
            {{ t('settings.sso.title') }}
          </div>
          <q-inner-loading :showing="ssoLoading" />
          <template v-if="ssoConfig">
            <q-card
              flat
              bordered
              class="q-pa-md q-mb-md"
            >
              <div class="row q-gutter-md items-center">
                <q-toggle
                  v-model="ssoConfig.enabled"
                  :label="t('settings.sso.enabled')"
                />
                <q-toggle
                  v-model="ssoConfig.auto_create_users"
                  :label="t('settings.sso.autoCreate')"
                />
                <q-toggle
                  v-model="ssoConfig.sync_roles_on_login"
                  :label="t('settings.sso.syncRoles')"
                />
                <q-select
                  v-model="ssoConfig.default_role"
                  :options="roleOptions"
                  :label="t('settings.sso.defaultRole')"
                  emit-value
                  map-options
                  class="col-2"
                />
              </div>

              <div class="text-subtitle2 q-mt-md">
                {{ t('settings.sso.groupRoleMap') }}
              </div>
              <div
                v-for="(row, idx) in groupMappings"
                :key="idx"
                class="row q-gutter-sm items-center q-mt-xs"
              >
                <q-input
                  v-model="row.group"
                  class="col"
                  :label="t('settings.sso.externalGroup')"
                  dense
                />
                <q-select
                  v-model="row.role"
                  class="col"
                  :options="roleOptions"
                  :label="t('settings.sso.appRole')"
                  emit-value
                  map-options
                  dense
                />
                <q-btn
                  flat
                  dense
                  icon="delete"
                  color="negative"
                  @click="groupMappings.splice(idx, 1)"
                />
              </div>
              <q-btn
                flat
                dense
                icon="add"
                color="primary"
                class="q-mt-sm"
                :label="t('settings.sso.addGroupMapping')"
                @click="groupMappings.push({ group: '', role: 'viewer' })"
              />
            </q-card>

            <!-- OIDC providers -->
            <q-card
              flat
              bordered
              class="q-pa-md q-mb-md"
            >
              <div class="row items-center q-mb-sm">
                <div class="text-subtitle2">
                  {{ t('settings.sso.oidcProviders') }}
                </div>
                <q-space />
                <q-btn
                  flat
                  dense
                  icon="add"
                  color="primary"
                  :label="t('settings.sso.addProvider')"
                  @click="openProvider('oidc')"
                />
              </div>
              <q-list
                v-if="ssoConfig.oidc_providers.length"
                dense
                bordered
                separator
              >
                <q-item
                  v-for="(p, i) in ssoConfig.oidc_providers"
                  :key="i"
                >
                  <q-item-section>{{ p.display_name || p.key }}</q-item-section>
                  <q-item-section side>
                    <div>
                      <q-btn
                        flat
                        dense
                        icon="edit"
                        @click="openProvider('oidc', i)"
                      />
                      <q-btn
                        flat
                        dense
                        icon="delete"
                        color="negative"
                        @click="ssoConfig.oidc_providers.splice(i, 1)"
                      />
                    </div>
                  </q-item-section>
                </q-item>
              </q-list>
              <div
                v-else
                class="text-grey text-caption"
              >
                {{ t('settings.users.noUsers') }}
              </div>
            </q-card>

            <!-- SAML providers -->
            <q-card
              flat
              bordered
              class="q-pa-md q-mb-md"
            >
              <div class="row items-center q-mb-sm">
                <div class="text-subtitle2">
                  {{ t('settings.sso.samlProviders') }}
                </div>
                <q-space />
                <q-btn
                  flat
                  dense
                  icon="add"
                  color="primary"
                  :label="t('settings.sso.addProvider')"
                  @click="openProvider('saml')"
                />
              </div>
              <q-list
                v-if="ssoConfig.saml_providers.length"
                dense
                bordered
                separator
              >
                <q-item
                  v-for="(p, i) in ssoConfig.saml_providers"
                  :key="i"
                >
                  <q-item-section>{{ p.display_name || p.key }}</q-item-section>
                  <q-item-section side>
                    <div>
                      <q-btn
                        flat
                        dense
                        icon="edit"
                        @click="openProvider('saml', i)"
                      />
                      <q-btn
                        flat
                        dense
                        icon="delete"
                        color="negative"
                        @click="ssoConfig.saml_providers.splice(i, 1)"
                      />
                    </div>
                  </q-item-section>
                </q-item>
              </q-list>
              <div
                v-else
                class="text-grey text-caption"
              >
                {{ t('settings.users.noUsers') }}
              </div>
            </q-card>

            <q-btn
              color="primary"
              :label="t('settings.sso.save')"
              :loading="savingSso"
              @click="saveSso"
            />
          </template>

          <!-- provider dialog -->
          <q-dialog v-model="providerDialog">
            <q-card style="min-width: 460px">
              <q-card-section class="text-h6">
                {{ providerType === 'oidc' ? 'OIDC' : 'SAML' }} — {{ editingProviderIndex === null ? t('settings.sso.addProvider') : t('settings.sso.editProvider') }}
              </q-card-section>
              <q-card-section class="q-gutter-md">
                <q-input
                  v-model="providerForm.key"
                  :label="t('settings.sso.providerKey')"
                  dense
                />
                <q-input
                  v-model="providerForm.display_name"
                  :label="t('settings.sso.displayName')"
                  dense
                />
                <q-toggle
                  v-model="providerForm.enabled"
                  :label="t('settings.users.active')"
                />
                <q-toggle
                  v-model="providerForm.allow_auto_create"
                  :label="t('settings.sso.allowAutoCreate')"
                />
                <template v-if="providerType === 'oidc'">
                  <q-input
                    v-model="providerForm.issuer"
                    :label="t('settings.sso.issuer')"
                    dense
                  />
                  <q-input
                    v-model="providerForm.authorization_endpoint"
                    :label="t('settings.sso.authorizationEndpoint')"
                    dense
                  />
                  <q-input
                    v-model="providerForm.token_endpoint"
                    :label="t('settings.sso.tokenEndpoint')"
                    dense
                  />
                  <q-input
                    v-model="providerForm.jwks_uri"
                    :label="t('settings.sso.jwksUri')"
                    dense
                  />
                  <q-input
                    v-model="providerForm.client_id"
                    :label="t('settings.sso.clientId')"
                    dense
                  />
                  <q-input
                    v-model="providerForm.client_secret"
                    :label="t('settings.sso.clientSecret')"
                    dense
                    type="password"
                  />
                  <q-input
                    v-model="providerForm.scopes"
                    :label="t('settings.sso.scopes')"
                    dense
                  />
                  <q-input
                    v-model="providerForm.group_claim"
                    :label="t('settings.sso.groupClaim')"
                    dense
                  />
                  <q-input
                    v-model="providerForm.email_claim"
                    :label="t('settings.sso.emailClaim')"
                    dense
                  />
                  <q-input
                    v-model="providerForm.name_claim"
                    :label="t('settings.sso.nameClaim')"
                    dense
                  />
                  <q-input
                    v-model="providerForm.subject_claim"
                    :label="t('settings.sso.subjectClaim')"
                    dense
                  />
                </template>
                <template v-else>
                  <q-input
                    v-model="providerForm.idp_entity_id"
                    :label="t('settings.sso.idpEntityId')"
                    dense
                  />
                  <q-input
                    v-model="providerForm.idp_sso_url"
                    :label="t('settings.sso.idpSsoUrl')"
                    dense
                  />
                  <q-input
                    v-model="providerForm.idp_x509_cert"
                    :label="t('settings.sso.idpX509Cert')"
                    type="textarea"
                    dense
                    autogrow
                  />
                  <q-input
                    v-model="providerForm.sp_entity_id"
                    :label="t('settings.sso.spEntityId')"
                    dense
                  />
                  <q-input
                    v-model="providerForm.acs_url"
                    :label="t('settings.sso.acsUrl')"
                    dense
                  />
                  <q-input
                    v-model="providerForm.group_attribute"
                    :label="t('settings.sso.groupAttribute')"
                    dense
                  />
                  <q-input
                    v-model="providerForm.email_attribute"
                    :label="t('settings.sso.emailAttribute')"
                    dense
                  />
                  <q-input
                    v-model="providerForm.name_attribute"
                    :label="t('settings.sso.nameAttribute')"
                    dense
                  />
                  <q-input
                    v-model="providerForm.subject_attribute"
                    :label="t('settings.sso.subjectAttribute')"
                    dense
                  />
                </template>
              </q-card-section>
              <q-card-actions align="right">
                <q-btn
                  v-close-popup
                  flat
                  :label="t('app.actions.cancel')"
                  color="primary"
                />
                <q-btn
                  flat
                  :label="t('app.actions.save')"
                  color="primary"
                  @click="saveProvider"
                />
              </q-card-actions>
            </q-card>
          </q-dialog>
        </q-tab-panel>

        <!-- COMPANY -->
        <q-tab-panel name="company">
          <div class="text-subtitle1 q-mb-sm">
            {{ t('settings.company.title') }}
          </div>
          <q-card
            flat
            bordered
            class="q-pa-md"
          >
            <div class="row q-gutter-sm items-center">
              <q-select
                v-model="companyLang"
                :options="languageOptions"
                :label="t('settings.company.defaultLanguage')"
                emit-value
                map-options
                class="col-3"
              />
              <q-btn
                color="primary"
                :label="t('app.actions.save')"
                :loading="savingCompany"
                @click="saveCompany"
              />
            </div>
          </q-card>
        </q-tab-panel>
        <q-tab-panel name="stockwire">
          <div class="text-subtitle1 q-mb-sm">
            {{ t('settings.stockwire.title') }}
          </div>
          <q-card
            flat
            bordered
            class="q-pa-md"
          >
            <div
              class="column q-gutter-md"
              style="max-width: 520px"
            >
              <q-input
                v-model="stockwireBaseUrl"
                :label="t('settings.stockwire.baseUrl')"
                placeholder="https://rental-api.sj-tech.se"
              />
              <q-input
                v-model="stockwirePublicUrl"
                :label="t('stockwire.publicUrl')"
                :hint="t('stockwire.publicUrlHint')"
                placeholder="http://host.docker.internal:8010"
              />
              <q-input
                v-model="stockwireApiKey"
                :label="t('settings.stockwire.apiKey')"
                :type="stockwireShowKey ? 'text' : 'password'"
                :hint="t('settings.stockwire.apiKeyHint')"
                :disable="stockwireHasKey && !stockwireShowKey"
              />
              <div class="row items-center q-gutter-sm">
                <q-toggle
                  v-model="stockwireEnabled"
                  :label="t('settings.stockwire.enabled')"
                />
                <q-toggle
                  v-if="stockwireHasKey"
                  v-model="stockwireShowKey"
                  :label="t('settings.stockwire.showKey')"
                />
              </div>
              <div class="row q-gutter-sm items-center">
                <q-btn
                  color="primary"
                  :label="t('app.actions.save')"
                  :loading="savingStockwire"
                  @click="saveStockwire"
                />
                <q-btn
                  color="secondary"
                  :label="t('settings.stockwire.test')"
                  :loading="testingStockwire"
                  @click="testStockwire"
                />
                <q-btn
                  color="positive"
                  icon="link"
                  :label="t('stockwire.connectRental')"
                  :loading="connectingRental"
                  @click="connectRental"
                />
                <q-chip
                  v-if="connectResult"
                  :color="connectResult.ok ? 'positive' : 'negative'"
                  :icon="connectResult.ok ? 'check' : 'error'"
                  square
                  dense
                >
                  {{ connectResultText }}
                </q-chip>
                <q-chip
                  v-if="testResult"
                  :color="testResult.ok ? 'positive' : 'negative'"
                  :icon="testResult.ok ? 'check' : 'error'"
                  square
                  dense
                >
                  {{ testResult.ok ? `${testResult.latency_ms} ms` : testResult.detail }}
                </q-chip>
              </div>
            </div>
          </q-card>

          <div class="text-subtitle1 q-mt-lg q-mb-sm">
            {{ t('stockwire.categoryMapTitle') }}
          </div>
          <div class="text-caption text-grey-7 q-mb-sm">
            {{ t('stockwire.categoryMapHint') }}
          </div>
          <q-card
            flat
            bordered
            class="q-pa-md"
          >
            <div style="max-width: 620px">
              <q-table
                :rows="categoryRows"
                :columns="categoryColumns"
                row-key="idx"
                dense
                hide-bottom
                :no-data-label="t('stockwire.notFound')"
              >
                <template #body-cell-categoryId="cell">
                  <q-td :props="cell">
                    <q-select
                      v-model="cell.row.categoryId"
                      :options="stockwireCategories"
                      option-value="id"
                      option-label="path"
                      emit-value
                      map-options
                      dense
                      borderless
                      use-input
                      input-debounce="0"
                      :placeholder="t('stockwire.searchPlaceholder')"
                    />
                  </q-td>
                </template>
                <template #body-cell-gearType="cell">
                  <q-td :props="cell">
                    <q-select
                      v-model="cell.row.gearType"
                      :options="gearTypeOptions"
                      dense
                      borderless
                      emit-value
                      map-options
                    />
                  </q-td>
                </template>
                <template #body-cell-actions="cell">
                  <q-td :props="cell">
                    <q-btn
                      dense
                      flat
                      round
                      size="sm"
                      icon="delete"
                      color="negative"
                      @click="categoryRows.splice(cell.row.idx, 1)"
                    />
                  </q-td>
                </template>
              </q-table>
              <div class="row q-gutter-sm q-mt-sm">
                <q-btn
                  flat
                  icon="add"
                  :label="t('app.actions.add')"
                  @click="categoryRows.push({ idx: categoryRows.length, categoryId: null, gearType: 'microphone' })"
                />
                <q-btn
                  color="primary"
                  :label="t('stockwire.saveMapping')"
                  :loading="savingMapping"
                  @click="saveMapping"
                />
              </div>
            </div>
          </q-card>
        </q-tab-panel>
      </q-tab-panels>
    </template>
  </q-page>
</template>

<script setup>
import { computed, onMounted, ref, watch } from 'vue'
import { useI18n } from 'vue-i18n'
import { api } from '@/boot/api'
import { useAuthStore } from '@/stores/auth'
import { SUPPORTED_LOCALES } from '../i18n'

const { t } = useI18n({ useScope: "global" })
const authStore = useAuthStore()
const isAdmin = computed(() => authStore.user?.role === 'admin')

const roleOptions = [
  { label: 'Admin', value: 'admin' },
  { label: 'Manager', value: 'manager' },
  { label: 'Viewer', value: 'viewer' },
]

const languageOptions = SUPPORTED_LOCALES.map((l) => ({
  label: t(`app.language.${l}`),
  value: l,
}))

/* ---------------- Company ---------------- */
const companyLang = ref('en')
const savingCompany = ref(false)

async function loadCompany() {
  try {
    const { data } = await api.get('/settings/company')
    companyLang.value = data.default_language || 'en'
  } catch {
    /* ignore */
  }
}

async function saveCompany() {
  savingCompany.value = true
  try {
    await api.put('/settings/company', { default_language: companyLang.value })
    localStorage.setItem('sw_company_default_language', companyLang.value)
  } finally {
    savingCompany.value = false
  }
}

/* ---------------- Stockwire integration ---------------- */
const stockwireBaseUrl = ref('')
const stockwireApiKey = ref('')
const stockwireEnabled = ref(false)
const stockwireHasKey = ref(false)
const stockwireShowKey = ref(false)
const savingStockwire = ref(false)
const testingStockwire = ref(false)
const testResult = ref(null)
const stockwirePublicUrl = ref('')
const connectingRental = ref(false)
const connectResult = ref(null)
const connectResultText = computed(() => {
  const r = connectResult.value;
  if (!r) return '';
  if (!r.code) return r.message || '';
  return t(`stockwire.connect.${r.code}`, { detail: r.message || '' });
});

async function loadStockwire() {
  try {
    const { data } = await api.get('/settings/stockwire')
    stockwireBaseUrl.value = data.base_url || ''
    stockwirePublicUrl.value = data.public_url || ''
    stockwireEnabled.value = !!data.enabled
    stockwireHasKey.value = !!data.has_api_key
    stockwireApiKey.value = ''
    stockwireShowKey.value = false
  } catch {
    /* ignore */
  }
}

async function saveStockwire() {
  savingStockwire.value = true
  try {
    await api.put('/settings/stockwire', {
      enabled: stockwireEnabled.value,
      base_url: stockwireBaseUrl.value,
      public_url: stockwirePublicUrl.value,
      api_key: stockwireApiKey.value || null,
    })
    if (stockwireApiKey.value) stockwireHasKey.value = true
    stockwireApiKey.value = ''
    stockwireShowKey.value = false
  } finally {
    savingStockwire.value = false
  }
}

async function connectRental() {
  connectingRental.value = true
  connectResult.value = null
  try {
    await saveStockwire()
    const { data } = await api.post('/settings/stockwire/connect-rental')
    connectResult.value = data
  } catch (e) {
    connectResult.value = {
      ok: false,
      message: e?.response?.data?.detail || t('stockwire.connectFailed'),
    }
  } finally {
    connectingRental.value = false
  }
}

async function testStockwire() {
  testingStockwire.value = true
  testResult.value = null
  try {
    const { data } = await api.post('/settings/stockwire/test')
    testResult.value = data
  } catch (e) {
    testResult.value = {
      ok: false,
      detail:
        e?.response?.data?.detail || t('settings.stockwire.notConfigured'),
    }
  } finally {
    testingStockwire.value = false
  }
}

/* ---------------- Stockwire category mapping ---------------- */
const categoryRows = ref([])
const stockwireCategories = ref([])
const savingMapping = ref(false)
const gearTypeOptions = [
  { label: t('stockwire.selectMixer'), value: 'mixer' },
  { label: t('stockwire.selectSource'), value: 'microphone' },
  { label: 'DI', value: 'di' },
  { label: 'Wireless', value: 'wireless' },
  { label: 'Stagebox', value: 'stagebox' },
  { label: t('stockwire.selectStand'), value: 'stand' },
  { label: 'Speaker', value: 'speaker' },
  { label: 'Monitor', value: 'monitor' },
  { label: 'Other', value: 'other' },
]
const categoryColumns = [
  { name: 'categoryId', label: t('stockwire.category'), field: 'categoryId', align: 'left' },
  { name: 'gearType', label: t('stockwire.gearType'), field: 'gearType', align: 'left', style: 'width: 200px' },
  { name: 'actions', label: '', field: 'actions', align: 'right', style: 'width: 50px' },
]

async function loadCategoryMap() {
  try {
    const [{ data: mapData }, { data: catData }] = await Promise.all([
      api.get('/settings/stockwire/category-map'),
      api.get('/stockwire/categories'),
    ])
    stockwireCategories.value = catData.categories || []
    const mapping = mapData.mapping || {}
    categoryRows.value = Object.entries(mapping).map(([categoryId, gearType], idx) => ({
      idx,
      categoryId: Number(categoryId),
      gearType,
    }))
  } catch {
    /* ignore */
  }
}

async function saveMapping() {
  savingMapping.value = true
  try {
    const mapping = {}
    for (const row of categoryRows.value) {
      if (row.categoryId && row.gearType) mapping[String(row.categoryId)] = row.gearType
    }
    await api.put('/settings/stockwire/category-map', { mapping })
  } finally {
    savingMapping.value = false
  }
}

const tab = ref('users')

/* ---------------- Users ---------------- */
const users = ref([])
const usersLoading = ref(false)
const userDialog = ref(false)
const editingUser = ref(null)
const savingUser = ref(false)
const userForm = ref(blankUser())

function blankUser() {
  return {
    email: '',
    password: '',
    first_name: '',
    last_name: '',
    role: 'viewer',
    is_active: true,
    preferred_language: 'en',
  }
}

const userColumns = [
  { name: 'email', label: t('settings.users.email'), field: 'email', align: 'left' },
  { name: 'name', label: t('settings.users.name'), field: (r) => `${r.first_name} ${r.last_name}`, align: 'left' },
  { name: 'role', label: t('settings.users.role'), field: 'role', align: 'left' },
  { name: 'active', label: t('settings.users.active'), field: 'is_active', align: 'left' },
  { name: 'actions', label: '', field: 'actions', align: 'right' },
]

async function loadUsers() {
  usersLoading.value = true
  try {
    const { data } = await api.get('/auth/users')
    users.value = data
  } catch {
    /* ignore */
  } finally {
    usersLoading.value = false
  }
}

function openCreateUser() {
  editingUser.value = null
  userForm.value = blankUser()
  userDialog.value = true
}

function openEditUser(row) {
  editingUser.value = row.id
  userForm.value = {
    email: row.email,
    password: '',
    first_name: row.first_name,
    last_name: row.last_name,
    role: row.role,
    is_active: row.is_active,
    preferred_language: row.preferred_language || 'en',
  }
  userDialog.value = true
}

async function saveUser() {
  savingUser.value = true
  try {
    const payload = { ...userForm.value }
    if (!payload.password) delete payload.password
    if (editingUser.value) {
      await api.put(`/auth/users/${editingUser.value}`, payload)
    } else {
      await api.post('/auth/users', payload)
    }
    userDialog.value = false
    await loadUsers()
  } finally {
    savingUser.value = false
  }
}

async function deleteUser(row) {
  if (!confirm(t('settings.users.deleteConfirm', { email: row.email }))) return
  await api.delete(`/auth/users/${row.id}`)
  await loadUsers()
}

/* ---------------- SSO ---------------- */
const ssoConfig = ref(null)
const ssoLoading = ref(false)
const savingSso = ref(false)
const providerDialog = ref(false)
const providerType = ref('oidc')
const editingProviderIndex = ref(null)
const providerForm = ref(blankProvider())

function blankProvider() {
  return {
    key: '',
    display_name: '',
    enabled: true,
    allow_auto_create: false,
    issuer: '',
    authorization_endpoint: '',
    token_endpoint: '',
    jwks_uri: '',
    client_id: '',
    client_secret: '',
    scopes: 'openid email profile',
    group_claim: 'groups',
    email_claim: 'email',
    name_claim: 'name',
    subject_claim: 'sub',
    idp_entity_id: '',
    idp_sso_url: '',
    idp_x509_cert: '',
    sp_entity_id: '',
    acs_url: '',
    group_attribute: 'groups',
    email_attribute: 'email',
    name_attribute: 'name',
    subject_attribute: 'nameID',
  }
}

const groupMappings = ref([])

watch(
  () => ssoConfig.value?.group_role_map,
  (map) => {
    groupMappings.value = Object.entries(map || {}).map(([group, role]) => ({ group, role }))
  },
  { immediate: true },
)

async function loadSso() {
  ssoLoading.value = true
  try {
    const { data } = await api.get('/auth/sso/config')
    ssoConfig.value = data
  } catch {
    /* ignore */
  } finally {
    ssoLoading.value = false
  }
}

function openProvider(type, index = null) {
  providerType.value = type
  editingProviderIndex.value = index
  if (index === null) {
    providerForm.value = blankProvider()
  } else {
    const list = type === 'oidc' ? ssoConfig.value.oidc_providers : ssoConfig.value.saml_providers
    providerForm.value = { ...list[index] }
  }
  providerDialog.value = true
}

function saveProvider() {
  const list = providerType.value === 'oidc' ? ssoConfig.value.oidc_providers : ssoConfig.value.saml_providers
  const clean = { ...providerForm.value }
  if (editingProviderIndex.value === null) {
    list.push(clean)
  } else {
    list[editingProviderIndex.value] = clean
  }
  providerDialog.value = false
}

async function saveSso() {
  savingSso.value = true
  try {
    const mapped = {}
    for (const row of groupMappings.value) {
      if (row.group && row.role) mapped[row.group] = row.role
    }
    ssoConfig.value.group_role_map = mapped
    await api.put('/auth/sso/config', ssoConfig.value)
    await loadSso()
  } finally {
    savingSso.value = false
  }
}

onMounted(() => {
  if (isAdmin.value) {
    loadUsers()
    loadSso()
    loadCompany()
    loadStockwire()
    loadCategoryMap()
  }
})

watch(isAdmin, (v) => {
  if (v) {
    loadUsers()
    loadSso()
    loadCompany()
    loadStockwire()
    loadCategoryMap()
  }
})
</script>
