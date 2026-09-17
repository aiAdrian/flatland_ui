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
    // Steps 1-9 of the thesis' interaction flow (Table 2): operational loop 1-5,
    // learning loop 6-9, with shift summary and event simulation after the episode.
    guide: [
      {
        id: 'detect',
        loop: 'operational',
        title: 'Konflikt erkennen',
        hint: 'Starten Sie mit «Play» und beobachten Sie die Strecke. Nach einer knappen halben Minute bleibt ein Zug im Einspurabschnitt stehen, und das TMS meldet die Störung links.',
      },
      {
        id: 'assess',
        loop: 'operational',
        module: true,
        panelType: 'impact',
        title: 'Risiko & Auswirkung',
        hint: 'Neu: «Impact» zeigt die Lage — welcher Zug betroffen ist, wie lange er stehen würde und wie viele Massnahmen nötig sind. Entschieden wird hier nicht; der betroffene Zug wartet.',
      },
      {
        id: 'alternatives',
        loop: 'operational',
        module: true,
        panelType: 'proposal-compare',
        title: 'Alternativen',
        hint: 'Neu: Die KI bietet Optionen an, ohne eine zu empfehlen. Unter «Plan / KI / Mensch» sehen Sie vorab, was der Plan, der KI-Vorschlag und Ihre eigene Wahl für den Zug bedeuten.',
      },
      {
        id: 'decide',
        loop: 'operational',
        panelType: 'proposal-compare',
        title: 'Entscheiden',
        hint: 'Wählen Sie unter «Plan / KI / Mensch» eine Option für den betroffenen Zug und übernehmen Sie sie.',
      },
      {
        id: 'execute',
        loop: 'operational',
        title: 'Umsetzen',
        hint: 'Das TMS setzt Ihre Wahl um. Lassen Sie die Simulation weiterlaufen.',
      },
      {
        id: 'reflect',
        loop: 'learning',
        module: true,
        title: 'Reflexion',
        hint: 'Neu: Nach Ihrer Entscheidung hält die Simulation an und fragt nach Ihrem Grund. Wählen Sie einen Grund, danach «Ja, als Regel» oder «Nur diesmal».',
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
        hint: 'Neu: Die KI übernimmt bestätigte Gründe in ihr Modell. Nach der Schicht sehen Sie das als Lern-Karte.',
      },
    ],
    moduleBadges: {
      impact: 'Risiko- und Auswirkungsanalyse',
      'proposal-compare': 'Auswirkungsanalyse: Plan, KI-Vorschlag und Ihre Wahl',
    },
    modeIntros: {
      'co-learning': {
        mode: 'co-learning',
        wp: 'Co-Learning · Walensee',
        title: 'Eine Störung am Einspurabschnitt',
        tagline: 'Die KI zeigt Auswirkungen und Optionen. Sie entscheiden und lernen daraus.',
        whatHappens:
          'Strecke Pfäffikon SZ–Chur am Walensee, von Ziegelbrücke bis Walenstadt, mit einem einspurigen Abschnitt. Drei Züge fahren nach Fahrplan. Nach einer knappen halben Minute bleibt ein Zug mitten im Einspurabschnitt stehen, und der Zug dahinter läuft auf ihn auf. Wie es weitergeht, entscheiden Sie.',
        focusView:
          'In der Mitte Streckenspiegel und Zeit-Weg-Linien (ZWL) als Tabs, darunter der Fahrplan. Den Streckenspiegel ziehen Sie mit der Maus seitlich, mit dem Mausrad zoomen Sie. Rechts liegen die Co-Learning-Module.',
        yourRole:
          'Sie disponieren. Die KI rankt nichts und empfiehlt nichts: Sie wählen selbst, vergleichen danach mit einer Alternative und denken über Ihre Entscheidung nach.',
        whatYouCanControl: [
          'Die Simulation starten, pausieren oder schrittweise laufen lassen',
          'Für einen betroffenen Zug eine Option wählen',
          'Unter «Plan / KI / Mensch» vorab vergleichen: Plan, KI-Vorschlag und Ihre eigene Wahl',
          'Nach einer Entscheidung den Grund angeben, als Regel oder nur für diesmal',
        ],
        watchFor: [
          'Panels mit dem Zeichen «Co-Learning» sind die neue Erweiterung. Alles andere steht für das TMS als Ganzes.',
          'Optionen erscheinen ohne Ranking und ohne «empfohlen»',
          'Blau steht für Ihre Entscheidung, gelb für die Variante der KI',
          'Oben führt ein Leitfaden durch die neun Schritte. Das jeweils nächste Modul wird hervorgehoben.',
        ],
        goal:
          'Es geht nicht um die perfekte Disposition, sondern um ein Gefühl dafür, was die Module leisten, als Grundlage für Ihre Schätzung.',
        note: PROTOTYPE_DISCLAIMER,
        labels: {
          stepPrefix: 'Modus',
          stepOf: 'von',
          whatHappens: 'Was passiert',
          focusView: 'Wohin Sie schauen',
          yourRole: 'Ihre Rolle',
          control: 'Was Sie tun können',
          watchFor: 'Worauf Sie achten',
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
        'Diese Tour zeigt in rund einer Viertelstunde, wie eine Co-Learning-Erweiterung für ein künftiges Traffic-Management-System funktionieren könnte. Sie ist die gemeinsame Grundlage für das anschliessende Interview.',
      byline: 'Daniel Boos · CAS Financial Decision Making, iimt Universität Freiburg · im Rahmen von AI4REALNET',
      sections: [
        {
          heading: 'Thema',
          body:
            'Das EU-Forschungsprojekt AI4REALNET untersucht KI-Unterstützung für Bahnnetze. Co-Learning heisst: Disponentin und KI lernen voneinander. Die KI bewertet eine Störung und zeigt Alternativen, der Mensch entscheidet und reflektiert, und die KI passt sich an. Betrachtet wird eine Erweiterung des TMS, kein vollständig KI-gesteuertes System.',
        },
        {
          heading: 'Ziel der Befragung',
          body:
            'Wir schätzen Kosten und Nutzen einer solchen Erweiterung ab. Einsatzdaten gibt es noch nicht (Reifegrad TRL 3–4). Deshalb fragen wir Fachpersonen nach Bandbreiten statt nach Einzelwerten. Die Werte fliessen in eine Monte-Carlo-Simulation, die zeigt, wie wahrscheinlich sich die Erweiterung über zehn Jahre lohnt.',
        },
        {
          heading: 'Was wir von Ihnen brauchen',
          items: [
            'Pro Kosten- oder Nutzenposition drei Werte: Minimum, wahrscheinlichster Wert, Maximum',
            'Bezug ist ein ausgereiftes, eingeführtes System (TRL 9), nicht der Prototyp, den Sie gleich sehen',
            'Angaben in Personenmonaten oder CHF, je nachdem, was Ihnen leichter fällt',
            'Eine breite Spanne ist eine gültige Antwort, wenn die Unsicherheit gross ist',
          ],
        },
        {
          heading: 'Ablauf',
          ordered: true,
          items: [
            'Einführung: diese Seite',
            'Betrieb (Schritte 1–5): eine Störung erleben, Auswirkungen und neutrale Optionen sehen, selbst entscheiden',
            'Lernen (Schritte 6–9): reflektieren, nach der Episode Schichtbilanz und Event-Simulation, die KI lernt mit',
            'Übersicht aller Module mit Lerntheorie als Grundlage für die Schätzfragen',
          ],
        },
        {
          heading: 'Die Simulation',
          body:
            'Sie sehen die Bahnsimulation Flatland: ein Gitter mit Zügen, Weichen und Haltepunkten, bewusst vereinfacht. Keine Signale, keine Fahrdynamik, ein Zeitschritt statt Sekunden und Minuten. Das genügt, um Konflikte, Auswirkungen und Entscheidungen erlebbar zu machen — Fahrzeiten oder Kapazitäten lassen sich damit nicht rechnen.',
        },
        {
          heading: 'Wer entscheidet was',
          items: [
            'TMS: plant den Fahrplan und passt ihn bei Störungen mit seinem eigenen Optimierungsalgorithmus an. Der Fahrplan ist dabei nur das Gerüst aus Ankunfts- und Haltezeiten, die Route bleibt beweglich.',
            'Co-Learning-KI: schaut auf die konkrete Situation und schlägt lokale Abweichungen vor — etwa, wer zuerst durch den Einspurabschnitt fährt. Gedacht ist dafür ein MARL-Ansatz, also mehrere lernende Agenten über dem Hauptalgorithmus. Im Prototyp rechnet an dieser Stelle noch ein klassischer Planungsalgorithmus, kein gelernter Agent.',
            'Mensch: Sie entscheiden als Fachperson. Ihre Entscheidung und Ihre Begründung fliessen zurück — daraus lernt die KI, und langfristig verbessert das den Hauptalgorithmus.',
          ],
        },
        {
          heading: 'Zum Prototyp',
          body:
            'Der Playground ist ein Forschungsprototyp auf der Bahnsimulation Flatland, kein Produkt. Die neuen Co-Learning-Module tragen ein violettes Zeichen «Co-Learning», alles andere steht für das TMS als Ganzes. ' +
            PROTOTYPE_DISCLAIMER +
            ' Die Übersicht am Ende zeigt, was Sie erlebt haben und was nur skizziert ist.',
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
          inTour: 'Panel «Impact» rechts, sobald die Störung wirkt',
          status: 'partial',
          statusNote: 'Betroffene Züge live, Zeitpuffer und Sektoren vereinfacht',
        },
        {
          name: 'Alternativen',
          area: 'Alternative Actions',
          kolbPhase: 'Konkrete Erfahrung',
          does: 'Von der KI berechnete Handlungsalternativen',
          inTour: 'Optionen im Panel «Impact», ohne Ranking',
          status: 'live',
          statusNote: 'Im Prototyp erlebbar',
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
        'Bitte schätzen Sie für ein ausgereiftes, eingeführtes System (TRL 9), nicht für diesen Prototyp: Minimum, wahrscheinlichster Wert, Maximum.',
      disclaimer: PROTOTYPE_DISCLAIMER,
      sources: 'Grundlagen: Hamouche et al. (2026), Mussi et al. (2025), Bessa et al. (2026), AI4REALNET.',
    },
  },
];

export function briefingById(id: string | undefined): TourBriefing | undefined {
  return id ? TOUR_BRIEFINGS.find((b) => b.id === id) : undefined;
}
