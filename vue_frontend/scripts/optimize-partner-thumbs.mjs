import { access, mkdir, readdir, stat } from 'node:fs/promises'
import path from 'node:path'
import { fileURLToPath } from 'node:url'
import sharp from 'sharp'

const __dirname = path.dirname(fileURLToPath(import.meta.url))
const root = path.resolve(__dirname, '..')
const srcDir = path.join(root, 'image-src', 'partner-thumbs-src')
const outDir = path.join(root, 'public', 'partner-thumbs')

const THUMB_HEIGHT = 400
const THUMB_QUALITY = 80
const PLACEHOLDER_NAME = '_placeholder_girl1.webp'

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

async function exists(filePath) {
  try {
    await access(filePath)
    return true
  } catch {
    return false
  }
}

/** Simple muted stand-in until a real master PNG is provided. */
async function writePlaceholder(outPath) {
  const size = 400
  const svg = `
<svg width="${size}" height="${size}" xmlns="http://www.w3.org/2000/svg">
  <rect width="100%" height="100%" fill="#e8e6e3"/>
  <circle cx="200" cy="145" r="52" fill="#c4c0ba"/>
  <ellipse cx="200" cy="310" rx="90" ry="100" fill="#c4c0ba"/>
  <text x="200" y="380" text-anchor="middle" font-family="system-ui,sans-serif" font-size="28" fill="#8a8580">?</text>
</svg>`
  await sharp(Buffer.from(svg)).webp({ quality: THUMB_QUALITY }).toFile(outPath)
}

async function main() {
  await mkdir(outDir, { recursive: true })
  await mkdir(srcDir, { recursive: true })

  const placeholderPath = path.join(outDir, PLACEHOLDER_NAME)
  if (!(await exists(placeholderPath))) {
    await writePlaceholder(placeholderPath)
    console.log(`wrote ${PLACEHOLDER_NAME}: ${formatBytes((await stat(placeholderPath)).size)}`)
  } else {
    console.log(`skip  ${PLACEHOLDER_NAME}`)
  }

  const files = (await readdir(srcDir)).filter((f) => f.toLowerCase().endsWith('.png')).sort()

  if (files.length === 0) {
    console.warn(`No PNG masters found in ${srcDir}`)
    return
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
        .resize({ height: THUMB_HEIGHT, withoutEnlargement: true })
        .webp({ quality: THUMB_QUALITY })
        .toFile(outPath)
    }

    const outSize = (await stat(outPath)).size
    totalOut += outSize
    console.log(
      `${(skip ? 'skip' : 'wrote').padEnd(5)} ${name}: ${formatBytes(srcStat.size)} → ${formatBytes(outSize)}`,
    )
  }

  console.log(
    `\nDone: ${files.length} thumbs, ${formatBytes(totalIn)} masters → ${formatBytes(totalOut)} webp outputs`,
  )
}

main().catch((err) => {
  console.error(err)
  process.exit(1)
})
