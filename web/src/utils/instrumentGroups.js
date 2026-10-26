export const INSTRUMENT_GROUP_COLORS = Object.freeze({
  drums: '#E53935',
  percussion: '#FB8C00',
  bass: '#8E24AA',
  guitars: '#3949AB',
  keys: '#00897B',
  brass: '#F9A825',
  vocals: '#D81B60',
  playback: '#546E7A',
  other: '#78909C',
});

export const INSTRUMENT_GROUP_KEYS = Object.keys(INSTRUMENT_GROUP_COLORS);

export function instrumentGroupColor(group) {
  return INSTRUMENT_GROUP_COLORS[group] || INSTRUMENT_GROUP_COLORS.other;
}

export function channelColor(channel) {
  if (channel?.color_code && /^#[0-9a-f]{6}$/i.test(channel.color_code)) {
    return channel.color_code;
  }
  return instrumentGroupColor(channel?.instrument_group);
}

export function channelTextColor(channel) {
  return !channel?.color_code && channel?.instrument_group === 'brass' ? 'dark' : 'white';
}
