/** אייקוני קו קטנים, באותו סגנון של דף הפתיחה. בלי חבילת אייקונים. */

type IconProps = { size?: number; className?: string };

function Icon({ size = 16, className, children }: IconProps & { children: React.ReactNode }) {
  return (
    <svg
      width={size} height={size} viewBox="0 0 24 24" fill="none" stroke="currentColor"
      strokeWidth="1.7" strokeLinecap="round" strokeLinejoin="round" aria-hidden className={className}
    >
      {children}
    </svg>
  );
}

export const IconDownload = (p: IconProps) => <Icon {...p}><path d="M12 4v11m0 0 4-4m-4 4-4-4M4 19h16" /></Icon>;
export const IconFile = (p: IconProps) => <Icon {...p}><path d="M14 3H7a2 2 0 0 0-2 2v14a2 2 0 0 0 2 2h10a2 2 0 0 0 2-2V8z" /><path d="M14 3v5h5M9 13h6M9 17h6" /></Icon>;
export const IconSheet = (p: IconProps) => <Icon {...p}><rect x="4" y="4" width="16" height="16" rx="2" /><path d="M4 10h16M4 15h16M10 4v16" /></Icon>;
export const IconPencil = (p: IconProps) => <Icon {...p}><path d="M4 20h4l10.5-10.5a2 2 0 0 0 0-2.8l-1.2-1.2a2 2 0 0 0-2.8 0L4 16z" /><path d="M13.5 6.5l4 4" /></Icon>;
export const IconSearch = (p: IconProps) => <Icon {...p}><circle cx="11" cy="11" r="7" /><path d="m20 20-3.5-3.5" /></Icon>;
export const IconLogout = (p: IconProps) => <Icon {...p}><path d="M10 4H6a2 2 0 0 0-2 2v12a2 2 0 0 0 2 2h4M15 8l5 4-5 4M20 12H9" /></Icon>;
export const IconChevronLeft = (p: IconProps) => <Icon {...p}><path d="M15 6l-6 6 6 6" /></Icon>;
export const IconChevronRight = (p: IconProps) => <Icon {...p}><path d="M9 6l6 6-6 6" /></Icon>;
export const IconArrowUp = (p: IconProps) => <Icon {...p}><path d="M12 19V5m0 0-6 6m6-6 6 6" /></Icon>;
export const IconArrowDown = (p: IconProps) => <Icon {...p}><path d="M12 5v14m0 0 6-6m-6 6-6-6" /></Icon>;
export const IconX = (p: IconProps) => <Icon {...p}><path d="M6 6l12 12M18 6 6 18" /></Icon>;
export const IconMenu = (p: IconProps) => <Icon {...p}><path d="M4 7h16M4 12h16M4 17h16" /></Icon>;
