import type { ButtonHTMLAttributes } from "react";

type Variant = "primary" | "secondary" | "destructive" | "ghost";

const base =
  "inline-flex items-center justify-center gap-2 font-medium transition-colors duration-200 " +
  "focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-brand-500 focus-visible:ring-offset-2 " +
  "disabled:opacity-50 disabled:cursor-not-allowed min-h-11 px-5 rounded-button";

const variants: Record<Variant, string> = {
  primary: "text-white hover:brightness-110",
  secondary: "bg-surface-1 text-ink border border-outline hover:bg-surface-2",
  destructive: "bg-[#B42318] text-white hover:brightness-110",
  ghost: "bg-transparent text-ink hover:bg-surface-1",
};

// Gradient fills use an inline style rather than a Tailwind arbitrary
// `bg-[image:var(...)]` utility — that utility did not apply the
// background-image in testing against this Tailwind v4 setup.
const variantStyle: Partial<Record<Variant, React.CSSProperties>> = {
  primary: { backgroundImage: "var(--grad-text)" },
};

export function Button({
  type = "button",
  variant = "primary",
  pill = false,
  className = "",
  style,
  ...props
}: ButtonHTMLAttributes<HTMLButtonElement> & { variant?: Variant; pill?: boolean }) {
  return (
    <button
      type={type}
      className={`${base} ${variants[variant]} ${pill ? "rounded-pill" : ""} ${className}`}
      style={{ ...variantStyle[variant], ...style }}
      {...props}
    />
  );
}
