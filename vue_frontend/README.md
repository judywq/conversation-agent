# vue_frontend

This template should help get you started developing with Vue 3 in Vite.

## Recommended IDE Setup

[VSCode](https://code.visualstudio.com/) + [Volar](https://marketplace.visualstudio.com/items?itemName=Vue.volar) (and disable Vetur).

## Type Support for `.vue` Imports in TS

TypeScript cannot handle type information for `.vue` imports by default, so we replace the `tsc` CLI with `vue-tsc` for type checking. In editors, we need [Volar](https://marketplace.visualstudio.com/items?itemName=Vue.volar) to make the TypeScript language service aware of `.vue` types.

## Customize configuration

See [Vite Configuration Reference](https://vite.dev/config/).

## Project Setup

```sh
npm install
```

### Compile and Hot-Reload for Development

```sh
npm run dev
```

### Type-Check, Compile and Minify for Production

```sh
npm run build
```

### Run Unit Tests with [Vitest](https://vitest.dev/)

```sh
npm run test:unit
```

### Run End-to-End Tests with [Cypress](https://www.cypress.io/)

```sh
npm run test:e2e:dev
```

This runs the end-to-end tests against the Vite development server.
It is much faster than the production build.

But it's still recommended to test the production build with `test:e2e` before deploying (e.g. in CI environments):

```sh
npm run build
npm run test:e2e
```

### Lint with [ESLint](https://eslint.org/)

```sh
npm run lint
```

## 3D agent avatars

The conversation view renders one TalkingHead panel per agent when a session is active.

- **Libraries:** `@met4citizen/talkinghead` and `three` (see `vite.config.ts` `optimizeDeps.exclude`).
- **Browser:** Chrome or Edge with WebGL enabled works best.
- **Warmup:** Click anywhere in the conversation page once to initialize avatar WebGL contexts (browser autoplay policy).
- **Audio:** Agent speech uses server TTS (`audio_url`) plus word-level `lipsync` metadata from the WebSocket `turn` event. Web Audio fetches media directly from Django (`http://localhost:8000/media/...` in dev); Django CORS must allow `/media/` (see `CORS_URLS_REGEX` in backend settings).
- **Models:** Default avatars load from the [TalkingHead sample GLBs](https://github.com/met4citizen/TalkingHead/tree/main/avatars); see `src/config/avatarPresets.ts`.
- **Toggle:** Use **Avatars On/Off** during a session to fall back to plain audio playback.
