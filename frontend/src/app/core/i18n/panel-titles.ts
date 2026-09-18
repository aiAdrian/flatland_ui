/**
 * Panel titles that ship with the app, mapped to their translation key.
 *
 * Matched by the title text rather than by panel type: a layout someone saved
 * with their own title ("Meine Züge") keeps it in every language, while the
 * titles the presets and the three-column layout bring are translated. Several
 * presets were written in German before English became the source language —
 * those map to the same keys as their English counterparts.
 */
export const STOCK_PANEL_TITLES: Readonly<Record<string, string>> = {
  'Situation Summary': 'panels.situationSummary',
  Situation: 'panels.situation',
  Notifications: 'panels.notifications',
  Ereignisse: 'panels.events',
  Agents: 'panels.agents',
  Trains: 'panels.trains',
  Züge: 'panels.trains',
  'Trains (Dispositionstabelle)': 'panels.trainsTable',
  'Flatland Map': 'panels.map',
  'Graphic Timetable': 'panels.graphicTimetable',
  Impact: 'panels.impact',
  Folgen: 'panels.consequences',
  Scenario: 'panels.scenario',
  Recommendations: 'panels.recommendations',
  Empfehlung: 'panels.recommendation',
  'What-if Compare': 'panels.whatifCompare',
  'KPI Filter': 'panels.kpiFilter',
  'Director Weights': 'panels.directorWeights',
  'Director Directive': 'panels.directorDirective',
  'Streckenspiegel & ZWL': 'panels.viewsMapZwl',
  'Streckenplan · ZWL · Fahrplan': 'panels.viewsAll',
  'View Tabs': 'panels.viewTabs',
  Reflection: 'panels.reflection',
  'Co-Learning Reflection': 'panels.coLearningReflection',
  'Co-Learning Effect': 'panels.coLearningEffect',
  Timetable: 'panels.timetable',
  Fahrplan: 'panels.timetable',
  'Combined Actions': 'panels.combinedActions',
  'Problem Overview': 'panels.problemOverview',
  'Zug-Detail': 'panels.trainDetail',
  'Agent Inspector': 'panels.agentInspector',
  'Decision Log': 'panels.decisionLog',
  Entscheidungsprotokoll: 'panels.decisionLog',
  'Lage: Risiko & Auswirkung': 'panels.riskAndImpact',
  'Plan / KI / Mensch': 'panels.planAiHuman',
  'Risk & Uncertainty': 'panels.riskUncertainty',
  'AI Activity': 'panels.aiActivity',
  'Goal Achievement': 'panels.goalAchievement',
  'Strategy Options (A/B/C)': 'panels.strategyOptions',
  'Strategy Impact Forecast': 'panels.strategyForecast',
  'Strategy Reflection': 'panels.strategyReflection',
  'Shift Review': 'panels.shiftReview',
  'Layer Visibility': 'panels.layerVisibility',
  Toolbar: 'panels.toolbar',
};
