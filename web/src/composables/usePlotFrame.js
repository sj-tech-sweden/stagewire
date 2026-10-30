import { computed, ref, watch } from 'vue';
import { api } from '@/boot/api';
import { buildCoverageCanvas, frameFromJob } from '@/utils/plotFrame';
import { cameraShapes, projectorShapes } from '@/utils/plotViews';

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
  const job = ref(null);
  const outlets = ref([]);
  const coverage = ref(null);
  const show = {
    outlets: ref(saved('sw_ws_outlets', true)),
    audience: ref(saved('sw_ws_audience', true)),
    coverage: ref(saved('sw_ws_coverage', false)),
    camera: ref(saved('sw_ws_camera', false)),
    projector: ref(saved('sw_ws_projector', false)),
  };
  const cameraMode = ref(saved('sw_ws_camera_mode', 'range'));
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
      console.error('Failed to load coverage', err);
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
    } catch (err) {
      console.error('Failed to load the stage frame', err);
    }
    await Promise.all([loadCoverage(), loadCameraSpecs()]);
  }

  // Camera specs (sensor, focal range) are looked up per plot element on the server.
  async function loadCameraSpecs() {
    if (!show.camera.value) return;
    try {
      cameraSpecs.value = (await api.get(`/jobs/${jobId}/camera-specs`)).data || {};
    } catch (err) {
      console.error('Failed to load camera specs', err);
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
    coverageImage,
    show,
    cameraMode,
    load,
    loadCoverage,
    loadCameraSpecs,
    viewShapes,
  };
}
