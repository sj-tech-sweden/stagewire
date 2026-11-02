import { useThemeStore } from '@/stores/theme';

// Apply the user's saved theme (light / dark / auto) as early as possible so the
// app paints in the correct mode. The store holds the mode and toggles Quasar's
// Dark plugin; for 'auto' it also tracks the OS preference live.
export default function () {
  const theme = useThemeStore();
  theme.init();
}
