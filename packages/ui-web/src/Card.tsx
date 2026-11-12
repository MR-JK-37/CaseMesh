import type { HTMLAttributes } from "react";

export interface CardProps extends HTMLAttributes<HTMLDivElement> {
  className?: string;
}

export interface TileProps extends HTMLAttributes<HTMLDivElement> {
  className?: string;
}

/** Section 9.1 rule 3: content cards stay solid, never glass. */
export function Card({ className = "", ...props }: CardProps) {
  return (
    <div
      className={`rounded-card bg-surface-0 p-6 shadow-[0_8px_24px_rgba(10,46,69,.12)] transition-shadow duration-200 ${className}`}
      {...props}
    />
  );
}

export function Tile({ className = "", ...props }: TileProps) {
  return (
    <div
      className={`rounded-tile bg-surface-1 p-4 shadow-[0_2px_8px_rgba(10,46,69,.08)] transition-shadow duration-200 ${className}`}
      {...props}
    />
  );
}

