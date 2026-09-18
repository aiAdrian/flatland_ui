import { TestBed } from '@angular/core/testing';
import { provideTranslocoTesting } from './testing/transloco-testing';
import { provideHttpClient } from '@angular/common/http';
import { AppComponent } from './app.component';

describe('AppComponent', () => {
  beforeEach(async () => {
    await TestBed.configureTestingModule({
      imports: [AppComponent],
      providers: [
        ...provideTranslocoTesting(), provideHttpClient()],
    }).compileComponents();
  });

  it('should create the dispatcher app', () => {
    const fixture = TestBed.createComponent(AppComponent);
    expect(fixture.componentInstance).toBeTruthy();
  });

  it('should render the Flatland Dispatcher shell', () => {
    const fixture = TestBed.createComponent(AppComponent);
    fixture.detectChanges();
    const compiled = fixture.nativeElement as HTMLElement;
    expect(compiled.textContent).toContain('Flatland Dispatcher');
  });
});
