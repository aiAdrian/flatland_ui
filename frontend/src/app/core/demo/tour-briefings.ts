/**
 * Tour briefings — the opening and closing pages a tour can wrap around its
 * modes. Content only; rendered by `features/tour-briefing`. A tour opts in via
 * `Tour.briefingId`.
 *
 * The first briefing frames the expert interviews for the CAS thesis "Evaluating
 * AI-Based Co-Learning Extensions for Railway Traffic Management Using Monte
 * Carlo Simulation" (D. Boos, iimt / Uni Fribourg). Module list, Kolb mapping and
 * the two loops follow that thesis' Tables 1 and 2.
 */

import { InteractionMode } from '../events/event-types';
import { ModeIntro } from './mode-intro-configs';

export interface BriefingSection {
  heading: string;
  body?: string;
  items?: string[];
  ordered?: boolean;
}

export type ModuleStatus = 'live' | 'partial' | 'concept';

export interface BriefingModule {
  name: string;
  area: string;
  kolbPhase: string;
  does: string;
  inTour: string;
  status: ModuleStatus;
  statusNote: string;
}

export interface KolbPhase {
  name: string;
  supported: boolean;
  note: string;
}

export interface LoopStep {
  actor: string;
  action: string;
}

export type GuideStepId =
  | 'detect'
  | 'assess'
  | 'alternatives'
  | 'decide'
  | 'execute'
  | 'reflect'
  | 'shift-summary'
  | 'event-simulation'
  | 'ai-learns';

export type GuideLoop = 'operational' | 'learning';

/** One step of the tour's interaction flow, shown in the guide strip. */
export interface TourGuideStep {
  id: GuideStepId;
  loop: GuideLoop;
  title: string;
  /** What to do or look at while this is the current step. */
  hint: string;
  /** Panel to highlight while this step is current. */
  panelType?: string;
  /** A Co-Learning module, as opposed to the TMS base. */
  module?: boolean;
  /** Takes place after the episode (sandbox); never ticked during the run. */
  afterEpisode?: boolean;
}

export interface TourBriefing {
  id: string;
  /** The interaction flow as a checklist that ticks itself during the run. */
  guide?: TourGuideStep[];
  /** After the shift, show the tour debrief (steps 7-9) instead of the Director review. */
  debrief?: boolean;
  /** Run the tour under a fresh operator id, so interviewees never inherit each other's preferences. */
  freshOperatorProfile?: boolean;
  /** Pause after a decision and ask "why?" in a dialog instead of only in the reflection panel. */
  reasonDialog?: boolean;
  /**
   * Keep the impact panel to the assessment and leave the options to the
   * proposals panel — the split of thesis Table 1, where "Risk & Impact
   * Assessment" and the "Alternatives Module" are two modules. Off elsewhere, so
   * the study conditions keep the panel that decides and assesses in one place.
   */
  assessmentOnly?: boolean;
  /**
   * The app language while this tour runs. Tour-owned text keeps its own
   * language, but the panels follow the app setting — without this a German
   * tour started from the English default shows a mix. The previous language
   * comes back when the tour ends.
   */
  language?: 'en' | 'de' | 'fr';
  /**
   * Name every train on the map and give it a larger click target. On a long
   * corridor shown at about 0.4 scale a train is a dot of a few pixels, and the
   * interview's first pilot run lost time hitting it.
   */
  mapTrainLabels?: boolean;
  /** Replaces the default intro of a mode while this tour runs. */
  modeIntros?: Partial<Record<InteractionMode, ModeIntro>>;
  /** Panel type → module name: these panels carry a "Co-Learning" badge. */
  moduleBadges?: Record<string, string>;
  /** Start the map on this column range (first, last), for long corridors. */
  mapFocusCols?: [number, number];
  opening: {
    eyebrow: string;
    title: string;
    lead: string;
    byline: string;
    sections: BriefingSection[];
    proceedLabel: string;
  };
  closing: {
    eyebrow: string;
    title: string;
    lead: string;
    kolbIntro: string;
    kolb: KolbPhase[];
    loops: { name: string; steps: LoopStep[] }[];
    loopsNote: string;
    modules: BriefingModule[];
    statusLabels: Record<ModuleStatus, string>;
    estimationReminder: string;
    disclaimer: string;
    sources: string;
  };
}

const PROTOTYPE_DISCLAIMER =
  'Die Widgets sind Entwürfe, nicht die finalen Oberflächen. Inhalte und Darstellung können sich noch ändern. Sie zeigen, in welche Richtung die Erweiterung gehen soll.';

