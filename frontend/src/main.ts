import { bootstrapApplication } from '@angular/platform-browser';
import { appConfig } from './app/app.config';
import { AppComponent } from './app/app.component';

// Lyne Web Components - Side-Effect Imports
// Note: secondary/transparent/mini-button only exist as sub-paths in 4.13.x
import '@sbb-esta/lyne-elements/button.js';
import '@sbb-esta/lyne-elements/button/secondary-button.js';
import '@sbb-esta/lyne-elements/button/transparent-button.js';
import '@sbb-esta/lyne-elements/button/mini-button.js';
import '@sbb-esta/lyne-elements/divider.js';
import '@sbb-esta/lyne-elements/tag.js';
import '@sbb-esta/lyne-elements/menu.js';
import '@sbb-esta/lyne-elements/menu/menu-button.js';
import '@sbb-esta/lyne-elements/menu/menu-link.js';
import '@sbb-esta/lyne-elements/loading-indicator.js';
import '@sbb-esta/lyne-elements/loading-indicator-circle.js';

import '@sbb-esta/lyne-elements/checkbox.js';
import '@sbb-esta/lyne-elements/checkbox/checkbox-group.js';
import '@sbb-esta/lyne-elements/radio-button.js';
import '@sbb-esta/lyne-elements/radio-button/radio-button-group.js';

import '@sbb-esta/lyne-elements/form-field.js';
import '@sbb-esta/lyne-elements/expansion-panel.js';

bootstrapApplication(AppComponent, appConfig)
  .catch((err) => console.error(err));
