// The portfolio (backend/web/portfolio_page.py): a work's photos slid one at a
// time and opened large, the mosaic's columns, the menu of types as tabs, and a
// work opened over the works. Without this script the page still works: each link goes to its page.
const modified = (event) => event.metaKey || event.ctrlKey || event.shiftKey || event.button !== 0;

// A work's photos and videos open large over the page, one after another with
// the arrows, the keyboard or a swipe; a video plays only here, and a
// before-and-after comparison (A46) on its slider. Without this script each
// link opens the photo or the video alone (a comparison, its "before" photo).
// `root` is the page, or a work loaded into the layer below.
const wireLightbox = (root) => {
  const lightbox = root.querySelector(".lightbox");
  if (!lightbox || !lightbox.showModal) return;
  const links = [...root.querySelectorAll("a.zoom")];
  const image = lightbox.querySelector(":scope > img");
  const video = lightbox.querySelector("video");
  const count = lightbox.querySelector(".count");
  const compare = lightbox.querySelector(".compare");
  const handle = compare.querySelector(".handle");
  const before = compare.querySelector("img.before");
  const after = compare.querySelector("img.after");
  // The handle's place, in % from the left: the "before" photo shows up to it.
  const slide = (at) => {
    const kept = Math.round(Math.min(100, Math.max(0, at)));
    compare.style.setProperty("--at", `${kept}%`);
    handle.setAttribute("aria-valuenow", String(kept));
    handle.setAttribute("aria-valuetext", `${kept}% ${compare.dataset.before}, ${100 - kept}% ${compare.dataset.after}`);
  };
  const point = (x) => {
    const box = compare.getBoundingClientRect();
    if (box.width) slide(((x - box.left) / box.width) * 100);
  };
  compare.addEventListener("pointerdown", (event) => {
    if (event.button !== 0) return;
    compare.setPointerCapture(event.pointerId);
    point(event.clientX);
  });
  compare.addEventListener("pointermove", (event) => {
    if (compare.hasPointerCapture(event.pointerId)) point(event.clientX);
  });
  handle.addEventListener("keydown", (event) => {
    const now = Number(handle.getAttribute("aria-valuenow"));
    const step = event.shiftKey ? 20 : 5;
    const to = { ArrowLeft: now - step, ArrowDown: now - step, ArrowRight: now + step, ArrowUp: now + step, Home: 0, End: 100 }[event.key];
    if (to === undefined) return;
    event.preventDefault();
    event.stopPropagation(); // the handle's arrows, not the next photo
    slide(to);
  });
  // Both photos fill the "before" photo's shape, so they line up.
  before.addEventListener("load", () => {
    if (before.naturalWidth && before.naturalHeight)
      compare.style.setProperty("--shape", String(before.naturalWidth / before.naturalHeight));
  });
  let shown = 0;
  const stopVideo = () => {
    video.pause();
    video.removeAttribute("src");
    video.removeAttribute("poster");
    video.load(); // lets go of the file
  };
  const show = (index) => {
    shown = (index + links.length) % links.length;
    const link = links[shown];
    const label = link.querySelector("img:not(.backdrop)")?.alt ?? "";
    const film = link.classList.contains("film");
    const pair = link.dataset.after;
    stopVideo();
    image.hidden = film || !!pair;
    video.hidden = !film;
    compare.hidden = !pair;
    if (pair) {
      image.removeAttribute("src");
      compare.style.removeProperty("--shape");
      before.src = link.href;
      before.alt = label;
      after.src = pair;
      compare.dataset.before = link.dataset.beforeLabel;
      compare.dataset.after = link.dataset.afterLabel;
      compare.querySelector(".side.before").textContent = link.dataset.beforeLabel;
      compare.querySelector(".side.after").textContent = link.dataset.afterLabel;
      slide(50);
    } else if (film) {
      image.removeAttribute("src");
      video.poster = link.dataset.poster;
      video.src = link.href;
      video.setAttribute("aria-label", label);
      video.play().catch(() => {}); // asked for with a click; a browser may still wait for one on the video
    } else {
      image.src = link.href;
      image.alt = label;
    }
    count.textContent = `${shown + 1} / ${links.length}`;
  };
  links.forEach((link, index) =>
    link.addEventListener("click", (event) => {
      if (modified(event)) return; // a new tab, as asked
      event.preventDefault();
      lightbox.showModal();
      show(index);
    }),
  );
  const single = links.length < 2;
  for (const button of lightbox.querySelectorAll(".prev, .next")) button.hidden = single;
  count.hidden = single;
  lightbox.querySelector(".prev").addEventListener("click", () => show(shown - 1));
  lightbox.querySelector(".next").addEventListener("click", () => show(shown + 1));
  lightbox.querySelector(".close").addEventListener("click", () => lightbox.close());
  // A click on the dark backdrop, not the photo, the video or a button, closes it.
  lightbox.addEventListener("click", (event) => event.target === lightbox && lightbox.close());
  lightbox.addEventListener("keydown", (event) => {
    if (event.target === video) return; // its own keys: ← → move within the video
    if (event.key === "ArrowLeft") show(shown - 1);
    if (event.key === "ArrowRight") show(shown + 1);
  });
  let start = null;
  lightbox.addEventListener("touchstart", (event) => {
    // On a video a swipe may be its timeline being dragged, and on a comparison
    // it moves the slider: the arrows move on.
    start = event.target === video || compare.contains(event.target) ? null : event.touches[0].clientX;
  }, { passive: true });
  lightbox.addEventListener("touchend", (event) => {
    const moved = start === null ? 0 : event.changedTouches[0].clientX - start;
    if (Math.abs(moved) > 50) show(shown + (moved < 0 ? 1 : -1));
    start = null;
  });
  lightbox.addEventListener("close", () => {
    stopVideo();
    image.removeAttribute("src");
    before.removeAttribute("src");
    after.removeAttribute("src");
  });
};
wireLightbox(document);

