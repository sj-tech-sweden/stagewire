const eslintPluginVue = require('eslint-plugin-vue');
const globals = require('globals');

module.exports = [
  {
    ignores: ['dist/**', '.quasar/**', 'node_modules/**', 'coverage/**'],
  },
  {
    files: ['**/*.{js,cjs,mjs,vue}'],
    languageOptions: {
      ecmaVersion: 2022,
      sourceType: 'module',
      globals: {
        ...globals.browser,
        ...globals.node,
      },
    },
  },
  ...eslintPluginVue.configs['flat/recommended'],
  {
    rules: {
      'vue/multi-word-component-names': 'off',
    },
  },
];
