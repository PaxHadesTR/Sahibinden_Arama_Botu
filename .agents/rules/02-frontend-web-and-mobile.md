---
description: Mobile (Flutter/iOS/Android) and Web (TypeScript/React/Next/Vue/HTML) UI/UX and lifecycle rules
trigger: glob
globs: ["**/*.dart", "**/*.ts", "**/*.tsx", "**/*.js", "**/*.jsx", "**/*.vue", "**/*.svelte", "**/*.swift", "**/*.kt", "**/*.html", "**/*.css"]
---
- **High-Craft UI/UX & Visual States:** Never ship raw or unstyled placeholder screens. Every screen or component must handle all 4 visual states gracefully:
  1. **Loading State:** Skeleton loaders, shimmer effects, or contextual progress indicators (prevent layout shift).
  2. **Empty State:** Clean iconography, helpful copy, and a clear primary call-to-action.
  3. **Error State:** User-friendly diagnostic message with an immediate `[Tekrar Dene / Retry]` action (never dump raw stack traces to the UI).
  4. **Active State:** High-contrast typography and surfaces (deep blacks / crisp borders), smooth micro-interactions, and responsive touch targets.
- **Lifecycle & Memory Leak Defense (V1/V2):** Always cancel active timers, debouncers, stream subscriptions, WebSocket listeners, and camera/media controllers inside component unmount / `dispose()` hooks. Prevent unnecessary UI tree rebuilds during transient loading states.
- **Offline & Network Resilience (V5):** Handle intermittent connectivity, request timeouts, and API errors gracefully. Ensure offline queues and retry mechanisms use idempotency keys or deduplication to prevent duplicate record creation upon reconnection.
- **Client-Side Data Confidentiality & XSS Defense (V4):** Never expose internal business margins, wholesale costs, admin secrets, or other tenants' metadata in client payloads, public URLs, console logs, or exported documents. Sanitize dynamic HTML/URLs against XSS and Open Redirects.
- **Contract Parity & Zero Linter Warnings (V7):** Keep client models and serialization logic strictly aligned with backend API schemas, and ensure all edits pass static type-checking and linters with zero warnings.
