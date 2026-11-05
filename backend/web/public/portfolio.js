// The portfolio (backend/web/portfolio_page.py): photos opened large, the
// mosaic's columns, the menu of types as tabs, and a work opened over the
// works. Without this script the page still works: each link goes to its page.
const modified = (event) => event.metaKey || event.ctrlKey || event.shiftKey || event.button !== 0;

// A work's photos and videos open large over the page, one after another with
// the arrows, the keyboard or a swipe; a video plays only here. Without this
// script each link opens the photo or the video alone. `root` is the page, or
// a work loaded into the layer below.
const wireLightbox = (root) => {
  const lightbox = root.querySelector(".lightbox");
  if (!lightbox || !lightbox.showModal) return;
  const links = [...root.querySelectorAll("a.zoom")];
  const image = lightbox.querySelector("img");
  const video = lightbox.querySelector("video");
  const count = lightbox.querySelector(".count");
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
    stopVideo();
    image.hidden = film;
    video.hidden = !film;
    if (film) {
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
    // On a video a swipe may be its timeline being dragged: the arrows move on.
    start = event.target === video ? null : event.touches[0].clientX;
  }, { passive: true });
  lightbox.addEventListener("touchend", (event) => {
    const moved = start === null ? 0 : event.changedTouches[0].clientX - start;
    if (Math.abs(moved) > 50) show(shown + (moved < 0 ? 1 : -1));
    start = null;
  });
  lightbox.addEventListener("close", () => {
    stopVideo();
    image.removeAttribute("src");
  });
};
wireLightbox(document);

// The mosaic format (the works' covers, or a work's images): in the order
// staff set them, left to right then down, in as many columns as fit; a work's
// images keep two on a phone. Without this, the stylesheet's columns fill top
// to bottom first. Gives back a way to lay the mosaic out again.
const layMosaic = (mosaic) => {
  const works = [...mosaic.children];
  const least = mosaic.classList.contains("posts") ? 2 : 1;
  const lay = (again = false) => {
    const width = mosaic.clientWidth;
    const count = width > 1020 ? 3 : width > 500 ? 2 : least;
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
  const open = async (url, push) => {
    let doc;
    try {
      const answer = await fetch(url, { headers: { Accept: "text/html" } });
      if (!answer.ok) throw new Error(String(answer.status));
      doc = new DOMParser().parseFromString(await answer.text(), "text/html");
    } catch {
      location.href = url;
      return;
    }
    const main = doc.querySelector("main");
    if (!main || !main.querySelector(".work")) {
      location.href = url;
      return;
    }
    body.replaceChildren(...main.children);
    document.title = doc.title;
    layer.setAttribute("aria-label", body.querySelector("h1")?.textContent ?? doc.title);
    wireLightbox(body);
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
  for (const link of document.querySelectorAll(".works a, .mosaic a")) {
    link.addEventListener("click", (event) => {
      if (modified(event)) return; // a new tab, as asked
      event.preventDefault();
      opener = link;
      open(link.href, true);
    });
  }
  layer.querySelector(":scope > .close").addEventListener("click", () => layer.close());
  layer.addEventListener("close", () => {
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
    } else if (layer.open) {
      leaving = true;
      layer.close();
    }
  });
}
