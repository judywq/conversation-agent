import { mkdir, readdir, stat } from 'node:fs/promises'
import path from 'node:path'
import { fileURLToPath } from 'node:url'
import sharp from 'sharp'

const __dirname = path.dirname(fileURLToPath(import.meta.url))
const root = path.resolve(__dirname, '..')
const srcDir = path.join(root, 'image-src', 'partner-card-bgs-src')
const outDir = path.join(root, 'public', 'partner-card-bgs')

const CARD_BG_HEIGHT = 360
const CARD_BG_QUALITY = 80

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
  await mkdir(srcDir, { recursive: true })

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
    const outPath = path.join(outDir, `${name}.webp`)
    const srcStat = await stat(srcPath)
    totalIn += srcStat.size

    const skip = await isNewer(outPath, srcStat.mtimeMs)
    if (!skip) {
      await sharp(srcPath)
        .resize({ height: CARD_BG_HEIGHT, withoutEnlargement: true })
        .webp({ quality: CARD_BG_QUALITY })
        .toFile(outPath)
    }

    const outSize = (await stat(outPath)).size
    totalOut += outSize
    console.log(
      `${(skip ? 'skip' : 'wrote').padEnd(5)} ${name}: ${formatBytes(srcStat.size)} → ${formatBytes(outSize)}`,
    )
  }

  console.log(
    `\nDone: ${files.length} card backgrounds, ${formatBytes(totalIn)} masters → ${formatBytes(totalOut)} webp outputs`,
  )
}

main().catch((err) => {
  console.error(err)
  process.exit(1)
})
