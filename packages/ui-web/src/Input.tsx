import { useId, type InputHTMLAttributes } from "react";

export function Input({
  label,
  error,
  helperText,
  className = "",
  ...props
}: InputHTMLAttributes<HTMLInputElement> & { label: string; error?: string; helperText?: string }) {
  const id = useId();
  const errorId = `${id}-error`;
  const helpId = `${id}-help`;
  return (
    <div className="flex flex-col gap-1.5">
      <label htmlFor={id} className="text-sm font-medium text-ink-muted">
        {label}
      </label>
      <input
        id={id}
        aria-invalid={!!error}
        aria-describedby={error ? errorId : helperText ? helpId : undefined}
        className={`min-h-11 rounded-input border border-outline bg-surface-0 px-3.5 text-ink
          placeholder:text-ink-muted focus-visible:outline-none focus-visible:ring-2
          focus-visible:ring-brand-500 ${error ? "border-[#B42318]" : ""} ${className}`}
        {...props}
      />
      {helperText && !error && (
        <p id={helpId} className="text-xs text-ink-muted">
          {helperText}
        </p>
      )}
      {error && (
        <p id={errorId} role="alert" className="text-sm text-[#B42318]">
          {error}
        </p>
      )}
    </div>
  );
}
