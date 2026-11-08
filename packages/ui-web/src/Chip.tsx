export function Chip({
  active = false,
  disabled = false,
  className = "",
  size = "md",
  children,
  onClick,
}: {
  active?: boolean;
  disabled?: boolean;
  className?: string;
  size?: "sm" | "md";
  children: React.ReactNode;
  onClick?: () => void;
}) {
  const sizeClasses = size === "sm" ? "min-h-7 px-3 text-xs" : "min-h-9 px-4 text-sm";
  return (
    <button
      type="button"
      aria-pressed={active}
      disabled={disabled}
      onClick={onClick}
      className={`rounded-pill font-medium transition-colors duration-200
        focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-brand-500
        disabled:opacity-50 disabled:cursor-not-allowed ${sizeClasses} ${className}
        ${
          // brand-500 is documented as decorative/non-text only (3.9:1 on
          // white, Section 9.2) — white text needs brand-600 (5.44:1).
          active
            ? "bg-brand-600 text-white"
            : "bg-brand-50 text-ink border border-outline hover:bg-surface-2"
        }`}
    >
      {children}
    </button>
  );
}
