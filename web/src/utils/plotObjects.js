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

export const objectType = (type) => OBJECT_TYPES.find((o) => o.type === type) || null;

// Colour a plot element is drawn with on the canvas (null for types without one).
export const objectColor = (element) => objectType(element?.attributes?.element_type)?.color || null;
