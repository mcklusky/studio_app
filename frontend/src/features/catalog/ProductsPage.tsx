import { MenuSelect } from '../../components/MenuSelect'
import { Layers, Package, Pencil } from 'lucide-react'
import { TableSkeleton } from '../../components/Feedback'
import { ActionsHeader, actionColumns, RowActions } from '../../components/RowActions'
import { useCallback, useEffect, useState, type FormEvent } from 'react'
import { Attachments, IMAGE_ACCEPT, PendingFilePicker, uploadAttachment } from '../../components/Attachments'
import { Dialog } from '../../components/Dialog'
import { EmptyState, ErrorBanner, SelectField, TextAreaField, TextField } from '../../components/Form'
import { api, ApiError, type FieldErrors, type Page } from '../../lib/api'
import { formatQuantity } from '../../lib/format'
import { CurrencySwitch, useDisplayCurrency } from '../currencies/DisplayCurrency'
import { useAuth } from '../identity/AuthContext'
import type { Focus } from '../../app/focus'

interface Variant {
  id: string
  code: string
  size: string
  color: string
  active: boolean
}

export interface Product {
  id: string
  section: string
  section_name: string
  category: string | null
  category_name: string | null
  name: string
  sku: string
  kind: 'product' | 'service'
  tracks_stock: boolean
  buying_price_base?: string
  selling_price_base: string
  minimum_stock: string
  status: 'active' | 'inactive'
  show_online: boolean
  public_description: string
  variants: Variant[]
  image_url: string | null
}

interface Draft {
  name: string
  section: string
  sku: string
  kind: 'product' | 'service'
  tracks_stock: boolean
  buying_price_base: string
  selling_price_base: string
  minimum_stock: string
  status: 'active' | 'inactive'
  show_online: boolean
  public_description: string
}

