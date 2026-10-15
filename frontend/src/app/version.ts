// Noticing a new deploy (plan A30). An open tab keeps running the build it
// loaded; when the API reports a different build, or one of this build's files
// can no longer be loaded, the app offers a reload instead of breaking. It never
// reloads by itself, so nothing typed is lost.

declare const __BUILD_ID__: string;
export const BUILD_ID = __BUILD_ID__;

let newVersion = false;
const listeners = new Set<() => void>();

function announce(): void {
  if (newVersion) return;
  newVersion = true;
  listeners.forEach((listener) => listener());
}

/** "dev" on either side means a local build: nothing to compare. */
export function isNewerBuild(ours: string, server: string | null): boolean {
  return !!server && server !== "dev" && ours !== "dev" && server !== ours;
}

export function noteServerBuild(serverBuild: string | null): void {
  if (isNewerBuild(BUILD_ID, serverBuild)) announce();
}

// Vite fires this when a lazily loaded file of this build is gone after a deploy.
window.addEventListener("vite:preloadError", (event) => {
  event.preventDefault();
  announce();
});

export const newVersionStore = {
  subscribe(listener: () => void) {
    listeners.add(listener);
    return () => listeners.delete(listener);
  },
  snapshot: () => newVersion,
};
