<template>
  <q-page padding>
    <VenueRigTabs :venue-id="venueId" />
    <div class="row q-col-gutter-md">
      <div class="col-12 col-md-3">
        <q-card
          flat
          bordered
        >
          <q-card-section>
            <div class="text-subtitle1 q-mb-sm">
              {{ t('video.lists') }}
            </div>
            <q-list separator>
              <q-item
                v-for="l in videoStore.lists"
                :key="l.id"
                v-ripple
                clickable
                :active="selectedId === l.id"
                active-class="text-primary"
                @click="selectedId = l.id"
              >
                <q-item-section>{{ l.name }}</q-item-section>
              </q-item>
            </q-list>
            <div
              v-if="!videoStore.lists.length"
              class="text-grey-7 q-mt-sm"
            >
              {{ t('video.empty') }}
            </div>
            <div class="row items-center q-gutter-sm q-mt-sm">
              <q-input
                v-model="newName"
                dense
                class="col"
                :label="t('video.newListName')"
                @keyup.enter="addList"
              />
              <q-btn
                dense
                flat
                round
                icon="add"
                :aria-label="t('video.addList')"
                :disable="!newName.trim()"
                @click="addList"
              />
            </div>
          </q-card-section>
        </q-card>
      </div>
      <div class="col-12 col-md-9">
        <VideoListEditor
          v-if="selected"
          :key="selected.id"
          :list="selected"
          :owner="owner"
        />
        <div
          v-else
          class="text-grey q-pa-md text-center"
        >
          {{ t('video.empty') }}
        </div>
      </div>
    </div>
  </q-page>
</template>

<script setup>
import { computed, onMounted, ref, watch } from 'vue';
import { useRoute } from 'vue-router';
import { useI18n } from 'vue-i18n';
import { useVideoStore } from '@/stores/video';
import VideoListEditor from '@/components/VideoListEditor.vue';
import VenueRigTabs from '@/components/VenueRigTabs.vue';

const route = useRoute();
const { t } = useI18n({ useScope: 'global' });
const videoStore = useVideoStore();

const venueId = route.params.venueId;
const owner = computed(() => ({ kind: 'venue', id: venueId }));

const selectedId = ref(null);
const newName = ref('');

const selected = computed(
  () => videoStore.lists.find((l) => l.id === selectedId.value) || videoStore.lists[0] || null,
);

async function load() {
  await videoStore.fetchLists(owner.value);
  if (!selectedId.value && videoStore.lists.length) {
    selectedId.value = videoStore.lists[0].id;
  }
}

function addList() {
  const name = newName.value.trim();
  if (!name) return;
  videoStore.createList(owner.value, name).then((created) => {
    selectedId.value = created.id;
    newName.value = '';
  });
}

onMounted(load);
watch(owner, load);
</script>
