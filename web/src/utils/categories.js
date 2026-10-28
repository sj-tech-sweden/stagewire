// Stage-plot categories. Elements are sorted by their type; anything else is sorted by
// the device it is linked to, so a camera or a switcher on the plot shows with video.
export const CATEGORIES = ['sound', 'video', 'stage', 'other'];

const ELEMENT_CATEGORY = {
  performer: 'stage',
  instrument: 'stage',
  dais: 'stage',
  riser: 'stage',
  microphone: 'sound',
  di: 'sound',
  multicore: 'sound',
  speaker: 'sound',
  speaker_main: 'sound',
  speaker_sub: 'sound',
  speaker_delay: 'sound',
  monitor: 'sound',
  mixer: 'sound',
  camera: 'video',
  switcher: 'video',
  screen: 'video',
  projector: 'video',
  moving_light: 'stage',
  static_light: 'stage',
  led_fixture: 'stage',
  hazer: 'stage',
};

const DEVICE_CATEGORY = {
  digital_stagebox: 'sound',
  analog_stagebox: 'sound',
  mixer: 'sound',
  split: 'sound',
  direct: 'sound',
  amp: 'sound',
  speaker: 'sound',
  monitor: 'sound',
  switcher: 'video',
  router: 'video',
  multiviewer: 'video',
  converter: 'video',
  encoder: 'video',
  recorder: 'video',
  camera: 'video',
  lens: 'video',
  ptz_camera: 'video',
  computer: 'video',
  screen: 'video',
  projector: 'video',
  fixture: 'stage',
};

// Network equipment and patchbays can carry any of the signals, so they sit under Other.
export function categoryOfDeviceType(deviceType) {
  return DEVICE_CATEGORY[deviceType] || 'other';
}

export function categoryOfElement(element, deviceType) {
  const byType = ELEMENT_CATEGORY[element.element_type];
  if (byType) return byType;
  if (element.linked_device_id && deviceType) return categoryOfDeviceType(deviceType);
  return 'other';
}