export const TOUR_BRIEFINGS: TourBriefing[] = [
  {
    id: 'co-learning-cost-benefit',
    // Ziegelbrücke (col 71) to Walenstadt (col 124): both starts, the shared
    // track after Weesen and the single-track section in between.
    mapFocusCols: [69, 126],
    debrief: true,
    freshOperatorProfile: true,
    // For the demo: makes step 6 hard to miss. The interview layout has no
    // reflection panel, so switching this off needs that panel back in the preset.
    reasonDialog: true,
    assessmentOnly: true,
    language: 'de',
    mapTrainLabels: true,
    // Steps 1-9 of the thesis' interaction flow (Table 2): operational loop 1-5,
    // learning loop 6-9, with shift summary and event simulation after the episode.
    guide: [
      {
        id: 'detect',
        loop: 'operational',
        title: 'Konflikt erkennen',
        hint: 'Starte mit «Play» und beobachte die Strecke. Nach einer knappen halben Minute bleibt ein Zug im Einspurabschnitt stehen, und das TMS meldet die Störung links.',
      },
      {
        id: 'assess',
        loop: 'operational',
        module: true,
        panelType: 'impact',
        title: 'Risiko & Auswirkung',
        hint: 'Neu: «Lage: Risiko & Auswirkung» zeigt, welcher Zug betroffen ist, wie lange er stehen würde und welche Massnahmen möglich sind. Entschieden wird hier nicht; der Zug wartet.',
      },
      {
        id: 'alternatives',
        loop: 'operational',
        module: true,
        panelType: 'proposal-compare',
        title: 'Alternativen',
        hint: 'Neu: Die KI bietet Optionen an, ohne eine zu empfehlen. Unter «Plan / KI / Mensch» siehst du vorab, was der Plan, der KI-Vorschlag und deine eigene Wahl für den Zug bedeuten.',
      },
      {
        id: 'decide',
        loop: 'operational',
        panelType: 'proposal-compare',
        title: 'Entscheiden',
        hint: 'Wähle unter «Plan / KI / Mensch» eine Option für den betroffenen Zug und übernimm sie.',
      },
      {
        id: 'execute',
        loop: 'operational',
        title: 'Umsetzen',
        hint: 'Das TMS setzt deine Wahl um. Lass die Simulation weiterlaufen.',
      },
      {
        id: 'reflect',
        loop: 'learning',
        module: true,
        title: 'Reflexion',
        hint: 'Neu: Nach deiner Entscheidung hält die Simulation an und fragt nach deinem Grund. Wähle einen Grund, danach «Ja, als Regel» oder «Nur diesmal».',
      },
      {
        id: 'shift-summary',
        loop: 'learning',
        module: true,
        afterEpisode: true,
        title: 'Schichtbilanz',
        hint: 'Nach der Episode: alle Massnahmen und ihre Wirkung über die ganze Schicht.',
      },
      {
        id: 'event-simulation',
        loop: 'learning',
        module: true,
        afterEpisode: true,
        title: 'Event-Simulation',
        hint: 'Nach der Episode, in der Sandbox: den erlebten Vorfall mit einer anderen Entscheidung nochmals durchspielen.',
      },
      {
        id: 'ai-learns',
        loop: 'learning',
        module: true,
        title: 'KI lernt',
        hint: 'Neu: Die KI übernimmt bestätigte Gründe in ihr Modell. Nach der Schicht siehst du das als Lern-Karte.',
      },
    ],
    // Panels that belong to the Co-Learning extension: they carry the violet
    // edge. The name is the tooltip and the wording used in the closing
    // overview — the panels themselves are no longer labelled.
    moduleBadges: {
      impact: 'Risiko- und Auswirkungsanalyse',
      'proposal-compare': 'Auswirkungsanalyse: Plan, KI-Vorschlag und deine Wahl',
      'decision-log': 'Grundlage für Reflexion und Lernen',
    },
    modeIntros: {
      'co-learning': {
        mode: 'co-learning',
        wp: 'Co-Learning · Walensee',
        title: 'Eine Störung am Einspurabschnitt',
        tagline: 'Die KI zeigt Auswirkungen und Optionen. Du entscheidest und lernst daraus.',
        whatHappens:
          'Strecke Pfäffikon SZ–Chur am Walensee, von Ziegelbrücke bis Walenstadt, mit einem einspurigen Abschnitt. Drei Züge fahren nach Fahrplan. Nach einer knappen halben Minute bleibt ein Zug mitten im Einspurabschnitt stehen, und der Zug dahinter läuft auf ihn auf. Wie es weitergeht, entscheidest du.',
        focusView:
          'In der Mitte Streckenspiegel und Zeit-Weg-Linien (ZWL) als Tabs, darunter der Fahrplan. Den Streckenspiegel ziehst du mit der Maus seitlich, mit dem Mausrad zoomst du. Rechts liegen die Co-Learning-Module.',
        yourRole:
          'Du disponierst. Die KI rankt nichts und empfiehlt nichts: Du wählst selbst, vergleichst danach mit einer Alternative und denkst über deine Entscheidung nach.',
        whatYouCanControl: [
          'Die Simulation starten, pausieren oder schrittweise laufen lassen',
          'Für einen betroffenen Zug eine Option wählen',
          'Unter «Plan / KI / Mensch» vorab vergleichen: Plan, KI-Vorschlag und deine eigene Wahl',
          'Nach einer Entscheidung den Grund angeben, als Regel oder nur für diesmal',
        ],
        watchFor: [
          'Panels mit violettem Rand sind die neue Erweiterung. Alles andere steht für das TMS als Ganzes.',
          'Optionen erscheinen ohne Ranking und ohne «empfohlen»',
          'Blau steht für deine Entscheidung, gelb für die Variante der KI',
          'Oben führt ein Leitfaden durch die neun Schritte. Das jeweils nächste Modul wird hervorgehoben.',
        ],
        goal:
          'Es geht nicht um die perfekte Disposition, sondern um ein Gefühl dafür, was die Module leisten, als Grundlage für deine Schätzung.',
        note: PROTOTYPE_DISCLAIMER,
        labels: {
          stepPrefix: 'Modus',
          stepOf: 'von',
          whatHappens: 'Was passiert',
          focusView: 'Wohin du schaust',
          yourRole: 'Deine Rolle',
          control: 'Was du tun kannst',
          watchFor: 'Worauf du achtest',
          goal: 'Ziel',
          start: 'Szenario starten',
          exit: 'Tour beenden',
        },
      },
    },
    opening: {
      eyebrow: 'Experteninterview · Co-Learning',
      title: 'Co-Learning in der Disposition erleben',
      lead:
        'Eine Viertelstunde Co-Learning zum Ausprobieren, als gemeinsame Grundlage für das Interview danach.',
      byline: 'Daniel Boos · CAS Financial Decision Making, iimt Universität Freiburg · im Rahmen von AI4REALNET',
      sections: [
        {
          heading: 'Worum es geht',
          body:
            'Co-Learning heisst: Disponentin und KI lernen voneinander. Die KI zeigt Auswirkungen und Alternativen, du entscheidest und begründest, die KI passt sich an. Es geht um eine Erweiterung des TMS, nicht um ein KI-gesteuertes System.',
        },
        {
          heading: 'Was wir von dir brauchen',
          body: 'Deine Schätzungen fliessen in eine Monte-Carlo-Simulation über zehn Jahre.',
          items: [
            'Pro Kosten- und Nutzenposition drei Werte: Maximum, Minimum, wahrscheinlichster Wert, in Personenmonaten oder CHF',
            'Bezug ist ein eingeführtes System (TRL 9), nicht dieser Prototyp',
            'Eine breite Spanne ist eine gültige Antwort',
          ],
        },
        {
          heading: 'Wer entscheidet was',
          items: [
            'TMS: plant den Fahrplan und passt ihn mit seinem Optimierungsalgorithmus an',
            'KI: schlägt für die konkrete Lage Abweichungen vor (gedacht als lernende Agenten, im Prototyp ein klassischer Planer)',
            'Du: entscheidest als Fachperson, und daraus lernt die KI',
          ],
        },
        {
          heading: 'Zum Prototyp',
          body:
            'Flatland ist eine bewusst vereinfachte Bahnsimulation: keine Signale, keine Fahrdynamik. Die neuen Co-Learning-Module haben einen violetten Rand. ' +
            PROTOTYPE_DISCLAIMER,
        },
      ],
      proceedLabel: 'Weiter zur Tour',
    },
    closing: {
      eyebrow: 'Übersicht · Grundlage für die Schätzung',
      title: 'Die Co-Learning-Module im Überblick',
      lead:
        'Sechs Module stützen den gemeinsamen Lernprozess von Disponentin und KI. Sie sind entlang des Lernzyklus nach Kolb angeordnet.',
      kolbIntro:
        'Lernen aus Erfahrung verläuft in vier Phasen. Drei davon kann ein Co-Learning-System unterstützen. Die abstrakte Begriffsbildung bleibt heute beim Menschen.',
      kolb: [
        { name: 'Konkrete Erfahrung', supported: true, note: 'Eine Situation erleben: Auswirkungen und Handlungsoptionen' },
        { name: 'Reflexion', supported: true, note: 'Zurückblicken: Was ist passiert, warum habe ich so entschieden?' },
        { name: 'Abstrakte Begriffsbildung', supported: false, note: 'Eigene Regeln ableiten, technisch nicht unterstützt' },
        { name: 'Aktives Experimentieren', supported: true, note: 'Ausprobieren: Alternativen und Vorfälle in der Sandbox' },
      ],
      loops: [
        {
          name: 'Operativer Loop',
          steps: [
            { actor: 'TMS', action: 'erkennt einen Konflikt oder eine Störung' },
            { actor: 'KI', action: 'bewertet Risiko und Auswirkungen' },
            { actor: 'KI', action: 'schlägt Alternativen vor' },
            { actor: 'Disponent/in', action: 'prüft und entscheidet' },
            { actor: 'TMS', action: 'setzt um, aktualisiert Netz und KPIs' },
          ],
        },
        {
          name: 'Lern-Loop',
          steps: [
            { actor: 'KI', action: 'regt Reflexion an, bündelt ähnliche Situationen' },
            { actor: 'KI / TMS', action: 'fasst Massnahmen und KPI-Wirkung der Schicht zusammen' },
            { actor: 'Disponent/in', action: 'übt bekannte und neue Hochrisiko-Fälle in der Sandbox' },
            { actor: 'KI', action: 'aktualisiert ihr Modell aus dem Feedback' },
          ],
        },
      ],
      loopsNote:
        'In der Praxis wird auch im operativen Loop gelernt. Die Trennung vereinfacht die Kostenschätzung.',
      modules: [
        {
          name: 'Risiko- & Auswirkungsanalyse',
          area: 'Impact Analysis',
          kolbPhase: 'Konkrete Erfahrung',
          does: 'Zeitpuffer berechnen, nötige Massnahmen und betroffene Sektoren zeigen, Wirkung auf betroffene Züge abschätzen',
          inTour: 'Panel «Lage: Risiko & Auswirkung» rechts, sobald die Störung wirkt',
          status: 'partial',
          statusNote: 'Betroffene Züge, Zeitpuffer und Art der Massnahmen live; betroffene Sektoren fehlen',
        },
        {
          name: 'Alternativen',
          area: 'Alternative Actions',
          kolbPhase: 'Konkrete Erfahrung',
          does: 'Von der KI berechnete Handlungsalternativen',
          inTour: 'Panel «Plan / KI / Mensch»: Plan, KI-Neuplanung und deine Wahl im Vergleich, auch direkt am Zug auf der Karte',
          status: 'live',
          statusNote: 'Erlebbar; die KI rechnet mit einem klassischen Planer statt mit gelernten Agenten',
        },
        {
          name: 'Reflexion',
          area: 'Reflection',
          kolbPhase: 'Reflexion',
          does: 'Reflexionsfragen stellen, ähnliche Situationen bündeln, automatisch zusammenfassen, anonymisiert im Team teilen',
          inTour: 'Dialog «Warum diese Entscheidung?» direkt nach dem Entscheid (Schritt 6)',
          status: 'partial',
          statusNote: 'Fragen und Rückspiegelung live, Teilen im Team nicht gebaut',
        },
        {
          name: 'Schichtbilanz',
          area: 'Sandbox',
          kolbPhase: 'Aktives Experimentieren',
          does: 'Alle Massnahmen, betroffenen Züge und KPIs einer Schicht zusammenfassen',
          inTour: 'Nach der Schicht (Schritt 7)',
          status: 'live',
          statusNote: 'Erlebbar; fasst hier eine Episode zusammen, nicht eine ganze Schicht',
        },
        {
          name: 'Event-Simulation',
          area: 'Sandbox',
          kolbPhase: 'Aktives Experimentieren',
          does: 'Erlebte Vorfälle mit anderen Massnahmen durchspielen, nie erlebte Hochrisiko-Fälle üben',
          inTour: 'Nach der Schicht in der Sandbox (Schritt 8)',
          status: 'partial',
          statusNote: 'Varianten mit dem Simulator vorberechnet, noch nicht selbst durchspielbar',
        },
        {
          name: 'System-Co-Learning',
          area: 'Co-Learning AI',
          kolbPhase: 'KI-seitig',
          does: 'Empfehlungsmodell aus dem Feedback anpassen, Input für TMS-Algorithmen liefern',
          inTour: 'Lern-Karten nach der Schicht (Schritt 9)',
          status: 'partial',
          statusNote: 'Präferenzmodell live, Rückfluss ins TMS nur Konzept',
        },
      ],
      statusLabels: {
        live: 'erlebbar',
        partial: 'teilweise',
        concept: 'Konzept',
      },
      estimationReminder:
        'Bitte schätze für ein ausgereiftes, eingeführtes System (TRL 9), nicht für diesen Prototyp: Maximum, Minimum, wahrscheinlichster Wert.',
      disclaimer: PROTOTYPE_DISCLAIMER,
      sources: 'Grundlagen: Hamouche et al. (2026), Mussi et al. (2025), Bessa et al. (2026), AI4REALNET.',
    },
  },
];

export function briefingById(id: string | undefined): TourBriefing | undefined {
  return id ? TOUR_BRIEFINGS.find((b) => b.id === id) : undefined;
}