export function ProductsPage({ notify, focus }: { notify: (message: string) => void; focus?: Focus }) {
  const { can, viewSections: sections } = useAuth()
  const { base } = useDisplayCurrency()
  const [query, setQuery] = useState(focus?.query ?? '')
  const [section, setSection] = useState('')
  const [page, setPage] = useState(1)
  const [data, setData] = useState<Page<Product> | null>(null)
  const [loadError, setLoadError] = useState<unknown>(null)
  const [editing, setEditing] = useState<Product | 'new' | null>(null)

  const load = useCallback(async () => {
    setLoadError(null)
    try {
      setData(await api.get<Page<Product>>('/products/', { search: query, section, page }))
    } catch (err) {
      setLoadError(err)
    }
  }, [query, section, page])

  useEffect(() => {
    const timer = window.setTimeout(load, query ? 250 : 0)
    return () => window.clearTimeout(timer)
  }, [load, query])

  const canCreate = can('catalog.create')
  const canManage = can('catalog.manage')
  const actionCols = actionColumns(canManage && 'Edit')

  return (
    <div className="page">
      <div className="page-header">
        <div>
          <p className="eyebrow">MANAGE</p>
          <h1>Products &amp; services</h1>
          <p className="subheading">{data ? `${data.count} items` : 'Loading…'}</p>
        </div>
        <CurrencySwitch />
        {canCreate && (
          <button className="button button-primary" onClick={() => setEditing('new')}>
            ＋ Add product
          </button>
        )}
      </div>

      <div className="toolbar">
        <input
          type="search"
          className="search-input"
          placeholder="Search name or SKU"
          aria-label="Search products"
          value={query}
          onChange={(e) => {
            setQuery(e.target.value)
            setPage(1)
          }}
        />
        {sections.length > 1 && (
          <MenuSelect
            variant="pill"
            icon={Layers}
            className="toolbar-select"
            aria-label="Section"
            value={section}
            onChange={(e) => {
              setSection(e.target.value)
              setPage(1)
            }}
          >
            <option value="">All sections</option>
            {sections.map((s) => (
              <option key={s.id} value={s.id}>
                {s.name}
              </option>
            ))}
          </MenuSelect>
        )}
      </div>

      <ErrorBanner error={loadError} />

      {data && data.results.length === 0 ? (
        <EmptyState icon={Package} title={query || section ? 'No products match' : 'No products yet'}>
          {!query && !section && canCreate && (
            <button className="button button-secondary" onClick={() => setEditing('new')}>
              Add your first product
            </button>
          )}
        </EmptyState>
      ) : !data ? (
        !loadError && <TableSkeleton columns={5} />
      ) : (
        <div className="panel table-panel">
          <table className="data-table">
            <thead>
              <tr>
                <th scope="col">Name</th>
                <th scope="col" className="hide-mobile">
                  Section
                </th>
                <th scope="col" className="num">
                  Price
                </th>
                <th scope="col" className="hide-mobile">
                  Stock
                </th>
                <ActionsHeader />
              </tr>
            </thead>
            <tbody>
              {data.results.map((product) => {
                const options = product.variants.filter((v) => v.active && v.code !== 'default')
                return (
                  <tr key={product.id} className={product.status === 'active' ? '' : 'is-inactive'}>
                    <td>
                      <span className="product-cell">
                        {product.image_url ? (
                          <img className="product-thumb" src={product.image_url} alt="" loading="lazy" />
                        ) : (
                          <span className="product-thumb product-thumb-empty" aria-hidden="true">
                            {product.name.slice(0, 1).toUpperCase()}
                          </span>
                        )}
                        <span>
                          <b>{product.name}</b>
                          {product.status !== 'active' && <span className="badge">Inactive</span>}
                          {product.show_online && product.status === 'active' && <span className="badge badge-online">On website</span>}
                          <small className="cell-sub">
                            {[
                              product.sku,
                              product.kind === 'service' ? 'Service' : null,
                              options.length ? `${options.length} options` : null,
                            ]
                              .filter(Boolean)
                              .join(' · ')}
                          </small>
                        </span>
                      </span>
                    </td>
                    <td className="hide-mobile">{product.section_name}</td>
                    <td className="num">{base(product.selling_price_base)}</td>
                    <td className="hide-mobile">{product.tracks_stock ? `Min ${formatQuantity(product.minimum_stock)}` : 'Not tracked'}</td>
                    <RowActions
                      label={`Actions for ${product.name}`}
                      columns={actionCols}
                      actions={{
                        Edit: { label: 'Edit product', icon: Pencil, tone: 'violet', onClick: () => setEditing(product) },
                      }}
                    />
                  </tr>
                )
              })}
            </tbody>
          </table>
          {(data.next || data.previous) && (
            <div className="pager">
              <button className="button button-ghost" disabled={!data.previous} onClick={() => setPage((p) => p - 1)}>
                ← Previous
              </button>
              <span>Page {page}</span>
              <button className="button button-ghost" disabled={!data.next} onClick={() => setPage((p) => p + 1)}>
                Next →
              </button>
            </div>
          )}
        </div>
      )}

      {editing && (
        <ProductDialog
          key={editing === 'new' ? 'new' : editing.id}
          product={editing === 'new' ? null : editing}
          onClose={() => setEditing(null)}
          onSaved={(saved, created) => {
            void load()
            if (created && saved.tracks_stock) {
              // Stay open in edit mode so sizes/colours can be added straight away.
              notify(`Added ${saved.name}. Add sizes or colours if needed, then record opening stock under Inventory.`)
              setEditing(saved)
            } else {
              notify(created ? `Added ${saved.name}.` : `Saved ${saved.name}.`)
              setEditing(null)
            }
          }}
        />
      )}
    </div>
  )
}

