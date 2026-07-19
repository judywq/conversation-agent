import { readdir, mkdir, stat } from 'node:fs/promises'
import path from 'node:path'
import { fileURLToPath } from 'node:url'
import sharp from 'sharp'

const __dirname = path.dirname(fileURLToPath(import.meta.url))
const root = path.resolve(__dirname, '..')
const srcDir = path.join(root, 'scenes-src')
const outDir = path.join(root, 'public', 'scenes')

const DISPLAY_WIDTH = 1600
const DISPLAY_QUALITY = 80
const THUMB_WIDTH = 480
const THUMB_QUALITY = 75

function formatBytes(n) {
  if (n < 1024) return `${n} B`
  if (n < 1024 * 1024) return `${(n / 1024).toFixed(1)} KB`
  return `${(n / (1024 * 1024)).toFixed(2)} MB`
}

async function isNewer(outputPath, sourceMtimeMs) {
  try {
    const out = await stat(outputPath)
    return out.mtimeMs >= sourceMtimeMs
  } catch {
    return false
  }
}

async function main() {
  await mkdir(outDir, { recursive: true })
  const files = (await readdir(srcDir)).filter((f) => f.toLowerCase().endsWith('.png')).sort()

  if (files.length === 0) {
    console.error(`No PNG masters found in ${srcDir}`)
    process.exit(1)
  }

  let totalIn = 0
  let totalOut = 0

  for (const file of files) {
    const name = path.basename(file, path.extname(file))
    const srcPath = path.join(srcDir, file)
    const displayPath = path.join(outDir, `${name}.webp`)
    const thumbPath = path.join(outDir, `${name}.thumb.webp`)
    const srcStat = await stat(srcPath)
    totalIn += srcStat.size

    const skipDisplay = await isNewer(displayPath, srcStat.mtimeMs)
    const skipThumb = await isNewer(thumbPath, srcStat.mtimeMs)

    if (!skipDisplay) {
      await sharp(srcPath)
        .resize({ width: DISPLAY_WIDTH, withoutEnlargement: true })
        .webp({ quality: DISPLAY_QUALITY })
        .toFile(displayPath)
    }

    if (!skipThumb) {
      await sharp(srcPath)
        .resize({ width: THUMB_WIDTH, withoutEnlargement: true })
        .webp({ quality: THUMB_QUALITY })
        .toFile(thumbPath)
    }

    const displaySize = (await stat(displayPath)).size
    const thumbSize = (await stat(thumbPath)).size
    totalOut += displaySize + thumbSize

    const status = skipDisplay && skipThumb ? 'skip' : 'wrote'
    console.log(
      `${status.padEnd(5)} ${name}: ${formatBytes(srcStat.size)} → display ${formatBytes(displaySize)}, thumb ${formatBytes(thumbSize)}`,
    )
  }

  console.log(
    `\nDone: ${files.length} scenes, ${formatBytes(totalIn)} masters → ${formatBytes(totalOut)} webp outputs`,
  )
}

main().catch((err) => {
  console.error(err)
  process.exit(1)
})
