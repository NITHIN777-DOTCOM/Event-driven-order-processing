/**
 * The only drawn graphics in the app: small line icons for the order tracker's stages.
 * 32x32 grid, 1.8px ink stroke, cream (#FAEAB1) / amber (#C58940) fills.
 */
import type { ReactNode, SVGProps } from "react";

const INK = "#222831";
const CREAM = "#FAEAB1";
const AMBER = "#C58940";
const GREEN = "#2F855A";

function Icon({ children, ...props }: SVGProps<SVGSVGElement> & { children: ReactNode }) {
  return (
    <svg
      viewBox="0 0 32 32"
      width={32}
      height={32}
      fill="none"
      stroke={INK}
      strokeWidth={1.8}
      strokeLinecap="round"
      strokeLinejoin="round"
      aria-hidden="true"
      {...props}
    >
      {children}
    </svg>
  );
}

/** Placed: a receipt. */
export const ReceiptIcon = () => (
  <Icon>
    <path d="M9 5h14v21.5l-2.33-1.5-2.34 1.5L16 25l-2.33 1.5-2.34-1.5L9 26.5z" fill={CREAM} />
    <path d="M12.5 10.5h7M12.5 14.5h7M12.5 18.5h4.5" />
  </Icon>
);

/** Queued: boxes moving along a line. */
export const QueueIcon = () => (
  <Icon>
    <path d="M12 7.5h11.5M21 5l2.5 2.5L21 10" />
    <rect x="4" y="13" width="6" height="6" rx="1.2" fill="#fff" />
    <rect x="12" y="13" width="6" height="6" rx="1.2" fill="#fff" />
    <rect x="20" y="13" width="7" height="6" rx="1.2" fill={AMBER} />
    <path d="M4 23.5h24" />
  </Icon>
);

/** Stock reserved: a package. */
export const PackageIcon = () => (
  <Icon>
    <path d="M16 4.5 26 9.5v12L16 26.5 6 21.5v-12z" fill={CREAM} />
    <path d="M6 9.5l10 5 10-5M16 14.5v12M11 7l10 5" />
  </Icon>
);

/** Paid: a card. */
export const CardIcon = () => (
  <Icon>
    <rect x="4" y="8" width="24" height="16" rx="2.5" fill={CREAM} />
    <path d="M4 13h24" />
    <rect x="8" y="17.5" width="5.5" height="3" rx="0.8" fill={AMBER} />
  </Icon>
);

/** Confirmed: an envelope with a green check. */
export const EnvelopeCheckIcon = () => (
  <Icon>
    <rect x="3.5" y="7.5" width="21" height="15" rx="2" fill={CREAM} />
    <path d="m4 8.5 10 7.5 10-7.5" />
    <circle cx="24" cy="22.5" r="5" fill={GREEN} />
    <path d="m21.7 22.6 1.6 1.6 3-3.2" stroke="#fff" />
  </Icon>
);

/** Stock released (compensation): a package with a return arrow. */
export const PackageReturnIcon = () => (
  <Icon>
    <path d="M13 4.5 21.5 8.75v9.5L13 22.5 4.5 18.25v-9.5z" fill={CREAM} />
    <path d="M4.5 8.75 13 13l8.5-4.25M13 13v9.5" />
    <path d="M28 18.5v2.5a3.5 3.5 0 0 1-3.5 3.5H17.5" />
    <path d="m20.5 21.5-3 3 3 3" />
  </Icon>
);
