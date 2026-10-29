import { clsx, type ClassValue } from "clsx"
import { twMerge } from "tailwind-merge"

export function cn(...inputs: ClassValue[]) {
  return twMerge(clsx(inputs))
}

// "LeBron James" -> "L. James", "Jaren Jackson Jr." -> "J. Jackson Jr." --
// the compact phone layout.
export function shortName(name: string): string {
  const parts = name.trim().split(/\s+/)
  return parts.length < 2 ? name : `${parts[0][0]}. ${parts.slice(1).join(" ")}`
}
