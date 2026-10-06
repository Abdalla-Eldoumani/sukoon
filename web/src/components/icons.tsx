import type { ReactNode } from 'react'

function Icon({ children }: { children: ReactNode }) {
  return (
    <svg
      width="20"
      height="20"
      viewBox="0 0 20 20"
      fill="none"
      stroke="currentColor"
      strokeWidth="1.5"
      strokeLinecap="round"
      strokeLinejoin="round"
      aria-hidden="true"
      focusable="false"
    >
      {children}
    </svg>
  )
}

const page = 'M5 2.75h6.5L15 6.25v11H5z M11.5 2.75v3.5H15'

export const AudioFileIcon = () => (
  <Icon>
    <path d={page} />
    <path d="M8 11v3 M10 9.5v6 M12 10.75v2.5" />
  </Icon>
)

export const VideoFileIcon = () => (
  <Icon>
    <path d={page} />
    <path d="M8.75 9.75v4.5l3.75-2.25z" />
  </Icon>
)

export const LinkIcon = () => (
  <Icon>
    <path d="M8.5 11.5a3 3 0 0 0 4.2 0l2.6-2.6a3 3 0 0 0-4.2-4.2l-.9.9M11.5 8.5a3 3 0 0 0-4.2 0l-2.6 2.6a3 3 0 0 0 4.2 4.2l.9-.9" />
  </Icon>
)

export const PlayIcon = () => (
  <Icon>
    <path d="M6.5 4.25v11.5l9-5.75z" />
  </Icon>
)

export const PauseIcon = () => (
  <Icon>
    <path d="M7 4.5v11 M13 4.5v11" />
  </Icon>
)

export const DownloadIcon = () => (
  <Icon>
    <path d="M10 3.5v9 M6.5 9l3.5 3.5L13.5 9 M4 16.25h12" />
  </Icon>
)

export const CancelIcon = () => (
  <Icon>
    <path d="M5.5 5.5l9 9 M14.5 5.5l-9 9" />
  </Icon>
)

export const RetryIcon = () => (
  <Icon>
    <path d="M15.25 10a5.25 5.25 0 1 1-1.54-3.71 M14.25 3.5v3.25H11" />
  </Icon>
)

export const DeleteIcon = () => (
  <Icon>
    <path d="M4 6h12 M8 6V4h4v2 M5.5 6l.75 10.25h7.5L14.5 6 M8.5 9v4.5 M11.5 9v4.5" />
  </Icon>
)

export const SettingsIcon = () => (
  <Icon>
    <path d="M3.5 5.5h3 M10 5.5h6.5 M3.5 10h8 M15 10h1.5 M3.5 14.5h1.5 M8.5 14.5h8" />
    <circle cx="8.25" cy="5.5" r="1.75" />
    <circle cx="13.25" cy="10" r="1.75" />
    <circle cx="6.75" cy="14.5" r="1.75" />
  </Icon>
)

export const FolderIcon = () => (
  <Icon>
    <path d="M2.75 5.25h5l1.5 1.75h8v8.75H2.75z" />
  </Icon>
)
