// When a screen shows a query's error. TanStack Query keeps a query's data when
// a background refresh fails, and sets its error as well: a screen that looked
// at the error first swapped what it was showing for the error, and nothing
// brought it back. So the error shows only while there is nothing else to show.

/** The query's error while it has no data (its first load failed); null once it
 *  has something to show, even if a later refresh failed. */
export function loadError<E>(query: { data: unknown; error: E }): E | null {
  return query.data == null ? query.error : null;
}
