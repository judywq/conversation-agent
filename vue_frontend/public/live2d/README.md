# Live2D assets (not committed)

These files are covered by the Live2D Proprietary License (Cubism Core) and the
Live2D Free Material License (sample models) and must not be redistributed via
this repository. To set up locally:

1. `live2dcubismcore.min.js` — download directly from
   `https://cubism.live2d.com/sdk-web/cubismcore/live2dcubismcore.min.js`
   (or via the Cubism SDK for Web at https://www.live2d.com/sdk/download/web/,
    `Core/live2dcubismcore.min.js`) and copy it here.
2. Sample models — place each model's **runtime** files under
   `public/live2d/<name>/` so the manifest lives at
   `public/live2d/<name>/<Name>.model3.json` with its `.moc3`, textures,
   `.physics3.json`, `.pose3.json` (if any), `.cdi3.json`, and
   `motion(s)/`/`expressions/` alongside it (paths inside the manifest are
   relative, so keep the folder layout intact).

   From [CubismWebSamples](https://github.com/Live2D/CubismWebSamples)
   (`Samples/Resources/<Name>/`, e.g. via `git clone --filter=blob:none --sparse`
   + `git sparse-checkout set`):
   - hiyori, haru, mao (female), natori (male)

   From the [Live2D sample data CDN](https://cubism.live2d.com/sample-data/js/download.js)
   (ZIP under `https://cubism.live2d.com/sample-data/bin/<id>/<id>_ja.zip`,
   then copy the ZIP's `runtime/` folder contents — for Epsilon use
   `epsilon_free/runtime/`):
   - epsilon → `Epsilon_free.model3.json` (female)
   - hibiki → `hibiki.model3.json` (female)
   - chitose → `chitose.model3.json` (male)

   Sample pages: [Chitose](https://www.live2d.com/en/learn/sample/chitose/),
   [Haru](https://www.live2d.com/en/learn/sample/haru/),
   [Epsilon](https://www.live2d.com/en/learn/sample/epsilon/),
   [Hibiki](https://www.live2d.com/en/learn/sample/hibiki/).
3. Model URLs are wired in `src/config/avatarPresets.ts` — update filenames there if
   the source ships different manifest names.

Sample models © Live2D Inc., used under the Live2D Free Material License
(https://www.live2d.com/eula/live2d-free-material-license-agreement_en.html).
