import { useEffect, useState } from 'react'

/** Chrome/Edge/Android "Add to home screen" event (not in the TypeScript DOM types yet). */
interface InstallPromptEvent extends Event {
  prompt: () => Promise<void>
  userChoice: Promise<{ outcome: 'accepted' | 'dismissed' }>
}

let deferred: InstallPromptEvent | null = null
const listeners = new Set<() => void>()
const notify = () => listeners.forEach((fn) => fn())

/** Register the (pass-through) service worker and catch the install prompt. Call once per page. */
export function setupInstall() {
  if ('serviceWorker' in navigator && (location.protocol === 'https:' || location.hostname === 'localhost')) {
    navigator.serviceWorker.register('/sw.js').catch(() => undefined)
  }
  window.addEventListener('beforeinstallprompt', (event) => {
    event.preventDefault()
    deferred = event as InstallPromptEvent
    notify()
  })
  window.addEventListener('appinstalled', () => {
    deferred = null
    notify()
  })
}

export function isInstalled() {
  return window.matchMedia('(display-mode: standalone)').matches || (navigator as Navigator & { standalone?: boolean }).standalone === true
}

export function isIos() {
  return /iphone|ipad|ipod/i.test(navigator.userAgent)
}

/** Whether this browser can show its own install dialog right now, and a function to show it. */
export function useInstallPrompt() {
  const [, force] = useState(0)
  useEffect(() => {
    const update = () => force((n) => n + 1)
    listeners.add(update)
    return () => {
      listeners.delete(update)
    }
  }, [])
  return {
    canInstall: deferred !== null,
    installed: isInstalled(),
    install: async () => {
      if (!deferred) return false
      await deferred.prompt()
      const { outcome } = await deferred.userChoice
      deferred = null
      notify()
      return outcome === 'accepted'
    },
  }
}
