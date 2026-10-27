import { validTimezone } from "../api/interviews.ts";

export type LocalSchedule = { utc: string; error?: never } | { utc?: never; error: string };

// Match wall-clock minutes in the chosen zone, never in the machine's local zone.
// Enumeration detects overlaps instead of silently choosing a DST occurrence.
export function localSchedule(value: string, zone: string, now = Date.now()): LocalSchedule {
  if (!validTimezone(zone)) return { error: "Choose a valid IANA timezone." };
  if (!/^\d{4}-\d{2}-\d{2}T\d{2}:\d{2}$/.test(value)) return { error: "Enter a valid local date and time." };
  const wall = new Date(value + ":00Z");
  if (!Number.isFinite(wall.valueOf()) || wall.toISOString().slice(0, 16) !== value)
    return { error: "Enter a valid local date and time." };
  const formatter = new Intl.DateTimeFormat("en-CA", { timeZone: zone, hourCycle: "h23",
    year: "numeric", month: "2-digit", day: "2-digit", hour: "2-digit", minute: "2-digit", second: "2-digit" });
  const matches: number[] = [];
  // All IANA offsets lie within this range. Minute resolution matches the input.
  for (let offset = -1440; offset <= 1440; offset++) {
    const instant = wall.valueOf() + offset * 60_000;
    const parts = Object.fromEntries(formatter.formatToParts(instant).map(p => [p.type, p.value]));
    const local = `${parts.year}-${parts.month}-${parts.day}T${parts.hour}:${parts.minute}`;
    if (local === value && parts.second === "00") matches.push(instant);
  }
  if (!matches.length) return { error: "This local time does not exist in that timezone. Choose another time." };
  if (matches.length > 1) return { error: "This local time occurs twice during a clock change. Choose an unambiguous time." };
  if (matches[0] <= now) return { error: "Choose a future local date and time." };
  return { utc: new Date(matches[0]).toISOString() };
}

export function timezoneOptions(current: string): string[] {
  return [...new Set([current, "UTC", ...Intl.supportedValuesOf("timeZone")])].sort();
}

export function interviewJoinWindow(start:string,duration:number,zone:string) {
 const time=Date.parse(start);
 const format=new Intl.DateTimeFormat('en',{dateStyle:'medium',timeStyle:'short',timeZone:zone});
 return `Join from ${format.format(new Date(time-10*60000))} until ${format.format(new Date(time+(duration+15)*60000))} (${zone}).`;
}