// A work's photos, one at a time in a track that slides from one to the next:
// the arrows and the count below are shown here, and the keyboard's ← → move
// it too (not while a photo is open large: that viewer's arrows take them).
// The photos either side of the one shown are fetched ahead, so a slide never
// waits. `keys` is where the keyboard is heard: the page, or the layer below.
// Without this script the track still slides by swipe or trackpad.
const wireRun = (root, keys) => {
  const run = root.querySelector(".run");
  if (!run) return () => {};
  const track = run.querySelector(".track");
  const shots = [...track.children];
  const prev = run.querySelector(".stage > .prev");
  const next = run.querySelector(".stage > .next");
  const count = run.querySelector(":scope > .count");
  let shown = 0; // the one in view
  let wanted = 0; // the one slid to, which the arrows count from while the slide is still moving
  const ahead = (index) => {
    const img = shots[index]?.querySelector("img");
    if (img) img.loading = "eager";
  };
  const place = () => {
    const width = track.clientWidth || 1; // none yet in a layer still closed
    shown = Math.max(0, Math.min(shots.length - 1, Math.round(track.scrollLeft / width)));
    if (Math.abs(track.scrollLeft - shown * width) < 2) wanted = shown; // settled, by a swipe maybe
    if (count) count.textContent = `${shown + 1} / ${shots.length}`;
    if (prev) prev.disabled = shown === 0;
    if (next) next.disabled = shown === shots.length - 1;
    ahead(shown + 1);
    ahead(shown - 1);
  };
  const go = (index) => {
    wanted = Math.max(0, Math.min(shots.length - 1, index));
    track.scrollTo({ left: wanted * track.clientWidth });
  };
  for (const [button, step] of [[prev, -1], [next, 1]]) {
    if (!button) continue;
    button.hidden = false;
    button.addEventListener("click", () => go(wanted + step));
  }
  if (count) count.hidden = false;
  track.addEventListener("scroll", () => requestAnimationFrame(place), { passive: true });
  const onKey = (event) => {
    if (event.target.closest(".lightbox, video")) return;
    if (event.key !== "ArrowLeft" && event.key !== "ArrowRight") return;
    event.preventDefault(); // the track would also scroll a little on its own
    go(wanted + (event.key === "ArrowLeft" ? -1 : 1));
  };
  keys.addEventListener("keydown", onKey);
  place();
  return () => keys.removeEventListener("keydown", onKey); // for the layer, before its next work
};
wireRun(document, document);

// The mosaic format (the works' covers, or a work's images): in the order
// staff set them, left to right then down, in as many columns as fit, never
// fewer than two (a phone shows two, as VSCO does). Without this, the
// stylesheet's columns fill top to bottom first. Gives back a way to lay the
// mosaic out again.
const layMosaic = (mosaic) => {
  const works = [...mosaic.children];
  const lay = (again = false) => {
    const width = mosaic.clientWidth;
    const count = width > 1020 ? 3 : 2;
    if (!again && mosaic.dataset.columns === String(count)) return;
    mosaic.dataset.columns = String(count);
    mosaic.replaceChildren();
    const columns = works.slice(0, count).map(() => {
      const column = document.createElement("li");
      column.className = "column";
      const list = document.createElement("ul");
      column.append(list);
      mosaic.append(column);
      return list;
    });
    // A work hidden by the menu of types stays out of the columns.
    works.filter((work) => !work.hidden).forEach((work, index) => columns[index % count].append(work));
  };
  lay();
  new ResizeObserver(() => lay()).observe(mosaic);
  return () => lay(true);
};
// Every work's card, those a filtered address (`/?tipo=…`) hides too, taken
// before the mosaic leaves the hidden ones out of the page: the menu of types
// below shows them again.
const cards = [...document.querySelectorAll(".works > li, .mosaic > li")];
let relayMosaic = () => {};
// A work's images get their shape as `--r`, so the stylesheet can size each one
// to fit the screen's height as well as its width (an inline style in the page
// itself is not allowed by its security policy; one set from here is).
const shapePosts = (root) => {
  for (const image of root.querySelectorAll(".posts img[width][height]")) {
    image.style.setProperty("--r", String(image.getAttribute("width") / image.getAttribute("height")));
  }
};
shapePosts(document);
for (const mosaic of document.querySelectorAll(".mosaic")) {
  const relay = layMosaic(mosaic);
  if (!mosaic.classList.contains("posts")) relayMosaic = relay;
}

