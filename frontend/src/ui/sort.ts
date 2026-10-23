// An order and its direction as one choice ("Nome: A–Z"), for every list that
// sorts (the painel's projects, a project page's files): one dropdown, not a
// dropdown and a direction button (Fabio, 22 Oct 2026).

export type Direction = "asc" | "desc";
export type Sort<K extends string> = { key: K; direction: Direction };

/** Every key in both directions, in `keys`' order: dates newest first, the rest A–Z first. */
export function sortOptions<K extends string>(keys: readonly K[], dates: readonly K[]): Sort<K>[] {
  return keys.flatMap((key): Sort<K>[] =>
    dates.includes(key)
      ? [{ key, direction: "desc" }, { key, direction: "asc" }]
      : [{ key, direction: "asc" }, { key, direction: "desc" }],
  );
}

/** As a dropdown's value: "updated-desc". */
export const sortValue = <K extends string>(sort: Sort<K>) => `${sort.key}-${sort.direction}`;

/** Back from a value; one that isn't among `options` gives `fallback`. */
export function sortFromValue<K extends string>(value: string, options: Sort<K>[], fallback: Sort<K>): Sort<K> {
  return options.find((option) => sortValue(option) === value) ?? fallback;
}

/** Its label's catalog key: "sort.updated_desc". */
export const sortLabelKey = <K extends string>(sort: Sort<K>) => `sort.${sort.key}_${sort.direction}`;
