// Things that go on the plot but are not devices: people, instruments and furniture. They give the
// plan context and, when linked, enrich the lists (a performer linked to a microphone or a channel
// puts their name on the channel). Sizes are cm; `labelKey` is an i18n key under stagePlot.types.
export const OBJECT_TYPES = [
  { type: 'performer', labelKey: 'stagePlot.types.performer', icon: 'person', color: '#35A853', w: 60, h: 60 },
  { type: 'instrument', labelKey: 'stagePlot.types.instrument', icon: 'music_note', color: '#26A69A', w: 90, h: 60 },
  { type: 'table', label: 'Table', labelKey: 'workspace.objectTable', icon: 'table_restaurant', color: '#8D6E63', w: 160, h: 80 },
  { type: 'chair', label: 'Chair', labelKey: 'workspace.objectChair', icon: 'chair', color: '#A1887F', w: 45, h: 45 },
  { type: 'riser', labelKey: 'stagePlot.types.riser', icon: 'layers', color: '#607D8B', w: 180, h: 90 },
  { type: 'dais', labelKey: 'stagePlot.types.dais', icon: 'crop_16_9', color: '#78909C', w: 220, h: 120 },
  { type: 'screen', labelKey: 'stagePlot.types.screen', icon: 'tv', color: '#78909C', w: 200, h: 20 },
  { type: 'custom', label: 'Custom', labelKey: 'stagePlot.custom', icon: 'add', color: '#90A4AE', w: 60, h: 60 },
];

// Gear that is drawn on the plot as an element and linked to a device (`deviceType`; `createDevice`
// makes one when no unplaced device of that type exists). Speakers carry the coverage they throw
// (angle in degrees, distance in metres) and face the audience by default.
export const GEAR_ELEMENTS = [
  { type: 'microphone', labelKey: 'stagePlot.types.microphone', icon: 'mic', color: '#AB47BC', w: 26, h: 26, group: 'audio' },
  { type: 'wireless_receiver', labelKey: 'stagePlot.types.wirelessReceiver', icon: 'settings_input_antenna', color: '#7E57C2', w: 48, h: 48, group: 'audio' },
  { type: 'di', label: 'DI', labelKey: 'workspace.objectDi', icon: 'crop_square', color: '#5C6BC0', w: 24, h: 18, group: 'audio' },
  { type: 'multicore', label: 'Multicore', labelKey: 'workspace.objectMulticore', icon: 'cable', color: '#8D6E63', w: 32, h: 120, group: 'audio' },
  { type: 'speaker_main', labelKey: 'stagePlot.types.speakerMain', icon: 'volume_up', color: '#FF7043', w: 42, h: 72, coverageAngle: 90, coverageDistance: 30, rotation: 180, group: 'audio', speaker: true },
  { type: 'speaker_sub', labelKey: 'stagePlot.types.speakerSub', icon: 'graphic_eq', color: '#F4511E', w: 60, h: 60, coverageAngle: 360, coverageDistance: 15, rotation: 180, group: 'audio', speaker: true },
  { type: 'speaker_delay', labelKey: 'stagePlot.types.speakerDelay', icon: 'speaker', color: '#FFA726', w: 42, h: 60, coverageAngle: 60, coverageDistance: 40, rotation: 180, group: 'audio', speaker: true },
  { type: 'monitor', label: 'Monitor', labelKey: 'workspace.objectMonitor', icon: 'headphones', color: '#26C6DA', w: 46, h: 36, coverageAngle: 60, coverageDistance: 8, group: 'audio', speaker: true },
  { type: 'mixer', labelKey: 'stagePlot.types.mixer', icon: 'tune', color: '#7E57C2', w: 90, h: 45, deviceType: 'mixer', group: 'audio' },
  { type: 'camera', labelKey: 'stagePlot.types.camera', icon: 'videocam', color: '#42A5F5', w: 40, h: 30, deviceType: 'camera', createDevice: true, group: 'video' },
  { type: 'projector', labelKey: 'stagePlot.types.projector', icon: 'slideshow', color: '#AB47BC', w: 40, h: 25, deviceType: 'projector', createDevice: true, group: 'video' },
  { type: 'switcher', labelKey: 'stagePlot.types.switcher', icon: 'memory', color: '#26A69A', w: 80, h: 45, deviceType: 'switcher', group: 'video' },
  { type: 'movingLight', labelKey: 'stagePlot.types.movingLight', icon: 'light_mode', color: '#FFCA28', w: 40, h: 30, deviceType: 'fixture', createDevice: true, group: 'lighting' },
  { type: 'staticLight', labelKey: 'stagePlot.types.staticLight', icon: 'highlight', color: '#FFA726', w: 36, h: 24, deviceType: 'fixture', createDevice: true, group: 'lighting' },
  { type: 'ledFixture', labelKey: 'stagePlot.types.ledFixture', icon: 'view_week', color: '#FFEE58', w: 90, h: 22, deviceType: 'fixture', createDevice: true, group: 'lighting' },
  { type: 'hazer', labelKey: 'stagePlot.types.hazer', icon: 'cloud', color: '#BDBDBD', w: 30, h: 30, deviceType: 'fixture', createDevice: true, group: 'lighting' },
];

export const SPEAKER_TYPES = new Set(GEAR_ELEMENTS.filter((g) => g.speaker).map((g) => g.type));
export const isSpeakerType = (type) => SPEAKER_TYPES.has(type);

export const objectType = (type) =>
  OBJECT_TYPES.find((o) => o.type === type) || GEAR_ELEMENTS.find((o) => o.type === type) || null;

// Colour a plot element is drawn with on the canvas (null for types without one).
export const objectColor = (element) => objectType(element?.attributes?.element_type)?.color || null;