function ProductDialog({
  product,
  onClose,
  onSaved,
}: {
  product: Product | null
  onClose: () => void
  onSaved: (product: Product, created: boolean) => void
}) {
  const { sections, can, organization } = useAuth()
  const showCosts = can('inventory.costs')
  const currency = organization?.base_currency ?? 'USD'
  const [draft, setDraft] = useState<Draft>(() =>
    product
      ? {
          name: product.name,
          section: product.section,
          sku: product.sku,
          kind: product.kind,
          tracks_stock: product.tracks_stock,
          buying_price_base: product.buying_price_base ?? '',
          selling_price_base: product.selling_price_base,
          minimum_stock: product.minimum_stock,
          status: product.status,
          show_online: product.show_online,
          public_description: product.public_description,
        }
      : {
          name: '',
          section: sections.length === 1 ? sections[0].id : '',
          sku: '',
          kind: 'product',
          tracks_stock: true,
          buying_price_base: '',
          selling_price_base: '',
          minimum_stock: '0',
          status: 'active',
          show_online: false,
          public_description: '',
        },
  )
  const [fieldErrors, setFieldErrors] = useState<FieldErrors>({})
  const [error, setError] = useState<unknown>(null)
  const [saving, setSaving] = useState(false)
  const [image, setImage] = useState<File | null>(null)

  const set = <K extends keyof Draft>(key: K, value: Draft[K]) => setDraft((d) => ({ ...d, [key]: value }))

  async function handleSubmit(event: FormEvent) {
    event.preventDefault()
    const errors: FieldErrors = {}
    if (!draft.name.trim()) errors.name = ['Enter a name.']
    if (!draft.section) errors.section = ['Choose a section.']
    if (Object.keys(errors).length) {
      setFieldErrors(errors)
      return
    }
    setSaving(true)
    setError(null)
    setFieldErrors({})
    const body: Record<string, unknown> = {
      ...draft,
      name: draft.name.trim(),
      sku: draft.sku.trim(),
      tracks_stock: draft.kind === 'service' ? false : draft.tracks_stock,
      selling_price_base: draft.selling_price_base || '0',
      minimum_stock: draft.minimum_stock || '0',
    }
    if (showCosts) body.buying_price_base = draft.buying_price_base || '0'
    else delete body.buying_price_base
    try {
      const saved = product ? await api.patch<Product>(`/products/${product.id}/`, body) : await api.post<Product>('/products/', body)
      if (!product && image) {
        try {
          await uploadAttachment('product_image', saved.id, image)
        } catch {
          // The product is saved; the photo can be added again from Edit.
        }
      }
      onSaved(saved, !product)
    } catch (err) {
      if (err instanceof ApiError) setFieldErrors(err.fieldErrors)
      setError(err)
    } finally {
      setSaving(false)
    }
  }

  return (
    <Dialog title={product ? `Edit ${product.name}` : 'Add product or service'} onClose={onClose} onSubmit={handleSubmit}>
      <ErrorBanner error={error} />
      <TextField label="Name" autoFocus value={draft.name} onChange={(e) => set('name', e.target.value)} error={fieldErrors.name} />
      <div className="field-row">
        <SelectField label="Section" value={draft.section} onChange={(e) => set('section', e.target.value)} error={fieldErrors.section}>
          <option value="">Choose…</option>
          {sections.map((s) => (
            <option key={s.id} value={s.id}>
              {s.name}
            </option>
          ))}
        </SelectField>
        <SelectField
          label="Type"
          value={draft.kind}
          onChange={(e) => set('kind', e.target.value as Draft['kind'])}
          error={fieldErrors.kind}
        >
          <option value="product">Product (physical item)</option>
          <option value="service">Service</option>
        </SelectField>
      </div>
      <div className="field-row">
        <TextField
          label={`Selling price (${currency})`}
          inputMode="decimal"
          value={draft.selling_price_base}
          onChange={(e) => set('selling_price_base', e.target.value)}
          error={fieldErrors.selling_price_base}
        />
        {showCosts && (
          <TextField
            label={`Buying price (${currency})`}
            inputMode="decimal"
            value={draft.buying_price_base}
            onChange={(e) => set('buying_price_base', e.target.value)}
            error={fieldErrors.buying_price_base}
            hint="Reference only; stock cost comes from receipts."
          />
        )}
      </div>
      {product ? (
        <Attachments
          purpose="product_image"
          owner={product.id}
          label="Photo"
          accept={IMAGE_ACCEPT}
          single
          canAdd={can('catalog.manage')}
          canRemove={can('catalog.manage')}
        />
      ) : (
        can('catalog.manage') && <PendingFilePicker label="Photo (optional)" accept={IMAGE_ACCEPT} file={image} onChange={setImage} />
      )}
      <TextField label="SKU / code (optional)" value={draft.sku} onChange={(e) => set('sku', e.target.value)} error={fieldErrors.sku} />
      {draft.kind === 'product' && (
        <>
          <label className="checkbox">
            <input type="checkbox" checked={draft.tracks_stock} onChange={(e) => set('tracks_stock', e.target.checked)} /> Track stock for
            this product
          </label>
          {fieldErrors.tracks_stock && <p className="field-error">{fieldErrors.tracks_stock.join(' ')}</p>}
          {draft.tracks_stock && (
            <TextField
              label="Low-stock alert at"
              inputMode="decimal"
              value={draft.minimum_stock}
              onChange={(e) => set('minimum_stock', e.target.value)}
              error={fieldErrors.minimum_stock}
              hint="Shown as low stock when on-hand quantity reaches this number."
            />
          )}
        </>
      )}
      {product && (
        <SelectField label="Status" value={draft.status} onChange={(e) => set('status', e.target.value as Draft['status'])}>
          <option value="active">Active</option>
          <option value="inactive">Inactive (hidden from sales)</option>
        </SelectField>
      )}
      <fieldset className="website-fieldset">
        <legend>Public website</legend>
        <label className="checkbox">
          <input type="checkbox" checked={draft.show_online} onChange={(e) => set('show_online', e.target.checked)} /> Show this on the
          website, with its selling price
        </label>
        {draft.show_online && (
          <TextAreaField
            label="What customers read about it"
            rows={3}
            maxLength={600}
            value={draft.public_description}
            onChange={(e) => set('public_description', e.target.value)}
            error={fieldErrors.public_description}
            hint="Plain words, e.g. what is included and how long it takes. Never shown: costs, stock or SKU."
          />
        )}
      </fieldset>
      {product && product.tracks_stock && <VariantEditor product={product} />}
      <div className="dialog-actions">
        <button type="button" className="button button-secondary" onClick={onClose}>
          {product ? 'Close' : 'Cancel'}
        </button>
        <button type="submit" className="button button-primary" disabled={saving}>
          {saving ? 'Saving…' : 'Save'}
        </button>
      </div>
    </Dialog>
  )
}

