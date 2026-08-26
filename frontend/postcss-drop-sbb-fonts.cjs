/**
 * PostCSS: entfernt @font-face-Regeln, die auf SBB-Infrastruktur zeigen.
 *
 * Warum: Lynes core.css und standard-theme.css deklarieren die Familie "SBB"
 * mit `src: url("https://cdn.app.sbb.ch/fonts/...")`. Die Schrift ist NICHT
 * Teil des MIT-lizenzierten Pakets — sie ist die proprietaere Hausschrift der
 * SBB und wird zur Laufzeit von deren Servern nachgeladen.
 *
 * styles.scss ueberschreibt bereits --sbb-typo-font-family auf IBM Plex Sans
 * (SIL OFL, selbst gehostet), womit die Regeln tot sind: ein Browser laedt eine
 * Schrift nur, wenn etwas sie matcht. Fuer eine Open-Source-Freigabe (OpenRail)
 * reicht "tot" aber nicht — die URLs stuenden weiterhin sichtbar im
 * ausgelieferten CSS-Artefakt und wuerden bei jeder Code-Pruefung auffallen.
 *
 * Das Plugin loescht ausschliesslich @font-face-Bloecke, deren src auf
 * SBB_FONT_HOST zeigt. Alles andere aus Lyne bleibt unangetastet, und ein
 * Lyne-Upgrade kann die Regeln nicht wieder einschleusen.
 *
 * Kontrolle: `npm run build` und danach
 *   grep -c "cdn.app.sbb.ch" dist/frontend/browser/*.css   → 0
 */
const SBB_FONT_HOST = 'cdn.app.sbb.ch';

module.exports = () => ({
  postcssPlugin: 'drop-sbb-fonts',
  AtRule: {
    'font-face': (atRule) => {
      let pointsAtSbb = false;
      atRule.walkDecls('src', (decl) => {
        if (decl.value.includes(SBB_FONT_HOST)) pointsAtSbb = true;
      });
      if (pointsAtSbb) atRule.remove();
    },
  },
});
module.exports.postcss = true;
