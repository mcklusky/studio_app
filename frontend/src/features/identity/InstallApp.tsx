import { CheckCircle2, Download, Smartphone } from 'lucide-react'
import { QrDialog } from '../../components/QrCode'
import { isIos, useInstallPrompt } from '../../lib/install'

/** Staff: scan the QR on a phone to open the app, then add it to the home screen. */
export function InstallAppDialog({ onClose }: { onClose: () => void }) {
  const { canInstall, installed, install } = useInstallPrompt()
  const url = `${location.origin}/`
  return (
    <QrDialog
      title="Get the app on your phone"
      url={url}
      fileName="just-smile-app-qr.png"
      posterHeadline="Just Smile staff app"
      posterSubline="Scan with your phone camera, sign in, then add it to your home screen."
      onClose={onClose}
    >
      {installed ? (
        <p className="install-now field-hint">
          <CheckCircle2 size={16} aria-hidden="true" /> You are using the installed app.
        </p>
      ) : (
        canInstall && (
          <button type="button" className="button button-primary install-now" onClick={() => void install()}>
            <Download size={16} aria-hidden="true" /> Install on this device
          </button>
        )
      )}
      <div className="install-steps">
        <section>
          <h3>
            <Smartphone size={16} aria-hidden="true" /> 1. Scan the code
          </h3>
          <ol>
            <li>Open the camera on the phone and point it at the code.</li>
            <li>Tap the link that appears and sign in with your own account.</li>
          </ol>
        </section>
        <section>
          <h3>2. Add it to the home screen</h3>
          <ol>
            {isIos() ? (
              <>
                <li>In Safari, tap the Share button (square with an arrow).</li>
                <li>Choose “Add to Home Screen”, then “Add”.</li>
              </>
            ) : (
              <>
                <li>Android (Chrome): tap “Install app” when it appears, or the ⋮ menu → “Install app” / “Add to Home screen”.</li>
                <li>iPhone (Safari): tap Share → “Add to Home Screen”.</li>
              </>
            )}
          </ol>
        </section>
      </div>
      <p className="field-hint">
        The app opens full-screen like any other app. It always shows live figures, so it needs an internet connection.
      </p>
    </QrDialog>
  )
}
