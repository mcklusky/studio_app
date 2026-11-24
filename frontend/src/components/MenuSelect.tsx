import { Check, ChevronDown, type LucideIcon } from 'lucide-react'
import {
  Children,
  isValidElement,
  useEffect,
  useLayoutEffect,
  useRef,
  useState,
  type CSSProperties,
  type KeyboardEvent,
  type ReactElement,
  type ReactNode,
} from 'react'

export interface MenuOption {
  value: string
  label: string
  icon?: LucideIcon
  tone?: string
  disabled?: boolean
}

/** Same shape as a native select's change event for the parts callers use (`e.target.value`). */
export interface MenuSelectChange {
  target: { value: string }
  currentTarget: { value: string }
}

export interface MenuSelectProps {
  value: string
  onChange?: (event: MenuSelectChange) => void
  /** Either `options`, or `<option>` children as with a native select. */
  options?: MenuOption[]
  children?: ReactNode
  /** pill = yellow toolbar filter, field = form input, subtle = white top-bar control. */
  variant?: 'pill' | 'field' | 'subtle'
  /** Icon shown on the button (the chosen option's own icon wins). */
  icon?: LucideIcon
  className?: string
  id?: string
  disabled?: boolean
  title?: string
  'aria-label'?: string
  'aria-invalid'?: boolean
  'aria-describedby'?: string
}

function textOf(node: ReactNode): string {
  if (node === null || node === undefined || typeof node === 'boolean') return ''
  if (typeof node === 'string' || typeof node === 'number') return String(node)
  if (Array.isArray(node)) return node.map(textOf).join('')
  if (isValidElement(node)) return textOf((node.props as { children?: ReactNode }).children)
  return ''
}

/** Read `<option>` children (including mapped arrays) into menu options. */
export function optionsFromChildren(children: ReactNode): MenuOption[] {
  const out: MenuOption[] = []
  Children.forEach(children, (child) => {
    if (!isValidElement(child)) return
    const element = child as ReactElement<{ value?: string | number; disabled?: boolean; children?: ReactNode }>
    if (element.type === 'option') {
      const label = textOf(element.props.children)
      out.push({ value: String(element.props.value ?? label), label, disabled: element.props.disabled })
    } else {
      out.push(...optionsFromChildren(element.props.children))
    }
  })
  return out
}

const MENU_GAP = 6
const MENU_MAX = 320

/**
 * Drop-down in the app's own menu style (the same card as the row Edit menu), usable wherever a
 * native select was: it takes `value`, `onChange(e)` with `e.target.value`, and `<option>` children.
 */
