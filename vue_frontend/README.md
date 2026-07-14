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

The conversation view renders one Live2D panel per agent when a session is active.

- **Libraries:** `pixi.js` v8 + `untitled-pixi-live2d-engine` (version pinned; see plan doc).
- **Runtime:** Live2D Cubism Core is loaded from `public/live2d/live2dcubismcore.min.js`
  via a script tag in `index.html` — see `public/live2d/README.md` for setup.
- **Models:** Official Live2D sample models (not committed — license); presets and framing
  tuning live in `src/config/avatarPresets.ts`.
- **Lip-sync:** word timings from the backend (`words` / `wtimes` / `wdurations`) drive
  mouth open/close via `mouthSync()`; falls back to audio-amplitude when timings are absent.
