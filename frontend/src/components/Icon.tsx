import { iconInner, type IconName } from '../lib/icons'

interface Props {
  name: IconName
  /** Pixel size. */
  size?: number
  className?: string
}

/** An inline icon in the current text color. The markup comes from the icon package, not from users. */
export default function Icon({ name, size = 18, className }: Props) {
  return (
    <svg
      className={className ? `icon ${className}` : 'icon'}
      width={size}
      height={size}
      viewBox="0 0 24 24"
      fill="none"
      stroke="currentColor"
      strokeWidth={2}
      strokeLinecap="round"
      strokeLinejoin="round"
      aria-hidden="true"
      dangerouslySetInnerHTML={{ __html: iconInner(name) }}
    />
  )
}
