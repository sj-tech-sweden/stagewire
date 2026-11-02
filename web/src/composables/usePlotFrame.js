import { computed, ref, watch } from 'vue';
import { Notify } from 'quasar';
import { i18n } from '@/i18n';
import { apiErrorText } from '@/utils/errors';
import { api } from '@/boot/api';
import { buildCoverageCanvas, frameFromJob } from '@/utils/plotFrame';
import { cameraShapes, projectorShapes } from '@/utils/plotViews';
import { emptyCablePlan } from '@/utils/cables';

const saved = (key, fallback) => {
  try {
    const raw = localStorage.getItem(key);
    return raw === null ? fallback : JSON.parse(raw);
  } catch {
    return fallback;
  }
};

// Loads what surrounds the gear on the workspace canvas (the job's stage and venue, the venue's
// outlets and, when switched on, the sound coverage) and remembers which layers are shown.
// Coverage is computed on the server from the placed speakers, so it is only requested while
// the layer is on and the job has a venue size.
export function usePlotFrame(jobId) {
  const t = (key) => i18n.global.t(key);
  const job = ref(null);
  const outlets = ref([]);
  const groups = ref([]);
  const coverage = ref(null);
  const show = {
    outlets: ref(saved('sw_ws_outlets', true)),
    audience: ref(saved('sw_ws_audience', true)),
    coverage: ref(saved('sw_ws_coverage', false)),
    camera: ref(saved('sw_ws_camera', false)),
    projector: ref(saved('sw_ws_projector', false)),
    cables: ref(saved('sw_ws_cables', false)),
  };
  const cameraMode = ref(saved('sw_ws_camera_mode', 'range'));

  // Cable routing: cableways and settings are the job's cable_plan, saved as a whole (a counter
  // makes sure an older save that finishes late cannot bring back an older plan).
  const cablePlan = computed(() => emptyCablePlan(job.value?.cable_plan));
  let planSeq = 0;
  async function savePlan(next) {
    const seq = ++planSeq;
    const previous = job.value?.cable_plan;
    job.value = { ...job.value, cable_plan: next };
    try {
      const { data } = await api.patch(`/jobs/${jobId}`, { cable_plan: next });
      if (seq === planSeq) job.value = { ...job.value, cable_plan: data.cable_plan };
    } catch (err) {
      // show what is really saved again, and say so, instead of a plan that is gone after a reload
      if (seq === planSeq) job.value = { ...job.value, cable_plan: previous };
      Notify.create({ type: 'negative', message: `${t('cables.saveFailed')}: ${apiErrorText(err)}` });
    }
  }
  const cameraSpecs = ref({});
  for (const [name, flag] of Object.entries(show)) {
    watch(flag, (value) => {
      try {
        localStorage.setItem(`sw_ws_${name}`, JSON.stringify(value));
      } catch {
        // storage can be blocked; the toggle still works for this visit
      }
    });
  }

  const frame = computed(() => frameFromJob(job.value));
  const coverageImage = computed(() =>
    show.coverage.value && coverage.value?.cols ? buildCoverageCanvas(coverage.value) : null,
  );

  async function loadCoverage() {
    if (!show.coverage.value || !frame.value.hasVenue) {
      coverage.value = null;
      return;
    }
    try {
      coverage.value = (await api.get(`/jobs/${jobId}/coverage`, { params: { cell_cm: 25 } })).data;
    } catch (err) {
      Notify.create({ type: 'warning', message: `${t('workspace.coverageFailed')}: ${apiErrorText(err)}` });
    }
  }

  async function load() {
    try {
      const [jobRes, outletRes] = await Promise.all([
        api.get(`/jobs/${jobId}`),
        api.get(`/jobs/${jobId}/power-outlets`),
      ]);
      job.value = jobRes.data;
      outlets.value = outletRes.data.filter((o) => o.x_cm != null && o.y_cm != null);
      groups.value = job.value.venue_id ? (await api.get(`/venues/${job.value.venue_id}/power-groups`)).data : [];
    } catch (err) {
      Notify.create({ type: 'negative', message: `${t('workspace.frameFailed')}: ${apiErrorText(err)}` });
    }
    await Promise.all([loadCoverage(), loadCameraSpecs()]);
  }

  // Camera specs (sensor, focal range) are looked up per plot element on the server.
  async function loadCameraSpecs() {
    if (!show.camera.value) return;
    try {
      cameraSpecs.value = (await api.get(`/jobs/${jobId}/camera-specs`)).data || {};
    } catch (err) {
      Notify.create({ type: 'warning', message: `${t('workspace.cameraSpecsFailed')}: ${apiErrorText(err)}` });
    }
  }

  // The venue area, in stage-relative cm, that cones are clipped to.
  const box = computed(() => ({
    minX: -frame.value.stageX,
    minY: -frame.value.stageY,
    maxX: frame.value.width - frame.value.stageX,
    maxY: frame.value.height - frame.value.stageY,
  }));

  // `elements` are the plot elements in the plot page's shape (see elementsFromGraph) and
  // `deviceOf` finds the device an element is linked to (projectors read their throw from it).
  function viewShapes(elements, deviceOf) {
    return [
      ...(show.camera.value
        ? cameraShapes({ elements, specs: cameraSpecs.value, mode: cameraMode.value, box: box.value })
        : []),
      ...(show.projector.value ? projectorShapes({ elements, deviceOf, box: box.value }) : []),
    ];
  }

  watch(cameraMode, (value) => {
    try {
      localStorage.setItem('sw_ws_camera_mode', JSON.stringify(value));
    } catch {
      // storage can be blocked
    }
  });
  watch(show.coverage, loadCoverage);
  watch(show.camera, loadCameraSpecs);
  return {
    job,
    frame,
    outlets,
    groups,
    coverageImage,
    show,
    cameraMode,
    cablePlan,
    savePlan,
    load,
    loadCoverage,
    loadCameraSpecs,
    viewShapes,
  };
}
