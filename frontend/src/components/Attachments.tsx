import { useCallback, useEffect, useRef, useState } from 'react'
import { api } from '../lib/api'
import { ErrorBanner } from './Form'

export interface Attachment {
  id: string
  purpose: string
  original_name: string
  content_type: string
  file_size: number
  url: string
  uploaded_by_name: string
  created_at: string
}

export const RECEIPT_ACCEPT = 'image/jpeg,image/png,image/webp,application/pdf'
export const IMAGE_ACCEPT = 'image/jpeg,image/png,image/webp'
const MAX_MB = 8

/** Upload one file for a record. Phones offer the camera from the same picker. */
export function uploadAttachment(purpose: string, owner: string, file: File) {
  const form = new FormData()
  form.append('purpose', purpose)
  form.append('owner', owner)
  form.append('file', file)
  return api.upload<Attachment>('/attachments/', form)
}

export function tooLarge(file: File) {
  return file.size > MAX_MB * 1024 * 1024 ? `The file is too large. The limit is ${MAX_MB} MB.` : null
}

/** Thumbnails of a record's files, with add/remove when allowed. `single` replaces instead of adding. */
export function Attachments({
  purpose,
  owner,
  label,
  accept,
  canAdd,
  canRemove,
  max = 5,
  single = false,
  onChange,
}: {
  purpose: string
  owner: string
  label: string
  accept: string
  canAdd: boolean
  canRemove: boolean
  max?: number
  single?: boolean
  onChange?: (files: Attachment[]) => void
}) {
  const [files, setFiles] = useState<Attachment[] | null>(null)
  const [error, setError] = useState<unknown>(null)
  const [busy, setBusy] = useState(false)
  const input = useRef<HTMLInputElement>(null)

  const load = useCallback(() => {
    api
      .get<Attachment[]>('/attachments/', { purpose, owner })
      .then((rows) => {
        setFiles(rows)
        onChange?.(rows)
      })
      .catch(setError)
  }, [purpose, owner, onChange])
  useEffect(load, [load])

  async function add(file: File | undefined) {
    if (!file) return
    const problem = tooLarge(file)
    if (problem) {
      setError(new Error(problem))
      return
    }
    setBusy(true)
    setError(null)
    try {
      await uploadAttachment(purpose, owner, file)
      load()
    } catch (err) {
      setError(err)
    } finally {
      setBusy(false)
      if (input.current) input.current.value = ''
    }
  }

  async function remove(file: Attachment) {
    if (!window.confirm(`Remove ${file.content_type === 'application/pdf' ? 'this PDF' : 'this photo'}? This cannot be undone.`)) return
    setBusy(true)
    setError(null)
    try {
      await api.delete(`/attachments/${file.id}/`)
      load()
    } catch (err) {
      setError(err)
    } finally {
      setBusy(false)
    }
  }

  const room = single || (files?.length ?? 0) < max
  return (
    <div className="attachments">
      <p className="attachments-label">{label}</p>
      <ErrorBanner error={error} />
      <div className="attachment-grid">
        {files?.map((file) => (
          <figure key={file.id} className="attachment-tile">
            <a
              href={`${file.url}?inline=1`}
              target="_blank"
              rel="noopener noreferrer"
              title={`Open (uploaded by ${file.uploaded_by_name})`}
            >
              {file.content_type.startsWith('image/') ? (
                <img src={file.url} alt={label} loading="lazy" />
              ) : (
                <span className="pdf-tile" aria-label="PDF">
                  PDF
                </span>
              )}
            </a>
            {canRemove && (
              <button type="button" className="tile-remove" aria-label="Remove" disabled={busy} onClick={() => void remove(file)}>
                ×
              </button>
            )}
          </figure>
        ))}
        {canAdd && room && (
          <label className={`attachment-add ${busy ? 'is-busy' : ''}`}>
            <input ref={input} type="file" accept={accept} disabled={busy} onChange={(e) => void add(e.target.files?.[0])} />
            <span aria-hidden="true">{busy ? '…' : '＋'}</span>
            <small>
              {busy ? 'Uploading' : single && files?.length ? 'Replace' : accept.includes('pdf') ? 'Photo or PDF' : 'Add photo'}
            </small>
          </label>
        )}
        {files?.length === 0 && !canAdd && <p className="field-hint">None attached.</p>}
      </div>
    </div>
  )
}

/** A file chosen before its record exists (uploaded right after saving). */
export function PendingFilePicker({
  label,
  accept,
  file,
  onChange,
}: {
  label: string
  accept: string
  file: File | null
  onChange: (file: File | null) => void
}) {
  const [preview, setPreview] = useState<string | null>(null)
  const [problem, setProblem] = useState<string | null>(null)

  function pick(next: File | null) {
    if (preview) URL.revokeObjectURL(preview)
    const issue = next ? tooLarge(next) : null
    setProblem(issue)
    const chosen = issue ? null : next
    setPreview(chosen && chosen.type.startsWith('image/') ? URL.createObjectURL(chosen) : null)
    onChange(chosen)
  }

  return (
    <div className="attachments">
      <p className="attachments-label">{label}</p>
      {problem && <p className="field-error">{problem}</p>}
      <div className="attachment-grid">
        {file ? (
          <figure className="attachment-tile">
            {preview ? <img src={preview} alt="" /> : <span className="pdf-tile">PDF</span>}
            <button type="button" className="tile-remove" aria-label="Remove" onClick={() => pick(null)}>
              ×
            </button>
          </figure>
        ) : (
          <label className="attachment-add">
            <input type="file" accept={accept} onChange={(e) => pick(e.target.files?.[0] ?? null)} />
            <span aria-hidden="true">＋</span>
            <small>{accept.includes('pdf') ? 'Photo or PDF' : 'Add photo'}</small>
          </label>
        )}
      </div>
    </div>
  )
}
