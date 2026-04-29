/**
 * Tiny class-name combinator.
 *
 * Drop-in replacement for `clsx` for our needs — joins truthy
 * strings with a single space. Keeping it local avoids adding
 * a dependency for a 10-line utility.
 */
export function cn(...values: Array<string | false | null | undefined>): string {
  return values.filter((v): v is string => Boolean(v) && typeof v === "string").join(" ");
}
