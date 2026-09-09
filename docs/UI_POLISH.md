# UI refinement, September 8 UTC

Preserve-mode polish of the existing React/Vite studio, not a product redesign.
The requested `design-taste-frontend` skill was inspected and installed. Its
marketing rules explicitly exclude dense product UI; its preserve-first audit
informed the welcome surface, while the actual studio retains its established
navigation, three camera roles, timing labels and real source disclosures.

## Design decisions

- Follow-up browser feedback: remove the production-header slogans and make the
  theme toggle icon-only (retain its accessible label and tooltip). Remove
  nonessential panel borders, filled title bars and header/rail dividers; group
  sections with whitespace. Keep media frames, input boundaries and selected
  camera feedback. The transport stays in document flow instead of covering
  the monitor or screenplay. Clappy's wordmark is unchanged.

- Per the updated user direction, default to white/sky blue and offer a
  persistent charcoal/grey theme toggle. Preserve the Clappy wordmark,
  DM Sans/Manrope and studio/review flow. Media stays on a dark viewing surface;
  footage colors are unchanged. No new animation dependency.
- Self-host the existing fonts via locked Fontsource packages. The welcome image
  reuses the existing 64 KB camera-C thumbnail, not a newly generated visual.
- Raise small label sizes and contrast, standardize panel/control radii and
  spacing, and give keyboard focus an explicit high-contrast treatment.
- Keep screenplay access on mobile. Stack phone cards with readable controls;
  make saved takes a horizontal strip and bring the selected take into view.
- Preserve error/loading states and microphone disclosure. Before admission,
  label the invitation requirement instead of implying an endless connection or
  reporting services as offline before their status is available.

## Verification

- TypeScript/Vite production build passes; 40 Python tests pass.
- Chrome studio/review have no document overflow at 320, 390 and 1440 px.
  Mobile screenplay remains visible; selected Take 10 is visible in its strip.
- A/B review preserved a paused five-second playhead. Resumed alternate playback
  reached 6.131 seconds with real saved media; no model result or API was mocked.
- WebKit 390×844 studio/review: no horizontal overflow; actual MP4 decoded at
  960 px and playback advanced to 1.194 seconds.
- Desktop/mobile invitation image loads, wrong-code error remains visible, and
  no Google Fonts stylesheet/font host is requested by the candidate page.
- React review: scroll position is kept in DOM refs, the effect depends only on
  take ID, no new global listeners or continuous React-state animation is added.
- Reduced-motion rules disable new movement. This is not a complete WCAG or
  physical-device certification.
- Updated palette: production build passes; local browser toggle survives a
  reload, with no Vite error overlay. Desktop and mobile screenshots are saved
  as `output/playwright/theme-*.png`.
- Airy follow-up: production build passes; desktop light/dark screenshots and
  a 390px dark mobile screenshot are saved as `output/playwright/airy-*.png`.
  Mobile has no document overflow; the toggle has no visible text and retains
  its accessible name. No runtime/API behavior was changed.

Screenshots are under `output/playwright/polish-*.png`. Candidate frontend assets
were served in an isolated test browser against the unchanged hosted API before
deployment. The new two-theme version is local-only, not deployed. No new AI
generation or credit inspection was needed for this pass.
