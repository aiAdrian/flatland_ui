import { Component, CUSTOM_ELEMENTS_SCHEMA } from '@angular/core';
import { ConfigShellComponent } from '../config-shell/config-shell.component';

/** One external or internal reference for a contribution area. `href` starting
 *  with "/" is an in-app route (works from this deployment only); anything
 *  else is an absolute GitHub URL, so it resolves the same whether this page
 *  runs from a laptop, a Hugging Face Space, or any other deployment that
 *  doesn't ship docs/ or backend/ in its static build. */
export interface ContributeLink {
  label: string;
  href: string;
}

export interface ContributeArea {
  id: string;
  title: string;
  /** One line: what contributing here means, in the app's own vocabulary. */
  summary: string;
  /** Whether this needs a cloned repo + dev environment, or works from the
   *  browser alone. Stated explicitly per the area, not assumed uniformly —
   *  Infrastructure and Layouts don't need it, Widgets/Algorithms/Surveys do. */
  setup: 'in-browser' | 'dev-environment';
  links: ContributeLink[];
}

const GH = 'https://github.com/aiAdrian/flatland_ui/blob/main';

/** The six ways to move this playground forward, each pointing at its real
 *  starting point rather than restating it — this page indexes, the linked
 *  docs stay the single source of truth. Add entries here, not new prose, as
 *  more docs land (docs/README.md is the full index; this is a curated front
 *  door onto it, grouped by what a contributor is trying to do). */
const AREAS: ContributeArea[] = [
  {
    id: 'widgets',
    title: 'Widgets',
    summary:
      'The HMI panels a dispatcher, a co-learner, or the Director see and act ' +
      'through — the timetable, the map, recommendations, the decision log, ' +
      'and 30+ others.',
    setup: 'dev-environment',
    links: [
      { label: 'Browse what exists — Widget Gallery', href: '/widgets' },
      { label: 'Authoring process (spec template, seams, the /create-widget skill)', href: `${GH}/docs/reference/widget-authoring-process.md` },
      { label: 'Candidate backlog', href: `${GH}/docs/plans/widget-catalog.md` },
    ],
  },
  {
    id: 'scenarios',
    title: 'Scenarios',
    summary:
      'What environment a session ran in — network, operational program, ' +
      'disruption and variant, kept as four separable layers rather than one ' +
      'dropdown that silently bundles them.',
    setup: 'in-browser',
    links: [
      { label: 'Build a scene — Infrastructure Builder', href: '/infrastructure-builder' },
      { label: 'The four layers and how they fit together', href: `${GH}/docs/plans/scenario-infrastructure-gallery.md` },
      { label: 'Study-design variant axes', href: `${GH}/docs/plans/scenario-variants.md` },
    ],
  },
  {
    id: 'infrastructure',
    title: 'Infrastructure',
    summary:
      'The track network itself — grid, tracks, stations, agents’ start ' +
      'and target positions — drawn and exported as a scene.',
    setup: 'in-browser',
    links: [
      { label: 'Draw one — Infrastructure Builder', href: '/infrastructure-builder' },
      { label: 'Data model and validation rules', href: `${GH}/docs/infrastructure_builder/requirements.md` },
    ],
  },
  {
    id: 'layouts',
    title: 'Layouts',
    summary:
      'Which panels appear where, and how the screen is arranged per ' +
      'interaction mode.',
    setup: 'in-browser',
    links: [
      { label: 'Arrange one — Layout Designer', href: '/designer' },
      { label: 'What a layout can say (grid vocabulary)', href: `${GH}/docs/plans/layout-grid-model-plan.md` },
      { label: 'Which layout renders per mode', href: `${GH}/docs/plans/mode-scoped-layouts-plan.md` },
    ],
  },
  {
    id: 'algorithms',
    title: 'Algorithms',
    summary:
      'The decision policy a train’s actions come from — anything from a ' +
      'one-line heuristic to the Director’s search planner.',
    setup: 'dev-environment',
    links: [
      { label: 'Starter template — copy, rename, implement act_for_handle', href: `${GH}/backend/app/policies/templates/template_policy.py` },
      { label: 'Register it here', href: `${GH}/backend/app/policies/registry.py` },
      { label: 'See it appear — Algorithm Gallery (reads the live registry)', href: '/algorithms' },
    ],
  },
  {
    id: 'surveys',
    title: 'Surveys',
    summary:
      'The post-session questionnaire — statistical scales plus open ' +
      'questions, one instrument per study.',
    setup: 'dev-environment',
    links: [
      { label: 'Source of truth for questions and scales', href: `${GH}/frontend/src/app/core/survey/survey-configs.ts` },
      { label: 'Check the validated instrument library first (AI4REALNET/hmisurveys, TU Delft)', href: `${GH}/CLAUDE.md` },
    ],
  },
];

/**
 * "Contribute" — the in-app front door onto everything that moves this
 * playground forward. Deliberately thin: one line of orientation per area,
 * then links to the real docs/tools, so this page and the repo docs never
 * have to be kept in sync by hand — this only ever points, never restates.
 *
 * Widgets, Algorithms and Surveys need a cloned repo and a dev environment
 * (they're code); Scenarios, Infrastructure and Layouts can be started
 * straight from the areas already in this app's menu.
 */
@Component({
  selector: 'app-contribute',
  standalone: true,
  imports: [ConfigShellComponent],
  templateUrl: './contribute.component.html',
  styleUrl: './contribute.component.scss',
  schemas: [CUSTOM_ELEMENTS_SCHEMA],
})
export class ContributeComponent {
  readonly areas = AREAS;
}
