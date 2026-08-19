export default function Pokeball({
  size = 22,
  className = "",
}: {
  size?: number;
  className?: string;
}) {
  return (
    <svg
      width={size}
      height={size}
      viewBox="0 0 24 24"
      className={className}
      aria-hidden="true"
      focusable="false"
    >
      <circle cx="12" cy="12" r="10" fill="#0b0f17" stroke="currentColor" strokeWidth="1.6" />
      <path d="M12 2a10 10 0 0 1 10 10H2A10 10 0 0 1 12 2z" fill="currentColor" opacity="0.28" />
      <path d="M2.2 12h19.6" stroke="currentColor" strokeWidth="1.6" />
      <circle cx="12" cy="12" r="3.1" fill="#0b0f17" stroke="currentColor" strokeWidth="1.6" />
      <circle cx="12" cy="12" r="1.2" fill="currentColor" />
    </svg>
  );
}