export function MenuSelect({
  value,
  onChange,
  options,
  children,
  variant = 'pill',
  icon,
  className = '',
  id,
  disabled,
  title,
  'aria-label': ariaLabel,
  'aria-invalid': invalid,
  'aria-describedby': describedBy,
}: MenuSelectProps) {
  const items = options ?? optionsFromChildren(children)
  const current = items.find((o) => o.value === value)
  const [open, setOpen] = useState(false)
  const [style, setStyle] = useState<CSSProperties | null>(null)
  const trigger = useRef<HTMLButtonElement>(null)
  const menu = useRef<HTMLDivElement>(null)

  // Fixed to the viewport so dialogs and scrolling tables cannot clip it; opens upward when short of room.
  useLayoutEffect(() => {
    if (!open || !trigger.current) return
    const rect = trigger.current.getBoundingClientRect()
    const below = window.innerHeight - rect.bottom - MENU_GAP - 8
    const above = rect.top - MENU_GAP - 8
    const up = below < Math.min(MENU_MAX, items.length * 44 + 14) && above > below
    const maxHeight = Math.min(MENU_MAX, up ? above : below)
    const minWidth = Math.max(rect.width, 200)
    const left = Math.min(rect.left, window.innerWidth - minWidth - 8)
    setStyle(
      up
        ? { bottom: window.innerHeight - rect.top + MENU_GAP, left, minWidth, maxHeight }
        : { top: rect.bottom + MENU_GAP, left, minWidth, maxHeight },
    )
  }, [open, items.length])

  useEffect(() => {
    if (!open) return
    const close = (event: Event) => {
      const target = event.target as Node
      if (menu.current?.contains(target) || trigger.current?.contains(target)) return
      setOpen(false)
    }
    document.addEventListener('mousedown', close)
    window.addEventListener('scroll', close, true)
    window.addEventListener('resize', close)
    return () => {
      document.removeEventListener('mousedown', close)
      window.removeEventListener('scroll', close, true)
      window.removeEventListener('resize', close)
    }
  }, [open])

  useEffect(() => {
    if (!open || !style) return
    const target =
      menu.current?.querySelector<HTMLButtonElement>('[aria-checked="true"]') ??
      menu.current?.querySelector<HTMLButtonElement>('button:not(:disabled)')
    target?.focus()
    target?.scrollIntoView({ block: 'nearest' })
  }, [open, style])

  function choose(option: MenuOption) {
    setOpen(false)
    trigger.current?.focus()
    if (option.value !== value) onChange?.({ target: { value: option.value }, currentTarget: { value: option.value } })
  }

  function onMenuKey(event: KeyboardEvent<HTMLDivElement>) {
    const buttons = [...(menu.current?.querySelectorAll<HTMLButtonElement>('.row-menu-item:not(:disabled)') ?? [])]
    const index = buttons.indexOf(document.activeElement as HTMLButtonElement)
    if (event.key === 'ArrowDown' || event.key === 'ArrowUp') {
      event.preventDefault()
      const step = event.key === 'ArrowDown' ? 1 : -1
      buttons[(index + step + buttons.length) % buttons.length]?.focus()
    } else if (event.key === 'Home' || event.key === 'End') {
      event.preventDefault()
      buttons[event.key === 'Home' ? 0 : buttons.length - 1]?.focus()
    } else if (event.key === 'Escape' || event.key === 'Tab') {
      if (event.key === 'Escape') event.preventDefault()
      setOpen(false)
      trigger.current?.focus()
    } else if (event.key.length === 1) {
      // Type a letter to jump to the next option starting with it.
      const letter = event.key.toLowerCase()
      const start = index + 1
      const next = [...buttons.slice(start), ...buttons.slice(0, start)].find((b) => b.textContent?.trim().toLowerCase().startsWith(letter))
      next?.focus()
    }
  }

  const TriggerIcon = current?.icon ?? icon
  const isSet = className.includes('active') || (variant === 'pill' && value !== '' && value !== items[0]?.value)
  return (
    <>
      <button
        ref={trigger}
        id={id}
        type="button"
        className={`menu-select menu-select-${variant} ${isSet ? 'is-set' : ''} ${className.replace(/\b(toolbar-select|active)\b/g, '')}`}
        aria-haspopup="menu"
        aria-expanded={open}
        aria-label={ariaLabel ? `${ariaLabel}: ${current?.label ?? 'none'}` : undefined}
        aria-invalid={invalid || undefined}
        aria-describedby={describedBy}
        disabled={disabled}
        title={title}
        onClick={() => setOpen((o) => !o)}
        onKeyDown={(e) => {
          if (e.key === 'ArrowDown' || e.key === 'ArrowUp') {
            e.preventDefault()
            setOpen(true)
          }
        }}
      >
        {TriggerIcon && <TriggerIcon size={16} className="menu-select-icon" aria-hidden="true" />}
        <span className="menu-select-text">{current?.label ?? ''}</span>
        <ChevronDown size={16} className="menu-select-chevron" aria-hidden="true" />
      </button>
      {open && style && (
        <div ref={menu} className="row-menu menu-select-menu" role="menu" aria-label={ariaLabel} style={style} onKeyDown={onMenuKey}>
          {items.map((option) => {
            const selected = option.value === value
            const OptionIcon = option.icon
            return (
              <button
                key={option.value}
                type="button"
                role="menuitemradio"
                aria-checked={selected}
                disabled={option.disabled}
                className={`row-menu-item ${selected ? 'is-selected' : ''}`}
                onClick={() => choose(option)}
              >
                {OptionIcon && (
                  <span className={`row-menu-icon tone-${option.tone ?? 'olive'}`} aria-hidden="true">
                    <OptionIcon size={15} strokeWidth={2.2} />
                  </span>
                )}
                <span className="row-menu-label">{option.label}</span>
                {selected && <Check size={16} className="row-menu-check" aria-hidden="true" />}
              </button>
            )
          })}
        </div>
      )}
    </>
  )
}
