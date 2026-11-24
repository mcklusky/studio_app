import './qr.css'
import { Download, Printer, TriangleAlert } from 'lucide-react'
import QRCode from 'qrcode'
import { useEffect, useState, type ReactNode } from 'react'
import { Dialog } from './Dialog'

const QR_OPTIONS = { errorCorrectionLevel: 'M' as const, margin: 2, color: { dark: '#050404', light: '#ffffff' } }

/** A QR code for `url`, rendered as an image (works offline: generated in the browser). */
export function QrImage({ url, size = 220, label }: { url: string; size?: number; label: string }) {
  const [src, setSrc] = useState('')
  useEffect(() => {
    let live = true
    QRCode.toDataURL(url, { ...QR_OPTIONS, width: size * 2 })
      .then((data) => live && setSrc(data))
      .catch(() => live && setSrc(''))
    return () => {
      live = false
    }
  }, [url, size])
  return src ? (
    <img className="qr-image" src={src} width={size} height={size} alt={label} />
  ) : (
    <span className="qr-image qr-placeholder" style={{ width: size, height: size }} aria-hidden="true" />
  )
}

async function downloadPng(url: string, fileName: string) {
  const data = await QRCode.toDataURL(url, { ...QR_OPTIONS, width: 1024 })
  const link = document.createElement('a')
  link.href = data
  link.download = fileName
  document.body.appendChild(link)
  link.click()
  link.remove()
}

/** Open a print-ready poster (logo, headline, big QR, link) in a new window. */
async function printPoster(url: string, headline: string, subline: string) {
  const qr = await QRCode.toString(url, { ...QR_OPTIONS, type: 'svg', margin: 1 })
  const win = window.open('', '_blank', 'width=720,height=960')
  if (!win) return
  const logo = `${location.origin}/brand/just-smile-ink.png`
  const esc = (text: string) => text.replace(/[&<>"]/g, (c) => ({ '&': '&amp;', '<': '&lt;', '>': '&gt;', '"': '&quot;' })[c] ?? c)
  win.document.write(`<!doctype html><html><head><meta charset="utf-8"><title>${esc(headline)}</title>
<style>
  @page { size: A4; margin: 18mm; }
  body { font-family: 'DM Sans', Arial, sans-serif; color: #050404; text-align: center; margin: 0; }
  .poster { border: 6px solid #fbbe25; border-radius: 28px; padding: 36px 28px; }
  img { width: 150px; height: 150px; }
  h1 { font-size: 34px; margin: 10px 0 6px; }
  p { font-size: 18px; color: #5f4a3d; margin: 0 0 22px; }
  .qr { width: 340px; height: 340px; margin: 0 auto; }
  .qr svg { width: 100%; height: 100%; }
  .url { margin-top: 18px; font-size: 16px; font-weight: 700; word-break: break-all; }
  .strip { margin-top: 26px; height: 10px; border-radius: 5px; background: linear-gradient(90deg, #a74d20, #fba023, #fbbe25); }
</style></head><body><div class="poster">
  <img src="${logo}" alt="Just Smile Empire">
  <h1>${esc(headline)}</h1><p>${esc(subline)}</p>
  <div class="qr">${qr}</div>
  <div class="url">${esc(url)}</div><div class="strip"></div>
</div></body></html>`)
  win.document.close()
  // Print from here: the site's security policy blocks inline scripts in the poster window.
  win.focus()
  window.setTimeout(() => win.print(), 500)
}

/** QR dialog with Download (PNG for flyers/WhatsApp) and Print (A4 poster). */
export function QrDialog({
  title,
  url,
  fileName,
  posterHeadline,
  posterSubline,
  children,
  onClose,
}: {
  title: string
  url: string
  fileName: string
  posterHeadline: string
  posterSubline: string
  children?: ReactNode
  onClose: () => void
}) {
  const local = ['localhost', '127.0.0.1'].includes(location.hostname)
  return (
    <Dialog title={title} onClose={onClose}>
      <div className="qr-card">
        <QrImage url={url} label={`QR code for ${url}`} />
        <a className="qr-url" href={url} target="_blank" rel="noreferrer">
          {url}
        </a>
      </div>
      {local && (
        <p className="qr-warning" role="note">
          <TriangleAlert size={16} aria-hidden="true" /> This is a test address on this computer, so phones cannot open it yet. Once the app
          is on its real web address, open this again and the QR code will point there.
        </p>
      )}
      {children}
      <div className="dialog-actions">
        <button type="button" className="button button-secondary" onClick={() => void printPoster(url, posterHeadline, posterSubline)}>
          <Printer size={16} aria-hidden="true" /> Print poster
        </button>
        <button type="button" className="button button-primary" onClick={() => void downloadPng(url, fileName)}>
          <Download size={16} aria-hidden="true" /> Download QR
        </button>
      </div>
    </Dialog>
  )
}
