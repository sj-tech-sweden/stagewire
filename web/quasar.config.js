module.exports = function (/* ctx */) {
  return {
    boot: ['api', 'theme', 'icons', 'i18n'],

    css: ['app.css'],

    framework: {
      config: {
        brand: {
          primary: '#3F873F',
          secondary: '#26A69A',
          accent: '#35A853',
          dark: '#0C1114',
          positive: '#3F873F',
          negative: '#E65656',
          info: '#3F873F',
          warning: '#F7B84B',
        },
      },
      plugins: ['Dark', 'Notify', 'Dialog'],
      lang: 'en-US',
      iconSet: 'material-icons',
    },

    build: {
      target: {
        browser: ['es2022'],
        node: 'node20',
      },
      vueRouterMode: 'history',
      distDir: 'dist/pwa',
      env: {
        API_BASE_URL: process.env.API_BASE_URL || 'http://localhost:8010',
      },
    },

    devServer: {
      host: '0.0.0.0',
      port: 9010,
      open: false,
    },

    sourceFiles: {
      rootComponent: 'src/App.vue',
      router: 'src/router/index.js',
      store: 'src/stores/index.js',
    },

    packageJson: {
      productName: 'Stagewire',
      description: 'Stage plots & patch sheets',
      author: 'SJ Tech Sweden',
    },

    extras: ['material-icons'],
  };
};
