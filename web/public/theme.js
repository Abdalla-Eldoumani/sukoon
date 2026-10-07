// Sets the theme before the page paints, so a stored choice never flashes the default first.
// lib/theme/theme.ts does the same once the app has loaded; a test keeps the two in step.
;(function () {
  var ids = ['dark', 'light', 'contrast', 'parchment', 'midnight']
  var theme = null
  try {
    theme = window.localStorage.getItem('sukoon.theme')
  } catch {
    // Blocked storage: the computer's preference decides below.
  }
  if (ids.indexOf(theme) < 0) {
    var ask = function (q) {
      return !!(window.matchMedia && window.matchMedia(q).matches)
    }
    theme = ask('(prefers-contrast: more)') ? 'contrast' : ask('(prefers-color-scheme: light)') ? 'light' : 'dark'
  }
  document.documentElement.setAttribute('data-theme', theme)
})()
