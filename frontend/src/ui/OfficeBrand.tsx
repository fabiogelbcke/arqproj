import { OfficeLogo } from "./OfficeLogo";

/** The office's mark in a header: its logo (which usually carries the name), or
 *  its name without one. The same on the painel's top bar and a project page's,
 *  where each wraps it in its link back to the painel. */
export function OfficeBrand({
  name,
  logo,
  logoDark,
}: {
  name: string;
  logo?: string | null;
  logoDark?: string | null;
}) {
  return logo ? <OfficeLogo light={logo} dark={logoDark} alt={name} /> : <span>{name}</span>;
}