// The menu of types switches the works shown in place, as tabs, and keeps the
// address (`/?tipo=interiors`) so it can be shared and the back button works.
// Without this script each link reloads the page with that type.
const types = document.querySelector(".types");
if (types) {
  const links = [...types.querySelectorAll("a")];
  const key = (href) => new URL(href, location.href).searchParams.get("tipo");
  const show = (wanted) => {
    for (const link of links) {
      if (key(link.href) === wanted) link.setAttribute("aria-current", "page");
      else link.removeAttribute("aria-current");
    }
    for (const card of cards) card.hidden = wanted !== null && card.dataset.type !== wanted;
    relayMosaic();
  };
  links.forEach((link) =>
    link.addEventListener("click", (event) => {
      if (modified(event)) return; // a new tab, as asked
      event.preventDefault();
      const url = new URL(link.href);
      url.hash = "";
      history.pushState(null, "", url);
      show(key(link.href));
    }),
  );
  addEventListener("popstate", () => show(key(location.href)));
}

// A work opens over the works: its page is fetched and shown in the layer,
// scrolling on its own, with the address following (`/?projeto=…`) so it can
// be shared and the back button closes it. × or Escape closes it back to the
// same place in the grid; "Próximo projeto" moves on within the layer. Without
// this script, or when the page can't be fetched, the link goes to the page.
const layer = document.querySelector(".layer");
if (layer && layer.showModal && window.fetch) {
  const body = layer.querySelector(".layer-body");
  const home = document.title;
  let opener = null; // the cover clicked, to go back to
  let pushed = false; // the address moved to the work: closing moves it back
  let leaving = false; // closing because the address moved back already
  let asked = 0; // the latest work asked for: an older answer, or one after closing, is dropped
  let unwireRun = () => {}; // lets go of the keys the work shown took
  const open = async (url, push) => {
    const mine = ++asked;
    let doc;
    try {
      const answer = await fetch(url, { headers: { Accept: "text/html" } });
      if (!answer.ok) throw new Error(String(answer.status));
      doc = new DOMParser().parseFromString(await answer.text(), "text/html");
    } catch {
      if (mine === asked) location.href = url;
      return;
    }
    if (mine !== asked) return;
    const main = doc.querySelector("main");
    if (!main || !main.querySelector(".work")) {
      location.href = url;
      return;
    }
    body.replaceChildren(...main.children);
    document.title = doc.title;
    layer.setAttribute("aria-label", body.querySelector("h1")?.textContent ?? doc.title);
    wireLightbox(body);
    unwireRun();
    unwireRun = wireRun(body, layer);
    shapePosts(body);
    for (const mosaic of body.querySelectorAll(".mosaic")) layMosaic(mosaic);
    body.querySelector("a.back")?.addEventListener("click", (event) => {
      if (modified(event)) return;
      event.preventDefault();
      layer.close();
    });
    body.querySelector("a.following")?.addEventListener("click", (event) => {
      if (modified(event)) return;
      event.preventDefault();
      const next = new URL(event.currentTarget.href);
      history.replaceState({ work: true }, "", next);
      open(next.href, false);
    });
    if (push) {
      history.pushState({ work: true }, "", url);
      pushed = true;
    }
    if (!layer.open) {
      layer.showModal();
      document.body.classList.add("held");
    }
    layer.scrollTop = 0;
  };
  // Every card's link, those a filtered mosaic left out of the page too (the
  // menu of types brings them back).
  for (const link of cards.flatMap((card) => [...card.querySelectorAll("a")])) {
    link.addEventListener("click", (event) => {
      if (modified(event)) return; // a new tab, as asked
      event.preventDefault();
      opener = link;
      open(link.href, true);
    });
  }
  layer.querySelector(":scope > .close").addEventListener("click", () => layer.close());
  layer.addEventListener("close", () => {
    asked++; // a work still on its way stays out
    unwireRun();
    unwireRun = () => {};
    body.replaceChildren();
    document.body.classList.remove("held");
    document.title = home;
    opener?.focus();
    if (pushed && !leaving) history.back();
    pushed = false;
    leaving = false;
  });
  addEventListener("popstate", () => {
    const wanted = new URL(location.href).searchParams.get("projeto");
    if (wanted) {
      pushed = true; // forward, to a work seen before: closing goes back again
      open(location.href, false);
    } else {
      asked++; // back at the grid: a work still on its way stays out
      if (layer.open) {
        leaving = true;
        layer.close();
      }
    }
  });
}