/** Sizes/colours. Each option holds its own stock. */
function VariantEditor({ product }: { product: Product }) {
  const [variants, setVariants] = useState(product.variants.filter((v) => v.active && v.code !== 'default'))
  const [size, setSize] = useState('')
  const [color, setColor] = useState('')
  const [error, setError] = useState<unknown>(null)
  const [adding, setAdding] = useState(false)

  async function addVariant() {
    if (!size.trim() && !color.trim()) return
    setAdding(true)
    setError(null)
    try {
      const code = [size.trim(), color.trim()].filter(Boolean).join('-').toUpperCase().replace(/\s+/g, '-')
      const created = await api.post<Variant>('/product-variants/', { product: product.id, code, size: size.trim(), color: color.trim() })
      setVariants((list) => [...list, created])
      setSize('')
      setColor('')
    } catch (err) {
      setError(err)
    } finally {
      setAdding(false)
    }
  }

  return (
    <fieldset className="subsection">
      <legend>Sizes and colours</legend>
      <p className="field-hint">Optional. Add these before recording stock: each option keeps its own count.</p>
      {variants.length > 0 && (
        <ul className="chip-list">
          {variants.map((v) => (
            <li key={v.id} className="chip">
              {[v.size, v.color].filter(Boolean).join(' / ') || v.code}
            </li>
          ))}
        </ul>
      )}
      <ErrorBanner error={error} />
      <div className="field-row field-row-end">
        <TextField label="Size" value={size} onChange={(e) => setSize(e.target.value)} placeholder="e.g. M" />
        <TextField label="Colour" value={color} onChange={(e) => setColor(e.target.value)} placeholder="e.g. Black" />
        <button
          type="button"
          className="button button-secondary add-variant"
          onClick={addVariant}
          disabled={adding || (!size.trim() && !color.trim())}
        >
          Add
        </button>
      </div>
    </fieldset>
  )
}
