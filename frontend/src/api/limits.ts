// The longest text staff can enter in each field, as the server enforces it
// (backend/web/limits.py). Generated with the API types (`make api-types`); a
// backend test fails if limits.json is out of date. Screens never write their own.
import limits from "./limits.json";

export const LIMITS: Readonly<typeof limits> = limits;
